"""Análisis de ofertas y redacción de cartas con Gemini (API REST, sin dependencias extra).

Regla central: la IA sólo puede usar datos de perfil/cv.md. Nunca inventa experiencia.
"""

import json
import re

import requests

from .config import gemini_key, load_config, load_cv

API = "https://generativelanguage.googleapis.com/v1beta"
_resolved_model = None


class AIError(Exception):
    pass


class AIRateLimit(AIError):
    pass


SYSTEM = """Sos un asistente de búsqueda laboral para un desarrollador junior argentino que busca su primer empleo IT.

REGLAS ESTRICTAS (no negociables):
1. Usá ÚNICAMENTE la información del CV y del perfil del candidato que se te da.
2. NUNCA inventes ni exageres: experiencia laboral, años de experiencia, horarios de cursada, empresas,
   métricas, logros, tecnologías, títulos o certificaciones que no estén en el CV.
3. El candidato NO tiene experiencia laboral formal en IT: su experiencia es de proyectos académicos y cursos.
   Nunca lo presentes como si tuviera experiencia laboral.
4. Si el aviso pide algo que el candidato no tiene, no lo afirmes. Podés mencionar con honestidad
   la base relacionada que sí tiene y su disposición a aprender.
5. Escribí en español rioplatense profesional (sin modismos excesivos)."""


def available() -> bool:
    cfg = load_config()
    return bool(cfg.get("ia", {}).get("habilitada", True) and gemini_key())


def _candidate_context() -> str:
    cfg = load_config()
    c = cfg.get("candidato", {})
    perfil = "\n".join(f"- {k.replace('_', ' ').capitalize()}: {v}" for k, v in c.items())
    return f"PERFIL DEL CANDIDATO:\n{perfil}\n\nCV (fuente de verdad):\n{load_cv()}"


def _job_context(job) -> str:
    desc = (job["description"] or "(sin descripción disponible)")[:9000]
    return (
        f"AVISO:\nTítulo: {job['title']}\nEmpresa: {job['company'] or 'No informada'}\n"
        f"Ubicación: {job['location'] or 'No informada'}\nModalidad: {job['modality'] or 'No informada'}\n"
        f"Portal: {job['source']}\n\nDescripción:\n{desc}"
    )


def _pick_model(key: str) -> str:
    """Si el modelo configurado no existe, elige automáticamente un modelo 'flash' disponible."""
    r = requests.get(f"{API}/models", headers={"x-goog-api-key": key}, timeout=20)
    if r.status_code != 200:
        raise AIError(f"No pude listar modelos de Gemini ({r.status_code}): {r.text[:200]}")
    models = [
        m["name"].split("/", 1)[1] for m in r.json().get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    flash = [m for m in models if "flash" in m and "lite" not in m and "image" not in m and "tts" not in m]
    stable = [m for m in flash if "preview" not in m and "exp" not in m]
    choice = (stable or flash or models or [None])[-1]
    if not choice:
        raise AIError("No hay modelos de Gemini disponibles para esta clave.")
    return choice


def _generate(prompt: str, temperature: float = 0.4) -> dict:
    global _resolved_model
    key = gemini_key()
    if not key:
        raise AIError("Falta la clave de Gemini (configurala en la pestaña Configuración).")
    model = _resolved_model or load_config().get("ia", {}).get("modelo", "gemini-2.5-flash")
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    for attempt in range(2):
        r = requests.post(f"{API}/models/{model}:generateContent",
                          headers={"x-goog-api-key": key}, json=body, timeout=90)
        if r.status_code == 404 and attempt == 0:
            model = _pick_model(key)
            continue
        break
    if r.status_code == 429:
        raise AIRateLimit("Se alcanzó el límite gratuito de Gemini por ahora. Probá más tarde.")
    if r.status_code in (400, 401, 403):
        raise AIError(f"Gemini rechazó el pedido ({r.status_code}). Revisá la clave. {r.text[:200]}")
    if r.status_code != 200:
        raise AIError(f"Error de Gemini ({r.status_code}): {r.text[:200]}")
    _resolved_model = model
    data = r.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        raise AIError(f"Respuesta vacía de Gemini: {json.dumps(data)[:300]}")
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise AIError("Gemini no devolvió JSON válido.")


def analyze(job) -> dict:
    prompt = f"""{_candidate_context()}

{_job_context(job)}

TAREA: evaluá qué tan buena es esta oferta para ESTE candidato (busca primer empleo como Junior/Trainee,
vive en Zona Sur del GBA y puede ir a CABA). Sé honesto y concreto.

Devolvé SOLO este JSON:
{{
  "puntaje": <entero 0-100: probabilidad realista de que el candidato sea considerado y le convenga>,
  "veredicto": "postular" | "evaluar" | "descartar",
  "resumen": "<1-2 frases: qué es el puesto y qué haría>",
  "seniority_real": "trainee" | "junior" | "semi senior" | "senior" | "no claro",
  "modalidad": "<presencial/híbrido/remoto + lugar, si se infiere>",
  "a_favor": ["<coincidencias reales entre el aviso y el CV>"],
  "en_contra": ["<lo que juega en contra>"],
  "requisitos_faltantes": ["<requisitos del aviso que NO están en el CV; marcá (excluyente) si el aviso lo dice>"],
  "consejo": "<1-2 frases: qué destacar o qué hacer antes de postular>"
}}"""
    result = _generate(prompt, temperature=0.2)
    try:
        result["puntaje"] = max(0, min(100, int(result.get("puntaje", 0))))
    except (TypeError, ValueError):
        result["puntaje"] = None
    result["modelo"] = _resolved_model
    return result


def write_letter(job) -> dict:
    prompt = f"""{_candidate_context()}

{_job_context(job)}

TAREA: redactá los textos de postulación para este aviso, personalizados con lo que pide el aviso y
lo que REALMENTE tiene el CV.

- "carta": carta de presentación de 150 a 230 palabras. Saludo al equipo de selección de la empresa
  (o "Estimado equipo de selección" si es confidencial). Mencioná el puesto. Conectá 2-3 requisitos del
  aviso con proyectos/formación concretos del CV. Cerrá con disponibilidad, GitHub y LinkedIn, y firma
  con nombre, email y teléfono. Sin frases vacías ni clichés.
- "mensaje_recruiter": mensaje para LinkedIn de máximo 280 caracteres, cordial y directo.
- "preguntas_probables": 3 preguntas que probablemente hagan en la entrevista para ESTE puesto, con una
  respuesta sugerida honesta basada en el CV.

Devolvé SOLO este JSON:
{{"carta": "...", "mensaje_recruiter": "...", "preguntas_probables": [{{"pregunta": "...", "respuesta": "..."}}]}}"""
    return _generate(prompt, temperature=0.6)


def template_letter(job, matched_stack: list) -> dict:
    """Carta sin IA: plantilla basada sólo en datos del CV y en el stack que coincide con el aviso."""
    cfg = load_config()
    nombre = cfg.get("candidato", {}).get("nombre", "")
    empresa = job["company"] if job["company"] and job["company"] != "Confidencial" else None
    saludo = f"Estimado equipo de selección de {empresa}:" if empresa else "Estimado equipo de selección:"
    stack = ", ".join(matched_stack[:5]) if matched_stack else "JavaScript (Node.js, React), Python y SQL"
    carta = f"""{saludo}

Me interesa postularme a la posición de {job['title']}.

Soy estudiante avanzado de la Tecnicatura Superior en Desarrollo de Software (IFTS N.° 29, CABA) y busco mi primer empleo en IT. En mi formación trabajé con {stack}, entre otras tecnologías.

Entre mis proyectos se destacan una aplicación web Full Stack (Node.js, Express y SQL) con API REST, validaciones en backend y control de versiones en GitHub, y una plataforma en Python/Django con autenticación de usuarios y paneles de control. También cuento con certificación AWS Cloud Security & Fundamentals y estoy cursando el Cloud Engineer Track de Google Cloud.

Vivo en Zona Sur con fácil acceso a CABA, tengo disponibilidad inmediata e inglés intermedio (B2). Pueden ver mi código en github.com/saos1739 y mi perfil en linkedin.com/in/rojasantiagoa.

Muchas gracias por su tiempo.

{nombre}
santiirojas2000@gmail.com | +54 9 11 3120-1154"""
    mensaje = (f"Hola, ¿cómo estás? Me postulé a {job['title']}"
               f"{' en ' + empresa if empresa else ''}. Soy estudiante de la Tecnicatura en Desarrollo de "
               f"Software (IFTS 29) con proyectos en {stack}. Mi GitHub: github.com/saos1739. ¡Gracias!")
    return {"carta": carta, "mensaje_recruiter": mensaje[:300], "preguntas_probables": []}
