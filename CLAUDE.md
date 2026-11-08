# Radar de Empleo

Panel local en Python que rastrea ofertas IT junior en portales argentinos, las filtra y puntúa contra mi perfil, las analiza con Gemini y me manda un resumen diario. Es un proyecto de portfolio: lo van a leer personas que me pueden contratar, así que la claridad del código importa más que las features extra.

## Stack

Python 3.12 · Flask + Jinja2 · SQLite · requests + BeautifulSoup · API REST de Gemini · Gmail SMTP

## Estructura

- `radar/sources/`: una clase por portal; todas heredan de `radar/sources/base.py`
- `radar/scoring.py`: filtro y puntaje por reglas
- `radar/ai.py`: análisis de ofertas y cartas con Gemini
- `radar/notify.py`: resumen por mail (en la v2 pasa a `radar/notifiers/`)
- `radar/runner.py`: orquesta la búsqueda en todas las fuentes
- `radar/web.py`, `radar/templates/`, `radar/static/`: panel Flask en http://127.0.0.1:5050
- `config.json`: palabras clave, filtros, IA y notificaciones
- `perfil/cv.md`: única fuente de verdad sobre mí para la IA

## Comandos

```
python -m radar panel        # abre el panel web
python -m radar buscar       # una búsqueda
python -m radar resumen      # busca y manda el resumen (--forzar para reenviar)
python -m radar probar-mail  # mail de prueba
python -m radar recalcular   # recalcula puntajes
python -m pytest             # tests (desde la Fase 0 de la v2)
ruff check .                 # lint (desde la Fase 0 de la v2)
```

## Trabajo en curso: v2

La especificación y el progreso están en `docs/specs/radar-v2.md`. Leela antes de cualquier tarea de la v2 y, cuando termines una fase, marcala en el checklist de ese archivo.

## Reglas

- Código, textos, config y commits en español. Respetá la arquitectura y el estilo existentes.
- Antes de escribir código de una fase, mostrame un plan corto (archivos que tocás y por qué) y esperá mi OK.
- Una fase por sesión, con commits chicos: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
- Tests junto con cada cambio; corré pytest antes de cada commit. Ningún test hace pedidos reales a internet.
- Nunca escribas claves, mi teléfono ni mi mail en archivos versionados. Los secretos van solo en `.env` (local) o en GitHub Secrets.
- No borres archivos, no hagas `git push --force` ni reescribas el historial sin preguntarme.
- La herramienta no postula sola ni inicia sesión en ningún portal.
- Si una API externa (CallMeBot, Gemini, un portal) no se comporta como dice la spec, frená y avisame en lugar de improvisar.
- Al cerrar una fase, decime qué cambió, cómo lo pruebo yo y qué tengo que configurar.
- Trabajo en Windows: usá comandos compatibles con PowerShell.
