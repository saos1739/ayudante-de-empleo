"""Empleos IT Argentina (https://www.empleosit.com.ar): portal especializado en IT."""

import re
from datetime import datetime

from bs4 import BeautifulSoup

from ..util import clean, http_get, pause
from .base import Source

BASE_URL = "https://www.empleosit.com.ar"
SEARCH_URL = f"{BASE_URL}/search-results-jobs/"


class EmpleosIT(Source):
    name = "empleosit"
    label = "Empleos IT"
    needs_detail = True

    def search(self):
        seen_ids = set()
        for kw in self.keywords:
            for page in range(1, self.pages + 1):
                params = {
                    "action": "search",
                    "listing_type[equal]": "Job",
                    "keywords[like]": kw,
                }
                if page > 1:
                    params["page"] = page

                try:
                    r = http_get(SEARCH_URL, params=params)
                    if r.status_code != 200:
                        break
                    soup = BeautifulSoup(r.text, "html.parser")
                    listings = soup.select("div.listingsection, div.listing-section")
                    if not listings:
                        break

                    found_on_page = 0
                    for item in listings:
                        job = self._parse_item(item)
                        if job and job["uid"] not in seen_ids:
                            seen_ids.add(job["uid"])
                            found_on_page += 1
                            yield job

                    pause(self.cfg)
                    if found_on_page == 0 or len(listings) < 10:
                        break
                except Exception as e:
                    self.log(f"Empleos IT ('{kw}'): {e}")
                    break

    def _parse_item(self, item) -> dict | None:
        title_el = item.select_one("div.listing-title a[href*='/display-job/']")
        if not title_el:
            return None

        url = title_el.get("href", "")
        if url.startswith("/"):
            url = BASE_URL + url
        url = url.split("?")[0]  # Limpiar query params de sesión/búsqueda

        # Extraer ID numérico de la URL: /display-job/130689/...
        m_id = re.search(r"/display-job/(\d+)/", url)
        ext_id = m_id.group(1) if m_id else url

        comp_el = item.select_one("span.company-ico")
        loc_el = item.select_one("span.location-ico")
        date_el = item.select_one("span.posted-ico")

        published_at = None
        if date_el:
            dt_txt = clean(date_el.get_text())
            # Formato típico: 21/10/2026
            try:
                published_at = datetime.strptime(dt_txt, "%d/%m/%Y").date().isoformat()
            except Exception:
                pass

        return self.make_job(
            external_id=ext_id,
            title=clean(title_el.get_text()),
            company=clean(comp_el.get_text()) if comp_el else "",
            location=clean(loc_el.get_text()) if loc_el else "Argentina",
            url=url,
            published_at=published_at,
        )

    def fetch_detail(self, job: dict) -> dict:
        try:
            r = http_get(job["url"])
            if r.status_code != 200:
                return job
            soup = BeautifulSoup(r.text, "html.parser")

            # La descripción está en div.displayField inmediatamente después del h2 "Descripción del empleo:"
            desc_el = None
            for h2 in soup.select("h2"):
                if "descripci" in h2.get_text().lower():
                    cand = h2.find_next_sibling()
                    if cand and cand.name == "div":
                        desc_el = cand
                        break

            if not desc_el:
                desc_el = soup.select_one("div.displayField")

            if desc_el:
                for tag in desc_el.select("script, style"):
                    tag.decompose()
                job["description"] = clean(desc_el.get_text("\n", strip=True))

            # Modalidad y localización en la barra de campos
            text_full = soup.get_text(" ", strip=True)
            for mod in ("remoto", "hibrido", "presencial"):
                if mod in text_full.lower():
                    job["modality"] = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial"}[mod]
                    break
        except Exception as e:
            self.log(f"Empleos IT detalle ({job.get('url')}): {e}")

        return job
