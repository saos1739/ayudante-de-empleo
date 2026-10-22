"""Bumeran y Zonajobs (grupo Navent): comparten la API interna que usa su propio sitio web."""

from datetime import datetime

from ..util import clean, html_to_text, http_post, norm, pause
from .base import Source

# Consultas cortas efectivas para la API searchV2 de Bumeran / Zonajobs (frases largas devuelven 0)
NAVENT_QUERIES = [
    "desarrollador",
    "programador",
    "junior",
    "trainee",
    "pasante sistemas",
    "python",
    "react",
    "node",
    "javascript",
    "full stack",
]


class _Navent(Source):
    site_id = ""
    base_url = ""

    def search(self):
        headers = {
            "x-site-id": self.site_id,
            "Content-Type": "application/json",
            "Referer": self.base_url + "/",
            "Origin": self.base_url,
        }
        seen = set()
        for kw in NAVENT_QUERIES:
            for page in range(self.pages):
                try:
                    r = http_post(
                        f"{self.base_url}/api/avisos/searchV2",
                        params={"pageSize": 25, "page": page, "sort": "RECIENTES"},
                        json={"filtros": [], "query": kw},
                        headers=headers,
                    )
                    r.raise_for_status()
                    data = r.json()
                except Exception as e:
                    self.log(f"{self.label} ('{kw}'): {e}")
                    break
                for item in data.get("content", []):
                    jid = item.get("id")
                    if not jid or jid in seen:
                        continue
                    # Filtrar solo área Tecnología/Sistemas (idArea=19) o títulos claramente IT
                    t_norm = norm(item.get("titulo") or "")
                    if item.get("idArea") != 19 and not any(
                        w in t_norm for w in ("desarroll", "program", "software", "sistemas", "python", "react", "node", "web", "datos", "data", "it ", "informatic", "fullstack", "full stack")
                    ):
                        continue
                    seen.add(jid)
                    yield self._parse(item)
                pause(self.cfg)
                total = data.get("total", 0)
                if (page + 1) * 25 >= total:
                    break

    def _parse(self, item: dict) -> dict:
        published = None
        raw = item.get("fechaHoraPublicacion") or item.get("fechaPublicacion")
        for fmt in ("%d-%m-%Y %H:%M:%S", "%d-%m-%Y"):
            try:
                published = datetime.strptime(raw, fmt).date().isoformat()
                break
            except (TypeError, ValueError):
                continue
        company = "Confidencial" if item.get("confidencial") else clean(item.get("empresa"))
        portal = (item.get("portal") or "").lower()
        label = "Zonajobs" if portal == "zonajobs" else "Bumeran" if portal == "bumeran" else self.label
        job = self.make_job(
            # Mismo ID en ambos portales: el prefijo común evita duplicados.
            external_id=item["id"],
            uid_prefix="navent",
            title=clean(item.get("titulo")),
            company=company,
            location=clean(item.get("localizacion")),
            modality=clean(item.get("modalidadTrabajo")),
            url=f"{self.base_url}/empleos/{item['id']}.html",
            description=html_to_text(item.get("detalle")),
            published_at=published,
            extra={
                "tipo_trabajo": item.get("tipoTrabajo"),
                "vacantes": item.get("cantidadVacantes"),
                "postulacion_rapida": item.get("postulacionRapida"),
                "tiene_preguntas": item.get("tienePreguntas"),
            },
        )
        job["source"] = label
        return job


class Bumeran(_Navent):
    name = "bumeran"
    label = "Bumeran"
    site_id = "BMAR"
    base_url = "https://www.bumeran.com.ar"


class Zonajobs(_Navent):
    name = "zonajobs"
    label = "Zonajobs"
    site_id = "ZJAR"
    base_url = "https://www.zonajobs.com.ar"
