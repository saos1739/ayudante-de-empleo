#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestor Automatizado de Postulaciones y Propuestas
Candidato: Santiago Agustín Rojas Casas
"""

import os
import re
import argparse
from datetime import datetime

PERFIL_CANDIDATO = {
    "nombre": "Santiago Agustín Rojas Casas",
    "email": "santiirojas2000@gmail.com",
    "telefono": "+54 9 11 3120-1154",
    "linkedin": "https://www.linkedin.com/in/rojasantiagoa",
    "github": "https://github.com/saos1739",
    "estudios": "Tecnicatura Superior en Desarrollo de Software (IFTS N.° 29, CABA)",
    "skills": ["JavaScript", "Node.js", "Express", "React", "Python", "Django", "SQL", "MySQL", "PostgreSQL", "AWS", "Google Cloud", "Git", "REST API", "Clean Code"],
    "ingles": "B2 (Intermedio Técnico y Profesional)"
}

KEYWORDS_MATCH = {
    "node": 15, "node.js": 15, "express": 10, "react": 15, "javascript": 10,
    "python": 15, "django": 10, "sql": 10, "mysql": 5, "postgres": 5, "postgresql": 5,
    "git": 5, "github": 5, "aws": 10, "gcp": 5, "cloud": 5, "rest": 10, "api": 10,
    "junior": 15, "trainee": 20, "entry level": 15, "sin experiencia": 20
}

def calcular_score_match(texto_vacante):
    texto = texto_vacante.lower()
    score = 40  # base score
    for kw, val in KEYWORDS_MATCH.items():
        if re.search(r'\b' + re.escape(kw) + r'\b', texto):
            score += val
    return min(score, 100)

def crear_propuesta(empresa, puesto, plataforma, modalidad, descripcion, link=""):
    score = calcular_score_match(f"{puesto} {descripcion}")
    fecha = datetime.now().strftime("%Y-%m-%d")
    
    os.makedirs("postulaciones", exist_ok=True)
    slug = re.sub(r'[^a-zA-Z0-9]', '_', empresa.lower())
    timestamp = datetime.now().strftime("%m%d_%H%M")
    nombre_archivo = f"postulaciones/propuesta_{slug}_{timestamp}.md"
    
    contenido_propuesta = f"""# Propuesta de Postulación: {puesto} en {empresa}

- **Fecha:** {fecha}
- **Plataforma:** {plataforma}
- **Modalidad / Ubicación:** {modalidad}
- **Enlace de la Oferta:** {link or 'N/A'}
- **Score de Compatibilidad (Match):** {score}%

---

## 1. Carta de Presentación Personalizada

Estimado equipo de selección de **{empresa}**,

Les escribo con gran entusiasmo para postularme a la posición de **{puesto}**.

Actualmente curso la Tecnicatura Superior en Desarrollo de Software en el IFTS N.° 29 (CABA) y me especializo en desarrollo Full Stack con **JavaScript (Node.js, Express, React)** y **Python (Django, APIs REST)**, junto con persistencia de datos relacionales en **SQL** y certificaciones oficiales en Cloud Computing (**AWS y Google Cloud**).

He revisado los requerimientos de la posición y considero que mi perfil se alinea fuertemente con la vacante:
- **Desarrollo Backend y APIs:** Experiencia práctica diseñando e implementando endpoints RESTful optimizados, validaciones en backend y conexión eficiente a bases de datos.
- **Frontend Responsivo:** Creación de interfaces de usuario dinámicas con React y buenas prácticas de componentización y diseño adaptativo.
- **Flujo de Trabajo Profesional:** Manejo ágil de repositorios y control de versiones con Git/GitHub, Clean Code y metodologías Scrum/Kanban.

Tengo plena disponibilidad para modalidad {modalidad}, nivel de inglés B2 para interactuar con documentación o equipos distribuidos, y una alta motivación para aprender sus procesos y aportar proactividad al equipo técnico de {empresa}.

Pueden revisar mi código y proyectos destacados en mi perfil de GitHub: **https://github.com/saos1739** y contactarme a través de **{PERFIL_CANDIDATO['email']}** o al **{PERFIL_CANDIDATO['telefono']}**.

Agradezco mucho su tiempo y consideración.

Atentamente,  
**{PERFIL_CANDIDATO['nombre']}**  
[LinkedIn: rojasantiagoa]({PERFIL_CANDIDATO['linkedin']}) | [GitHub: saos1739]({PERFIL_CANDIDATO['github']})

---

## 2. Mensaje Directo para Recruiter / Contacto en LinkedIn (Pitch Corto)

```text
Hola, un gusto saludarte. Vi la vacante de {puesto} en {empresa} y me interesó mucho. Soy Desarrollador Junior especializado en Node.js, React, Python y Cloud (AWS/GCP), estudiante del IFTS 29. Me postulé a la vacante y te comparto mi GitHub (github.com/saos1739). ¡Muchas gracias por tu tiempo y que tengas buen día!
```

---

## 3. Pasos para Concretar la Postulación
1. [ ] Verificar que el CV en PDF tenga los enlaces funcionales a tus repositorios.
2. [ ] Ingresar a la plataforma ({plataforma}) y cargar la carta de presentación adaptada.
3. [ ] Adjuntar el CV actualizado en formato PDF.
4. [ ] Buscar en LinkedIn al recruiter o responsable de RRHH / Líder Técnico de **{empresa}** y enviarle el mensaje corto de contacto.
5. [ ] Marcar como `Postulado` en `tracking_postulaciones.md`.
"""
    
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        f.write(contenido_propuesta)
    
    # Registrar en tracking
    registrar_en_tracking(fecha, empresa, puesto, plataforma, modalidad, score, nombre_archivo)
    
    print(f"\n[OK] Propuesta generada con éxito: {nombre_archivo}")
    print(f"[OK] Score de compatibilidad estimado: {score}%")
    print(f"[OK] Registrado en tracking_postulaciones.md\n")

def registrar_en_tracking(fecha, empresa, puesto, plataforma, modalidad, score, archivo_propuesta):
    tracker_file = "tracking_postulaciones.md"
    if not os.path.exists(tracker_file):
        return
    
    with open(tracker_file, "r", encoding="utf-8") as f:
        contenido = f.read()
    
    # Contar postulaciones existentes
    ids_existentes = re.findall(r'\| #(\d{3}) \|', contenido)
    siguiente_num = 1
    if ids_existentes:
        siguiente_num = max(int(n) for n in ids_existentes) + 1
    id_str = f"#{siguiente_num:03d}"
    
    nueva_fila = f"| {id_str} | {fecha} | {empresa} | {puesto} | {plataforma} | {modalidad} | {score}% | Propuesta Lista | `{archivo_propuesta}` | Enviar postulación |\n"
    
    tabla_sep = "| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    if tabla_sep in contenido:
        partes = contenido.split(tabla_sep)
        contenido = partes[0] + tabla_sep + "\n" + nueva_fila + partes[1].lstrip("\n")
    else:
        contenido += "\n" + nueva_fila
        
    with open(tracker_file, "w", encoding="utf-8") as f:
        f.write(contenido)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador y Administrador de Postulaciones")
    parser.add_argument("--empresa", required=True, help="Nombre de la empresa")
    parser.add_argument("--puesto", required=True, help="Título del puesto (ej. Desarrollador Junior Node/React)")
    parser.add_argument("--plataforma", default="LinkedIn", help="Plataforma de empleo")
    parser.add_argument("--modalidad", default="Híbrido (CABA)", help="Modalidad y ubicación")
    parser.add_argument("--desc", default="", help="Descripción de la vacante o tecnologías pedidas")
    parser.add_argument("--link", default="", help="Enlace a la oferta de trabajo")
    
    args = parser.parse_args()
    crear_propuesta(args.empresa, args.puesto, args.plataforma, args.modalidad, args.desc, args.link)
