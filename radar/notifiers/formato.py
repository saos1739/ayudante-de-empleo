"""Datos de una oferta tal como se muestran en los avisos (comunes a todos los canales)."""

import json


def puntaje(job) -> int:
    return job["ai_score"] if job["ai_score"] is not None else job["rule_score"]


def etiqueta(job) -> str:
    """«encaja» o «aplicá igual»; vacía en ofertas guardadas antes de la v2 hasta que se recalculen."""
    return job["etiqueta"] or ""


def motivos(job, limit: int = 3) -> list:
    """Los mejores motivos a favor y, aparte, todas las advertencias (penalizaciones) marcadas con ⚠."""
    try:
        items = json.loads(job["rule_reasons"] or "[]")
    except ValueError:
        return []
    a_favor = [r["t"] for r in items if (r.get("p") or 0) > 0][:limit]
    advertencias = [f"⚠ {r['t']}" for r in items if (r.get("p") or 0) < 0]
    return a_favor + advertencias
