"""Filtro y puntaje por reglas (rápido, sin IA). La IA afina después sobre las mejores."""

import re
from functools import lru_cache

from .util import norm

# Valores por defecto del perfil. Se pueden pisar desde config.json (`perfil.stack_core` y
# `perfil.stack_ajeno`) para actualizar el perfil sin tocar código.
#
# Tecnologías principales del CV de Santiago (las que definen si una oferta técnica le sirve).
STACK_CORE = {
    "JavaScript": ["javascript", "js", "es6"],
    "TypeScript": ["typescript", "ts"],
    "Node.js": ["node", "nodejs", "node.js"],
    "Express": ["express", "expressjs", "express.js"],
    "React": ["react", "reactjs", "react.js"],
    "React Native": ["react native", "react-native", "reactnative"],
    "Expo": ["expo"],
    "Python": ["python"],
    "Django": ["django"],
    "Flask": ["flask"],
    "SQL": ["sql", "mysql", "postgres", "postgresql", "sqlite"],
    "HTML/CSS": ["html", "html5", "css", "css3", "bootstrap"],
    "APIs REST": ["api rest", "apis rest", "restful", "rest api"],
    "AWS": ["aws", "amazon web services"],
    "Google Cloud": ["gcp", "google cloud"],
    "Salesforce": ["salesforce", "trailhead"],
    "Datos/BI": ["power bi", "business intelligence", "pandas", "data analytics", "analisis de datos", "etl", "tableau", "looker"],
    "scikit-learn": ["scikit-learn", "scikit learn", "sklearn"],
    "C# (básico)": ["c#"],
}

# Herramientas complementarias que suman puntos pero por sí solas no definen el puesto.
STACK_COMPLEMENTARIO = {
    "Git": ["git", "github", "gitlab"],
    "Scrum/Ágil": ["scrum", "kanban", "agil", "agile"],
    "Postman": ["postman"],
}

# Los 3 puestos objetivo (en orden de prioridad): términos que, en el título, indican que la oferta encaja.
PUESTOS_OBJETIVO = {
    "Desarrollo Full Stack / Frontend / Backend": [
        "desarrollador", "developer", "programador", "desarrollo de software", "full stack", "fullstack",
        "full-stack", "frontend", "front end", "front-end", "backend", "back end", "back-end",
        "ingeniero de software", "software engineer",
    ],
    "Datos / BI": [
        "analista de datos", "data analyst", "analista bi", "analista de bi", "bi analyst",
        "business intelligence", "analytics", "analista de inteligencia",
    ],
    "Cloud": ["cloud", "devops"],
}

# Entradas del stack core que por sí solas no alcanzan para decir que la oferta es de desarrollo/datos/cloud.
STACK_CORE_NO_PRIMARIO = ("APIs REST", "C# (básico)")

# Jornada parcial o por proyecto: resta puntos pero no excluye (Santiago prefiere full time).
JORNADA_PARCIAL = [
    "part time", "part-time", "parttime", "medio tiempo", "jornada parcial", "jornada reducida",
    "freelance", "freelancer",
]

REMOTO = ["remoto", "remote", "home office", "teletrabajo", "100% remoto", "fully remote"]

# Tecnologías o rubros en el TÍTULO que descartan la oferta porque no son el perfil de Santiago
TITULO_STACK_AJENO = [
    ".net", "vb.net", "asp.net", "java", "spring", "angular", "vue", "php", "laravel", "symfony",
    "cobol", "golang", "ruby", "rails", "flutter", "android", "ios", "kotlin", "swift",
    "sap", "abap", "hana", "genexus", "delphi", "wordpress", "drupal", "magento", "shopify", "odoo",
    "c++", "rust", "scala", "elixir", "mainframe", "as400", "rpg", "pl/sql", "oracle forms",
    "power platform", "power apps", "powerapps", "sharepoint", "dynamics", "microstrategy", "qlik",
    "cnc", "plc", "scada", "electronico", "electronica", "electromecanico", "mecanic", "electricista",
    "incendios", "cctv", "redes", "telecomunicaciones", "hardware", "reparacion", "microinformatic",
    "mesa de ayuda", "help desk", "helpdesk", "soporte tecnico", "technical support",
    "bejerman", "tango", "calipso", "finnegans",
]

# Exigencias excluyentes en la descripción que no aplican al perfil de Santiago
DESC_EXCLUYENTES_NO_DEV = [
    "no son puestos para perfiles de desarrollo",
    "mesa de ayuda",
    "help desk",
    "reparacion de pc",
    "armado y reparacion",
    "cableado estructurado",
    "programacion de plc",
    "torno cnc",
    "centro de mecanizado",
    "deteccion de incendios",
    "direccion caba en el dni",
    "ingenieria electronica",
    "labview",
    "simulink",
]

# Stacks principales ajenos en la descripción (excluyen si la oferta NO menciona Node/React/Python/Django)
DESC_STACK_AJENO_ESTRICTO = [
    ".net core", "asp.net", "vb.net", "entity framework", "winforms",
    "spring boot", "jakarta ee", "hibernate", "jsf", "maven",
    "php", "laravel", "symfony", "codeigniter", "wordpress",
    "angular", "vuejs", "vue.js",
    "sap business one", "sap b1", "sap fi", "sap mm", "sap sd", "abap",
    "genexus", "delphi", "cobol", "rpg", "as400",
    "flutter", "kotlin", "swift", "objective-c",
    "microstrategy", "odoo", "dynamics 365",
]

# Exigencia de inglés avanzado / bilingüe. Santiago tiene B2: «intermedio», «intermedio-avanzado» y
# «upper intermediate» alcanzan, así que no figuran acá.
INGLES_AVANZADO = [
    "ingles avanzado", "ingles bilingue", "ingles fluido", "ingles nativo", "ingles c1", "ingles c2",
    "advanced english", "fluent english", "proficient english", "english proficient", "bilingual english",
    "nivel de ingles avanzado", "ingles oral avanzado",
    "english c1", "english c2", "c1 english", "c2 english", "bilingue", "bilingual",
]

# Rangos que arrancan en B2 («intermedio-avanzado», «upper intermediate to advanced»): se ignoran al buscar
# exigencias de inglés avanzado, porque el piso del rango ya lo cubre B2.
RANGO_B2_A_AVANZADO = re.compile(
    r"(?:upper[- ]intermediate|intermediate|intermedio)\s*(?:-|/|to|a|o)\s*(?:advanced|avanzado)"
)

# Frases que indican que el aviso acepta explícitamente candidatos sin experiencia laboral formal
ACEPTA_SIN_EXPERIENCIA = [
    "sin experiencia laboral", "sin experiencia previa", "experiencia academica", "proyectos personales",
    "proyectos academicos", "primer empleo", "primer trabajo", "formacion en bootcamps",
    "aprendizaje autodidacta", "pasantia", "programa de pasantias", "jovenes profesionales",
]


# Un remoto desde el exterior sólo sirve si el aviso dice que acepta Argentina / LATAM / cualquier lugar.
ACEPTA_ARGENTINA = [
    "argentina", "latam", "latinoamerica", "latin america", "anywhere", "worldwide",
    "cualquier parte del mundo", "cualquier lugar del mundo",
]

# Exigencias de residencia o permiso de trabajo en otro país: excluyen aunque el puesto sea remoto.
EXIGE_RESIDENCIA = [
    "must reside", "must be located in", "residir en", "residentes en", "residencia en", "us citizen",
    "us only", "u.s. citizen", "work authorization", "authorized to work in", "legally authorized",
    "right to work in",
]

HIBRIDO = ["hibrido", "hybrid"]
PRESENCIAL = ["presencial", "on-site", "onsite", "on site"]

# Países y regiones fuera de Argentina a excluir estrictamente (incluso si dicen 'remoto')
PAISES_EXTRANJEROS = [
    "estados unidos", "united states", "eeuu", "ee.uu.", "usa", "u.s.a.", "u.s.", "us only", "us citizen",
    "california", "florida", "texas", "new york", "miami", "san francisco", "austin", "seattle", "chicago",
    "chile", "santiago de chile", "colombia", "bogota", "medellin", "cali",
    "mexico", "méxico", "cdmx", "guadalajara", "monterrey",
    "peru", "perú", "lima",
    "uruguay", "montevideo",
    "espana", "españa", "madrid", "barcelona", "valencia",
    "ecuador", "quito", "guayaquil",
    "brasil", "brazil", "sao paulo",
    "venezuela", "caracas",
    "costa rica", "san jose",
    "panama", "panamá",
    "canada", "canadá", "toronto", "vancouver",
    "reino unido", "uk", "london", "alemania", "germany", "berlin",
]

# Provincias argentinas alejadas de Buenos Aires (solo excluyen si es presencial o híbrido)
PROVINCIAS_LEJANAS = [
    "cordoba", "rosario", "santa fe", "mendoza", "tucuman", "neuquen", "salta", "jujuy", "chubut",
    "mar del plata", "bahia blanca", "tandil", "san juan", "san luis", "misiones", "corrientes",
    "entre rios", "parana", "rio negro", "bariloche", "la pampa", "santiago del estero", "catamarca",
    "la rioja", "formosa", "chaco", "santa cruz", "tierra del fuego",
]


def stack_core(cfg: dict) -> dict:
    """Stack propio {nombre: [alias]} según config.json; si falta, el default."""
    return cfg.get("perfil", {}).get("stack_core") or STACK_CORE


def stack_ajeno(cfg: dict) -> list:
    """Términos del título que descartan la oferta, según config.json; si faltan, el default."""
    return cfg.get("perfil", {}).get("stack_ajeno") or TITULO_STACK_AJENO


def puestos_objetivo(cfg: dict) -> dict:
    """Puestos objetivo {nombre: [términos del título]} según config.json; si faltan, el default."""
    return cfg.get("perfil", {}).get("puestos_objetivo") or PUESTOS_OBJETIVO


@lru_cache(maxsize=2048)
def _rx(term: str) -> re.Pattern:
    t = norm(term.strip())
    # Términos cortos (o que terminan en símbolo) van como palabra exacta; los largos aceptan sufijos
    # (ej. "desarroll" -> desarrollador, "senior" -> seniority).
    right = r"(?![a-z0-9])" if len(t) <= 5 or not t[-1].isalnum() else ""
    return re.compile(r"(?<![a-z0-9])" + re.escape(t) + right)


def find_term(text: str, terms) -> str | None:
    for term in terms:
        if term.strip() and _rx(term).search(text):
            return term.strip()
    return None


def find_all(text: str, terms) -> list:
    return [t.strip() for t in terms if t.strip() and _rx(t).search(text)]


def years_required(desc: str) -> int | None:
    """Detecta 'X años de experiencia'. Ignora 'hasta X años' o cuando aclara que acepta sin experiencia."""
    if any(p in desc for p in ACEPTA_SIN_EXPERIENCIA):
        return 0
    found = []
    for m in re.finditer(r"(\d{1,2})\s*(?:a|-|–|o|y|to)\s*(\d{1,2})\s*\+?\s*(?:anos|years|yrs)", desc):
        ctx = desc[max(0, m.start() - 50): m.end() + 50]
        if "experien" in ctx:
            found.append(int(m.group(1)))
    for m in re.finditer(r"(\d{1,2})\s*\+?\s*(?:anos|years|yrs)", desc):
        before = desc[max(0, m.start() - 35): m.start()]
        if any(w in before for w in ("hasta", "menos de", "maximo", "0 a", "0 -", "entre 0")):
            continue
        ctx = desc[max(0, m.start() - 50): m.end() + 50]
        if "experien" in ctx:
            found.append(int(m.group(1)))
    found = [n for n in found if 0 < n <= 10]
    return min(found) if found else None


def _is_mostly_english(text: str) -> bool:
    if len(text) < 120:
        return False
    es_hits = sum(1 for w in (" de ", " la ", " el ", " en ", " con ", " para ", " que ", " por ", " los ", " las ") if w in text)
    en_hits = sum(1 for w in (" the ", " and ", " with ", " for ", " you ", " our ", " will ", " work ", " team ", " experience ") if w in text)
    return en_hits >= 5 and en_hits > es_hits * 2


def evaluate(job: dict, cfg: dict) -> dict:
    f = cfg["filtros"]
    title = norm(job.get("title"))
    desc = norm(job.get("description"))
    loc = norm(job.get("location"))
    modality = norm(job.get("modality"))
    extra = job.get("extra") or {}
    reasons = []
    exclude = None

    def add(points: int, text: str) -> None:
        reasons.append({"p": points, "t": text})

    full = f"{title} {desc}"
    matched_core = [name for name, aliases in stack_core(cfg).items() if find_term(full, aliases)]
    matched_comp = [name for name, aliases in STACK_COMPLEMENTARIO.items() if find_term(full, aliases)]
    matched = matched_core + matched_comp

    # Tecnologías de desarrollo web/datos/cloud de Santiago para validar si la oferta es de su palo
    has_primary_dev_stack = any(k not in STACK_CORE_NO_PRIMARIO for k in matched_core)

    # ---------- exclusiones duras ----------
    # 1. Seniority alto o Semi-Senior en el título
    hit = find_term(title, f["excluir_titulo"])
    if hit:
        exclude = f"Seniority excluido en el título («{hit}»)"

    # 2. Títulos no técnicos o no IT
    if not exclude:
        hit = find_term(title, f["titulo_no_tecnico"])
        if hit:
            exclude = f"No es un puesto de desarrollo («{hit}»)"

    # 3. Tecnología o rubro en el título que no coincide con el perfil de Santiago (.NET, Java, Angular, SAP, PLC, Soporte, etc.)
    if not exclude:
        hit_foreign_title = find_term(title, stack_ajeno(cfg))
        if hit_foreign_title and not has_primary_dev_stack:
            exclude = f"Pide tecnología/rubro ajeno a tu CV en el título («{hit_foreign_title}»)"
        elif hit_foreign_title and hit_foreign_title in (
            ".net", "vb.net", "asp.net", "java", "angular", "vue", "php", "laravel", "cobol", "golang",
            "ruby", "flutter", "android", "ios", "kotlin", "swift", "sap", "abap", "genexus", "delphi",
            "cnc", "plc", "electronico", "electronica", "electromecanico", "mecanic", "incendios", "cctv",
            "mesa de ayuda", "help desk", "helpdesk", "soporte tecnico",
        ):
            exclude = f"Puesto centrado en «{hit_foreign_title}» (no coincide con tu stack principal)"

    if not exclude and not find_term(title, f["palabras_tecnicas"]):
        if not (find_term(title, f["senales_junior"]) and find_term(desc, f["palabras_tecnicas"])):
            exclude = "No parece un puesto de desarrollo / IT"

    # 4. Seniority según metadatos del portal (Get on Board, LinkedIn)
    sen_id = extra.get("seniority_id")
    if not exclude and sen_id in (3, 4, 5):
        exclude = f"Seniority {extra.get('nivel', 'Semi Senior / Senior')} según el portal"

    sen_txt = norm(extra.get("seniority_text", ""))
    if not exclude and sen_txt:
        if any(k in sen_txt for k in ("intermedio", "mid-senior", "mid senior", "mid level", "semi senior", "semisenior", "senior", "director", "ejecutivo", "lead")):
            exclude = f"Seniority no junior según el portal («{extra.get('seniority_text')}»)"

    # 5. Señal obligatoria de Junior / Trainee / Pasante / Estudiante / Primer Empleo
    has_jr_title = bool(find_term(title, f["senales_junior"]))
    has_jr_desc = bool(find_term(desc, f["senales_junior"])) or any(p in desc for p in ACEPTA_SIN_EXPERIENCIA)
    has_jr_portal = (sen_id in (1, 2)) or any(k in sen_txt for k in ("sin experiencia", "practicas", "entry", "intern"))
    if not exclude and not (has_jr_title or has_jr_desc or has_jr_portal):
        exclude = "No está orientada a perfiles Junior / Trainee / Estudiantes"

    # 6. Años de experiencia o mención explícita de Semi Senior en la descripción
    years = years_required(desc)
    if not exclude and years is not None and years >= 3:
        exclude = f"Exige {years}+ años de experiencia (buscás primer empleo / trainee / junior)"
    aplica_igual = years == 2  # 2 años: no se excluye, se avisa que conviene postular igual

    if not exclude and any(k in desc for k in (
        "semi senior", "semisenior", "semi-senior", "perfil ssr", "desarrollador ssr", "programador ssr",
        "jr/ssr", "jr / ssr", "jr o ssr", "jr a ssr",
    )):
        exclude = "El texto del aviso indica perfil Semi Senior (SSR)"

    # 7. Ubicación: Argentina. Un remoto desde el exterior se acepta si dice que admite Argentina/LATAM.
    is_remote = bool(find_term(f"{loc} {modality} {title}", REMOTO))
    es_hibrido_o_presencial = bool(find_term(full, HIBRIDO) or find_term(f"{loc} {modality} {title}", PRESENCIAL))
    remoto_total = is_remote and not es_hibrido_o_presencial

    pais_extranjero = find_term(f"{loc} {title}", PAISES_EXTRANJEROS)
    countries = extra.get("countries")
    fuera_de_argentina = bool(pais_extranjero) or (countries is not None and "Argentina" not in countries)
    remoto_exterior = False
    if not exclude and fuera_de_argentina:
        lugar = pais_extranjero.title() if pais_extranjero else (", ".join(countries) or "Exterior")
        residencia = find_term(full, EXIGE_RESIDENCIA)
        if residencia:
            exclude = f"Exige residir/trabajar en otro país («{residencia}», {lugar})"
        elif not remoto_total:
            exclude = f"Presencial/híbrido fuera de Argentina ({lugar})"
        elif not find_term(full, ACEPTA_ARGENTINA):
            exclude = f"Remoto desde el exterior sin aclarar que acepta Argentina/LATAM ({lugar})"
        else:
            remoto_exterior = True

    # 8. Presencial o híbrido fuera de Buenos Aires (CABA / GBA)
    if not exclude and not is_remote:
        far_local = find_term(loc, PROVINCIAS_LEJANAS)
        if far_local:
            exclude = f"Presencial/híbrido fuera de Buenos Aires ({far_local.title()})"

    # 9. Inglés avanzado / bilingüe o aviso íntegro en inglés (contractor exterior)
    if not exclude:
        hit_eng = find_term(RANGO_B2_A_AVANZADO.sub(" ", full), INGLES_AVANZADO)
        if hit_eng:
            exclude = f"Exige inglés avanzado/bilingüe («{hit_eng}»; tu CV indica B2 lectura técnica)"
        elif _is_mostly_english(desc):
            exclude = "Aviso redactado íntegramente en inglés (exige inglés fluido / contractor internacional)"

    # 10. Descripción de soporte / mesa de ayuda / hardware o stack excluyente que no manejás
    if not exclude:
        hit_nodev = find_term(desc, DESC_EXCLUYENTES_NO_DEV)
        if hit_nodev:
            exclude = f"No aplicable a tu perfil («{hit_nodev}»)"

    if not exclude and desc:
        hit_strict_foreign = find_all(desc, DESC_STACK_AJENO_ESTRICTO)
        # Si pide explícitamente .NET, Java/Spring, Angular, SAP, GeneXus, etc. y NO menciona Node, React, Python ni JS
        if hit_strict_foreign and not any(k in matched_core for k in ("Node.js", "Express", "React", "Python", "Django")):
            exclude = "Pide stack que no manejás (" + ", ".join(hit_strict_foreign[:3]) + ")"

    # Regla de portfolio: tiene que mencionar tecnología de tu stack core o encajar con uno de tus puestos objetivo
    puesto = next((n for n, terms in puestos_objetivo(cfg).items() if find_term(title, terms)), None)
    if not exclude and desc and not has_primary_dev_stack and not puesto:
        exclude = "No menciona tecnologías de tu stack ni encaja con tus puestos objetivo (Desarrollo, Datos/BI, Cloud)"

    # ---------- puntaje ----------
    score = 35

    if has_jr_title:
        score += 25
        add(25, "Junior / Trainee / Pasante en el título")
    elif sen_id in (1, 2):
        score += 25
        add(25, "El portal la marca como Junior / Sin experiencia")
    elif has_jr_desc:
        score += 15
        add(15, "Menciona perfil junior / estudiante en la descripción")

    if any(p in desc for p in ACEPTA_SIN_EXPERIENCIA):
        score += 10
        add(10, "Acepta experiencia académica / proyectos / primer empleo")

    if years == 1:
        add(0, "Piden hasta 1 año de experiencia (podés postular con tus proyectos)")
    elif aplica_igual:
        score -= 10
        add(-10, "Piden 2 años de experiencia: aplicá igual, destacando tus proyectos")

    if matched_core:
        pts = min(35, 7 * len(matched_core))
        score += pts
        add(pts, "Coincide con tu stack principal: " + ", ".join(matched_core))
    if matched_comp:
        pts = min(9, 3 * len(matched_comp))
        score += pts
        add(pts, "Herramientas de tu CV: " + ", ".join(matched_comp))

    foreign_desc = find_all(desc, f["tecnologias_ajenas"])
    if foreign_desc:
        pts = min(9, 3 * len(foreign_desc))
        score -= pts
        add(-pts, "También mencionan: " + ", ".join(foreign_desc[:5]))

    jornada = find_term(f"{title} {desc} {modality}", JORNADA_PARCIAL)
    if jornada:
        score -= 10
        add(-10, f"Jornada parcial o freelance («{jornada}»): preferís full time")

    if is_remote:
        score += 10
        add(10, "Modalidad remota")
    if remoto_exterior:
        score -= 5
        add(-5, "Remoto desde el exterior (acepta Argentina/LATAM)")
    if find_term(loc, f["zona_sur"]):
        score += 15
        add(15, "En Zona Sur, cerca tuyo")
    elif find_term(loc, f["zona_preferida"]):
        score += 12
        add(12, "En CABA")
    elif find_term(loc, f["gba_lejano"]):
        far = find_term(loc, f["gba_lejano"])
        score -= 12
        add(-12, f"GBA alejado de Zona Sur ({far.title()})")
    elif "buenos aires" in loc or "gba" in loc:
        score += 5
        add(5, "Buenos Aires / AMBA")
    elif countries and "Argentina" in countries:
        score += 5
        add(5, "Argentina")

    score = max(0, min(100, score))
    if exclude:
        reasons.insert(0, {"p": None, "t": "Filtrada: " + exclude})
    etiqueta = None if exclude else ("aplicá igual" if aplica_igual else "encaja")
    return {"score": score, "reasons": reasons, "excluded": bool(exclude), "exclude_reason": exclude,
            "matched_stack": matched, "etiqueta": etiqueta}
