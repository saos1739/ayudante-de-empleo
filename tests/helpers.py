"""Ayudas compartidas entre tests: ofertas de ejemplo y su guardado en la base temporal."""

from radar import db, scoring
from radar.config import load_config


def oferta(uid: str, descripcion: str = "", titulo: str = "Desarrollador Full Stack Jr") -> dict:
    return {"uid": uid, "source": "Prueba", "title": titulo, "company": "ACME", "location": "CABA",
            "modality": "Híbrido", "url": f"https://example.com/{uid}", "description": descripcion,
            "fingerprint": uid, "extra": {}}


def guardar(descripcion: str = "", uid: str = "a", titulo: str = "Desarrollador Full Stack Jr") -> int:
    """Evalúa la oferta con las reglas reales y la guarda; devuelve su id."""
    job = oferta(uid, descripcion, titulo)
    return db.insert_job(job, scoring.evaluate(job, load_config()))
