"""LinkedIn: endpoints públicos para invitados (sin login, NO usa tu cuenta).

Se consultan con filtro de nivel 'Prácticas' y 'Sin experiencia' y publicaciones de la última semana.
LinkedIn limita la cantidad de pedidos: si responde 429 se corta la fuente hasta la próxima búsqueda.
"""

from bs4 import BeautifulSoup

from ..util import clean, http_get, pause
from .base import Source

LIST_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"


class RateLimited(Exception):
    pass


class LinkedIn(Source):
    name = "linkedin"
    label = "LinkedIn"
    needs_detail = True

    def __init__(self, cfg, log):
        super().__init__(cfg, log)
        self.blocked = False

    def search(self):
        location = self.cfg["busqueda"].get("linkedin_ubicacion", "Buenos Aires, Argentina")
        for kw in self.keywords:
            for page in range(self.pages):
                r = http_get(LIST_URL, params={
                    "keywords": kw, "location": location,
                    "f_E": "1,2",          # Prácticas + Sin experiencia
                    "f_TPR": "r604800",    # última semana
                    "start": page * 10,
                })
                if r.status_code == 429:
                    self.blocked = True
                    raise RateLimited("LinkedIn limitó los pedidos (429). Se reintenta en la próxima búsqueda.")
                if r.status_code != 200 or not r.text.strip():
                    break
                soup = BeautifulSoup(r.text, "html.parser")
                cards = soup.select("div.base-card")
                for card in cards:
                    job = self._parse(card)
                    if job:
                        yield job
                pause(self.cfg)
                if len(cards) < 10:
                    break

    def _parse(self, card):
        urn = card.get("data-entity-urn", "")
        jid = urn.split(":")[-1]
        if not jid:
            return None
        title = card.select_one("h3.base-search-card__title")
        company = card.select_one("h4.base-search-card__subtitle")
        loc = card.select_one("span.job-search-card__location")
        time_el = card.select_one("time")
        link = card.select_one("a.base-card__full-link")
        url = (link.get("href") if link else "") or f"https://www.linkedin.com/jobs/view/{jid}"
        return self.make_job(
            external_id=jid,
            title=clean(title.get_text()) if title else "",
            company=clean(company.get_text()) if company else "",
            location=clean(loc.get_text()) if loc else "",
            url=url.split("?")[0],
            published_at=time_el.get("datetime") if time_el else None,
        )

    def fetch_detail(self, job: dict) -> dict:
        if self.blocked:
            return job
        jid = job["uid"].split(":", 1)[1]
        r = http_get(DETAIL_URL.format(jid))
        if r.status_code == 429:
            self.blocked = True
            self.log("LinkedIn limitó los pedidos de detalle; el resto se puntúa solo por el título.")
            return job
        if r.status_code != 200:
            return job
        soup = BeautifulSoup(r.text, "html.parser")
        desc = soup.select_one("div.show-more-less-html__markup")
        if desc:
            job["description"] = desc.get_text("\n", strip=True)
        for li in soup.select("li.description__job-criteria-item"):
            h = li.select_one("h3")
            v = li.select_one("span")
            if not h or not v:
                continue
            key, val = clean(h.get_text()).lower(), clean(v.get_text())
            if "antigüedad" in key or "seniority" in key:
                job["extra"]["seniority_text"] = val
            elif "tipo de empleo" in key or "employment" in key:
                job["extra"]["tipo_empleo"] = val
        return job
