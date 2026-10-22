"""Clase base para las fuentes."""

from ..util import fingerprint


class Source:
    name = "base"
    label = "Base"
    needs_detail = False  # True si el listado no trae la descripción completa

    def __init__(self, cfg: dict, log):
        self.cfg = cfg
        self.log = log
        self.keywords = cfg["busqueda"]["palabras_clave"]
        self.pages = max(1, int(cfg["busqueda"].get("paginas_por_palabra", 1)))

    def search(self):
        """Generador de ofertas (dict)."""
        raise NotImplementedError

    def fetch_detail(self, job: dict) -> dict:
        """Completa descripción/extra de una oferta. Devuelve el job actualizado."""
        return job

    def make_job(self, external_id, title, company="", location="", url="", description="",
                 modality="", published_at=None, salary=None, extra=None, uid_prefix=None) -> dict:
        company = company or ""
        return {
            "uid": f"{uid_prefix or self.name}:{external_id}",
            "source": self.label,
            "title": (title or "").strip(),
            "company": company.strip(),
            "location": (location or "").strip(),
            "url": url,
            "description": description or "",
            "modality": modality or "",
            "published_at": published_at,
            "salary": salary,
            "extra": extra or {},
            "fingerprint": fingerprint(title or "", company),
        }
