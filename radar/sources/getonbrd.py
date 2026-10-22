"""Get on Board: API pública oficial (https://www.getonbrd.com/api/v0)."""

import json
from datetime import datetime

from ..util import html_to_text, http_get, pause
from .base import Source

API = "https://www.getonbrd.com/api/v0"
MODALIDAD = {
    "fully_remote": "Remoto",
    "remote_local": "Remoto (local)",
    "hybrid": "Híbrido",
    "no_remote": "Presencial",
}
SENIORITY = {1: "Sin experiencia", 2: "Junior", 3: "Semi Senior", 4: "Senior", 5: "Expert"}


class GetOnBoard(Source):
    name = "getonbrd"
    label = "Get on Board"

    def search(self):
        b = self.cfg["busqueda"]
        seen_ids = set()

        # 1. Búsqueda específica con términos Junior / Trainee
        search_terms = ["junior", "trainee", "developer junior", "desarrollador junior"]
        for term in search_terms:
            for page in range(1, 3):
                try:
                    r = http_get(f"{API}/search/jobs",
                                 params={"query": term, "per_page": 50, "page": page,
                                         "expand": json.dumps(["company"])})
                    if r.status_code != 200:
                        break
                    data = r.json()
                    for item in data.get("data", []):
                        jid = item.get("id")
                        if jid and jid not in seen_ids:
                            seen_ids.add(jid)
                            job = self._parse(item)
                            if job:
                                yield job
                    if page >= data.get("meta", {}).get("total_pages", 1):
                        break
                    pause(self.cfg)
                except Exception as e:
                    self.log(f"Get on Board search '{term}': {e}")
                    break

        # 2. Categoría programación (solo si es Junior o Sin Experiencia)
        for cat in b.get("getonbrd_categorias", ["programming"]):
            for page in range(1, int(b.get("getonbrd_paginas", 2)) + 1):
                try:
                    r = http_get(f"{API}/categories/{cat}/jobs",
                                 params={"per_page": 50, "page": page,
                                         "expand": json.dumps(["company"])})
                    if r.status_code != 200:
                        break
                    data = r.json()
                    for item in data.get("data", []):
                        jid = item.get("id")
                        if jid and jid not in seen_ids:
                            seen_ids.add(jid)
                            job = self._parse(item)
                            if job:
                                yield job
                    if page >= data.get("meta", {}).get("total_pages", 1):
                        break
                    pause(self.cfg)
                except Exception as e:
                    self.log(f"Get on Board category '{cat}': {e}")
                    break

    def _parse(self, item: dict):
        a = item.get("attributes", {})
        sen_id = int(a.get("seniority", {}).get("data", {}).get("id") or 0) or None
        # Descartar de antemano si el portal lo categoriza como Semi Senior, Senior o Expert
        if sen_id in (3, 4, 5):
            return None

        countries = a.get("countries") or []
        # Exigir estrictamente que Argentina esté en la lista de países del aviso
        if "Argentina" not in countries:
            return None

        try:
            company = a["company"]["data"]["attributes"]["name"]
        except (KeyError, TypeError):
            company = ""
        countries = a.get("countries") or []
        rm = a.get("remote_modality")
        parts = [
            a.get("description_headline") and f"{a['description_headline']}",
            html_to_text(a.get("description")),
            a.get("functions_headline") and f"\n{a['functions_headline']}",
            html_to_text(a.get("functions")),
            a.get("desirable_headline") and f"\n{a['desirable_headline']}",
            html_to_text(a.get("desirable")),
            a.get("benefits_headline") and f"\n{a['benefits_headline']}",
            html_to_text(a.get("benefits")),
        ]
        salary = None
        if a.get("min_salary") or a.get("max_salary"):
            salary = f"USD {a.get('min_salary') or '?'} – {a.get('max_salary') or '?'} / mes"
        published = None
        if a.get("published_at"):
            published = datetime.fromtimestamp(a["published_at"]).date().isoformat()
        return self.make_job(
            external_id=item["id"],
            title=a.get("title"),
            company=company,
            location=", ".join(countries),
            modality=MODALIDAD.get(rm, rm or ""),
            url=item.get("links", {}).get("public_url", ""),
            description="\n".join(p for p in parts if p),
            published_at=published,
            salary=salary,
            extra={
                "seniority_id": sen_id,
                "nivel": SENIORITY.get(sen_id),
                "countries": countries,
                "remote_modality": rm,
                "postulantes": a.get("applications_count"),
            },
        )
