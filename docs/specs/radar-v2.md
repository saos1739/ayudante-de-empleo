# Radar de Empleo v2: especificación

## Progreso

- [ ] Fase 0: repo presentable y sin datos personales
- [ ] Fase 1: filtros alineados con mi perfil
- [ ] Fase 2: avisos por WhatsApp
- [ ] Fase 3: ejecución diaria en GitHub Actions
- [ ] Fase 4: tests, CI y README

## Objetivo

1. Recibir las ofertas nuevas que encajan con mi perfil por **WhatsApp**, además del mail.
2. Que funcione **aunque mi PC esté apagada**, corriendo una vez por día en GitHub Actions.
3. Filtros alineados con mi perfil actual (ver abajo).
4. Repo listo para mostrar: sin datos personales, con dependencias declaradas, tests y CI.

**Fuera de alcance:** postular automáticamente, iniciar sesión en cualquier portal, sumar fuentes de empleo nuevas, rehacer el panel web.

## Mi perfil (fuente de verdad)

Usá estos datos para actualizar `perfil/cv.md` y las listas de stack del scoring. No agregues nada que no esté acá. Mis datos de contacto los cargo yo en mi copia local.

- **Situación:** estoy terminando la Tecnicatura en Desarrollo de Software (IFTS N.º 29) y busco mi primer trabajo en IT.
- **Ubicación:** Buenos Aires, zona sur; viajo sin problema a CABA.
- **Busco:** full time (preferido); presencial o híbrido en CABA / GBA Sur, o remoto.
- **Inglés:** B2 (intermedio-alto).
- **Experiencia laboral formal en IT:** ninguna todavía (primer empleo).
- **Puestos objetivo, en orden de prioridad:**
  1. Desarrollador Full Stack / Frontend / Backend Jr o Trainee (JavaScript/TypeScript, React, React Native, Node.js, Python)
  2. Analista de Datos Jr / BI Jr (Python, Pandas, SQL)
  3. Cloud Jr (Google Cloud, AWS)
- **Stack:** JavaScript, TypeScript, React, React Native (Expo), Astro, Node.js, Express, Python, Django, Flask, SQL (MySQL, PostgreSQL, SQLite), Pandas, scikit-learn, Jupyter, Google Cloud, AWS, Git/GitHub, Postman, Figma, n8n, Salesforce, C# (básico).
- **Formación:** Tecnicatura en Desarrollo de Software, IFTS N.º 29 (en curso).
- **Certificaciones y cursos:**
  - Google Cloud, ruta Cloud Engineer (en curso, termina el 25/11/2026); Google Cloud Computing Foundations + 4 skill badges
  - AWS Academy Cloud Foundations
  - Data Analytics y Machine Learning con Python, Talento Tech (2025)
  - Business Intelligence, Talento Tech (2025)
  - Desarrollador en Plataforma Salesforce, Talento Tech (2024); rango Mountaineer en Trailhead
  - Full Stack Python y Full Stack JavaScript/Node.js, Codo a Codo (2023)
  - Desarrollo Web, Coderhouse (2022); #SeProgramar, Argentina Programa (2022)
- **Proyectos:**
  - Radar de Empleo (este repo).
  - Rodando X MZA: app móvil para que usuarios de silla de ruedas en Mendoza planifiquen rutas accesibles y reporten obstáculos. Hago el frontend mobile con Expo y React Native (trabajo en equipo, repo privado).
  - Análisis de datos con Python: proyecto final de Data Analytics en Jupyter con Pandas y visualizaciones.
  - Innova Lab (Agencia de Habilidades para el Futuro, GCBA): Frontend Developer en el equipo que desarrolló una app educativa de matemáticas.
  - App web CRUD con Node.js + Express + SQL, y plataforma web con Django.

---

## Fase 0: repo presentable y sin datos personales

- Crear `requirements.txt` con lo que el código realmente importa (revisá los imports) y `requirements-dev.txt` con `pytest` y `ruff`.
- Hoy hay archivos versionados con mi teléfono y mis postulaciones reales: `perfil/cv.md`, `postulaciones/`, `tracking_postulaciones.md`, `plantillas/`, `scripts/gestor_postulaciones.py` y el texto de firma al final de `radar/ai.py`.
  - Pasá esos datos a archivos ignorados por git y dejá versiones de ejemplo con datos ficticios (`perfil/cv.example.md`, `plantillas/*.example.md`, etc.).
  - El contacto que firma las cartas sale de variables de entorno (`CANDIDATO_TELEFONO`, `CANDIDATO_EMAIL`) o del cv local, nunca del código.
  - `config.json` no debe tener mi mail: el destinatario sale de `RADAR_DESTINATARIO` (si no existe, `GMAIL_USER`).
  - Usá `git rm --cached` para dejar de versionarlos sin borrarlos de mi disco. No reescribas el historial: al final decime qué datos siguen en el historial para que yo decida.
- Agregar `.env.example` con todas las variables, sin valores reales.

**Listo cuando:** buscar mi teléfono con `git grep` no devuelve nada en el árbol actual y la app arranca igual usando mis archivos locales.

## Fase 1: filtros alineados con mi perfil

- El scoring debe leer el stack propio y el stack ajeno desde `config.json` (por ejemplo `perfil.stack_core` y `perfil.stack_ajeno`) en lugar de constantes en `scoring.py`, para que actualizar mi perfil no requiera tocar código. Los valores actuales quedan como default.
- Cambios de reglas (cada uno con su test, en esta misma fase):
  1. **React Native:** sacarlo de `TITULO_STACK_AJENO` y sumarlo al stack propio, junto con TypeScript, Expo, Flask, Pandas y scikit-learn.
  2. **Puestos:** sumar palabras clave de búsqueda para Analista de Datos Jr / BI Jr y Cloud Jr (por ejemplo "analista de datos junior", "data analyst junior", "analista bi junior", "cloud junior", "cloud engineer junior", "devops junior"), además de las de Full Stack que ya existen.
  3. **Experiencia:** si el mínimo exigido es 0–1 año, normal; si es 2 años, **no excluir**: marcar como "aplicá igual" con una penalización; si es 3 años o más, excluir.
  4. **Remoto desde el exterior:** hoy se excluye cualquier país extranjero. Nueva regla: si es 100 % remoto y acepta Argentina, LATAM o "anywhere", se mantiene con una penalización leve; si es presencial/híbrido fuera del AMBA o exige residir en otro país, se excluye.
  5. **Inglés:** B2 alcanza para "intermedio", "intermedio-avanzado" y "upper intermediate". Se siguen excluyendo "avanzado", "fluido", "bilingüe", C1 y C2.
  6. **Jornada:** part time o freelance restan puntos pero no excluyen.
  7. **Regla de portfolio:** una oferta tiene que mencionar al menos una tecnología de mi stack core o encajar con uno de los 3 puestos objetivo; si no, se descarta. Verificá si la lógica actual ya lo cubre y completala si falta.
- Cada oferta guarda una etiqueta legible ("encaja" o "aplicá igual") y sus motivos, para mostrarlos en el mail y en WhatsApp.
- Actualizá el prompt de `radar/ai.py` para que evalúe contra los 3 puestos objetivo y respete la regla de "aplicá igual".

**Listo cuando:** hay tests con avisos de ejemplo que cubren las 7 reglas y pasan.

## Fase 2: avisos por WhatsApp

- Refactorizar `radar/notify.py` en un paquete `radar/notifiers/` con una interfaz común (por ejemplo `enviar(ofertas) -> resultado`) y dos implementaciones: `email.py` (lo actual) y `whatsapp.py`.
- WhatsApp vía **CallMeBot** (gratis para uso personal, solo manda a tu propio número, texto plano). Variables: `WHATSAPP_PHONE` y `CALLMEBOT_APIKEY`. Leé la documentación actual de CallMeBot antes de implementar (formato de la URL, límites y largo máximo del mensaje).
- Formato del mensaje: encabezado con fecha y cantidad; las 5 ofertas con mejor puntaje, cada una con puntaje, etiqueta, título, empresa, modalidad y link; cierre "+N más en tu mail". Si supera el largo máximo, partirlo en varios mensajes con una pausa entre envíos.
- Config: `notificaciones.canales: ["email", "whatsapp"]`. Si un canal falla, se loguea y se sigue con el otro. Una oferta queda marcada como avisada si llegó por al menos un canal.
- Comando nuevo: `python -m radar probar-whatsapp`.
- Dejá la interfaz lista para sumar otro proveedor más adelante (Twilio, Meta Cloud API), pero no lo implementes ahora.

**Listo cuando:** los tests con HTTP mockeado pasan y me llega el mensaje de prueba a WhatsApp.

## Fase 3: ejecución diaria en GitHub Actions

- Modo sin panel: `python -m radar resumen --ci` (no abre navegador; los links al panel local no se incluyen en los avisos).
- Workflow `.github/workflows/radar-diario.yml`:
  - Programado todos los días a las 8:17 hora Argentina (`17 11 * * *` en UTC). Evitá el minuto 0: GitHub demora más los jobs programados a la hora en punto. Sumá `workflow_dispatch` para correrlo a mano.
  - Python 3.12 con caché de pip; `concurrency` para que no se pisen dos corridas; `permissions: contents: write` solo para guardar el estado.
  - Secrets: `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `RADAR_DESTINATARIO`, `WHATSAPP_PHONE`, `CALLMEBOT_APIKEY` y `GEMINI_API_KEY` (opcional).
- **Estado entre corridas:** cada corrida de GitHub arranca vacía. Guardá solo hashes de las ofertas ya avisadas (sin títulos ni el estado de mis postulaciones) en `notificados.json`, en una rama huérfana `radar-state`. Borrá entradas de más de 45 días.
- **Fuentes en la nube:** LinkedIn y otros portales pueden bloquear IPs de servidores. Una fuente que falla se loguea y se saltea, nunca corta la corrida, y el resumen dice qué fuentes fallaron. Agregá `busqueda.fuentes_ci`, separada de `fuentes_activas`, con LinkedIn desactivado por defecto.
- La tarea programada de Windows sigue funcionando como alternativa local. Agregá `notificaciones.modo: "local" | "ci"` para no recibir avisos repetidos si se usan las dos.
- Documentá en el README que GitHub desactiva los workflows programados en repos públicos después de 60 días sin actividad, y cómo reactivarlos.

**Listo cuando:** una corrida manual del workflow manda mail y WhatsApp, y una segunda corrida no repite ofertas.

## Fase 4: tests, CI y README

- Completar `tests/` con `pytest`: reglas del scoring, formato de los mensajes, notifiers con SMTP/HTTP mockeados y limpieza del estado. Ningún test hace pedidos reales a internet.
- Workflow `.github/workflows/tests.yml` que corre `ruff` y `pytest` en cada push y PR, con su badge en el README.
- README:
  - Reemplazar la sección "¿Queda bien o mal tener este proyecto en GitHub?" por "Decisiones de diseño y uso responsable": no postula solo, no inicia sesión, respeta pausas entre pedidos, datos personales fuera del repo.
  - Arreglar el árbol de carpetas (dice `LABUBU/`), actualizar el diagrama mermaid con los notifiers y GitHub Actions, y sumar instalación, variables de entorno, uso local, uso en la nube y una sección corta "Stack y lo que aprendí".
  - Cambiar "Desarrollado para" por "Autor: Santiago Rojas", con links a LinkedIn y GitHub.
  - Opcional: un resumen de 3 líneas en inglés al principio.
- Tag `v2.0.0` con un `CHANGELOG.md` breve.
