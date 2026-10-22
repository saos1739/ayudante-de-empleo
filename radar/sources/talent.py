"""Talent.com Argentina (https://ar.talent.com): agregador masivo de vacantes."""

import re
from datetime import datetime

from bs4 import BeautifulSoup

from ..util import clean, http_get, norm, pause, relative_date
from .base import Source

BASE_URL = "https://ar.talent.com"


class Talent(Source):
    name = "talent"
    label = "Talent.com"
    needs_detail = True

    def search(self):
        seen_ids = set()
        for kw in self.keywords:
            for page in range(1, self.pages + 1):
                params = {
                    "k": kw,
                    "l": "Buenos Aires, Argentina",
                }
                if page > 1:
                    params["p"] = page

                try:
                    r = http_get(f"{BASE_URL}/jobs", params=params)
                    if r.status_code != 200:
                        break
                    soup = BeautifulSoup(r.text, "html.parser")
                    cards = soup.select("[class*='JobCard_card__']")
                    if not cards:
                        break

                    found_on_page = 0
                    for card in cards:
                        job = self._parse_card(card)
                        if job and job["uid"] not in seen_ids:
                            seen_ids.add(job["uid"])
                            found_on_page += 1
                            yield job

                    pause(self.cfg)
                    if found_on_page == 0 or len(cards) < 10:
                        break
                except Exception as e:
                    self.log(f"Talent.com ('{kw}'): {e}")
                    break

    def _parse_card(self, card) -> dict | None:
        title_el = card.select_one("[class*='JobCard_title__']")
        link_el = card.select_one("a[href*='/view?id=']")
        if not title_el or not link_el:
            return None

        href = link_el.get("href", "")
        url = BASE_URL + href if href.startswith("/") else href

        m_id = re.search(r"id=([a-zA-Z0-9]+)", url)
        ext_id = m_id.group(1) if m_id else url

        comp_el = card.select_one("[class*='JobCard_company__']")
        loc_el = card.select_one("[class*='JobCard_location__']")
        date_el = card.select_one("[class*='JobCard_timeText__']")
        snip_el = card.select_one("[class*='JobCard_snippet__']")

        date_text = date_el.get_text(strip=True) if date_el else ""
        date_text = re.sub(r"^.*?actualizaci[oó]n:\s*", "", date_text, flags=re.IGNORECASE)

        return self.make_job(
            external_id=ext_id,
            title=clean(title_el.get_text()),
            company=clean(comp_el.get_text()) if comp_el else "",
            location=clean(loc_el.get_text()) if loc_el else "Buenos Aires, Argentina",
            url=url,
            description=clean(snip_el.get_text(" ", strip=True)) if snip_el else "",
            published_at=relative_date(date_text),
        )

    def fetch_detail(self, job: dict) -> dict:
        try:
            r = http_get(job["url"])
            if r.status_code != 200:
                return job
            soup = BeautifulSoup(r.text, "html.parser")
            desc_el = soup.select_one("div[class*='styles_jobDescriptionContainer'], div[class*='job__description']")
            if desc_el:
                for tag in desc_el.select("script, style"):
                    tag.decompose()
                job["description"] = clean(desc_el.get_text("\n", strip=True))

            text_low = norm(job.get("description", ""))
            for mod in ("remoto", "hibrido", "presencial"):
                if mod in text_low[:300]:
                    job["modality"] = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial"}[mod]
                    break
        except Exception as e:
            self.log(f"Talent.com detalle ({job.get('url')}): {e}")

        return job
