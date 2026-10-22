"""Computrabajo Argentina: lectura del listado HTML público + página de detalle."""

import re

from bs4 import BeautifulSoup

from ..util import clean, http_get, norm, pause, relative_date
from .base import Source

BASE = "https://ar.computrabajo.com"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(text)).strip("-")


class Computrabajo(Source):
    name = "computrabajo"
    label = "Computrabajo"
    needs_detail = True

    def search(self):
        for kw in self.keywords:
            for page in range(1, self.pages + 1):
                r = http_get(f"{BASE}/trabajo-de-{_slug(kw)}", params={"p": page} if page > 1 else None)
                if r.status_code == 404:
                    break
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                articles = soup.select("article.box_offer")
                for art in articles:
                    job = self._parse(art)
                    if job:
                        yield job
                pause(self.cfg)
                if len(articles) < 15:
                    break

    def _parse(self, art):
        link = art.select_one("h2 a")
        if not link:
            return None
        oid = art.get("data-id") or art.get("id")
        company_el = art.select_one("a[offer-grid-article-company-url]")
        ps = art.select("p.fs16")
        if company_el is None and ps:
            company_el = ps[0]
        company = clean(company_el.get_text()) if company_el else ""
        # Quitar puntaje de reseñas pegado al nombre (ej. "4,2 Empresa")
        company = re.sub(r"^\d[\d,\.]*\s*", "", company).strip()

        location = ""
        if len(ps) >= 2:
            loc_span = ps[-1].select_one("span.mr10") or ps[-1]
            location = clean(loc_span.get_text())
        elif ps:
            spans = ps[0].select("span.mr10")
            for sp in reversed(spans):
                txt = clean(sp.get_text())
                if txt and not re.match(r"^\d[\d,\.]*$", txt):
                    location = txt
                    break

        date_el = art.select_one("p.fs13")
        href = link.get("href", "").split("#")[0]
        return self.make_job(
            external_id=oid,
            title=clean(link.get_text()),
            company=company,
            location=location,
            url=BASE + href if href.startswith("/") else href,
            published_at=relative_date(date_el.get_text()) if date_el else None,
        )

    def fetch_detail(self, job: dict) -> dict:
        r = http_get(job["url"])
        if r.status_code != 200:
            return job
        soup = BeautifulSoup(r.text, "html.parser")
        # Si la ubicación quedó vacía o era un puntaje numérico, recuperarla del subtítulo del detalle
        if not job.get("location") or re.match(r"^\d[\d,\.]*$", job.get("location", "")):
            sub = soup.select_one("main h1 + p, div.container p.fs16")
            if sub:
                parts = [clean(p) for p in sub.get_text().split("-") if clean(p)]
                if parts:
                    job["location"] = parts[-1]
        box = soup.select_one("div[div-link='oferta']")
        if box:
            for tag in box.select("script, style, button"):
                tag.decompose()
            text = box.get_text("\n", strip=True)
            text = re.sub(r"^Descripción de la oferta\s*", "", text)
            # Recortar pie automático de Computrabajo ("Requerimientos / Educación mínima / X años...")
            text = re.split(r"\n(?:Requerimientos|Palabras clave|Postularme)\n", text)[0].strip()
            job["description"] = text
            m = re.search(r"\$\s?[\d\.\,]+(?:\s*-\s*\$\s?[\d\.\,]+)?", text)
            if m:
                job["salary"] = m.group(0)
            low = norm(text)
            for mod in ("remoto", "hibrido", "presencial"):
                if mod in low[:400]:
                    job["modality"] = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial"}[mod]
                    break
        return job
