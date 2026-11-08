"""Fuentes de ofertas de mentira para probar el runner y la corrida en CI sin tocar internet."""

from radar.util import fingerprint

DESC = "Perfil junior con JavaScript y React. "


def oferta(uid, titulo="Desarrollador Full Stack Jr", empresa="ACME"):
    return {"uid": uid, "source": "falsa", "title": titulo, "company": empresa, "location": "CABA",
            "modality": "Híbrido", "url": f"https://example.com/{uid}", "description": DESC, "salary": None,
            "published_at": None, "fingerprint": fingerprint(titulo, empresa), "extra": {}}


def fuente(nombre, ofertas=(), falla=None, necesita_detalle=False):
    """Clase de fuente de mentira. Anota en `Fuente.detalles` cuántas veces se pidió el detalle."""

    class Fuente:
        name = nombre
        label = nombre.capitalize()
        needs_detail = necesita_detalle
        detalles = 0

        def __init__(self, cfg, log):
            pass

        def search(self):
            if falla:
                raise RuntimeError(falla)
            yield from ofertas

        def fetch_detail(self, job):
            Fuente.detalles += 1
            return job

    return Fuente
