"""Funciones auxiliares: normalización de texto, HTTP y fechas."""

import html
import re
import time
import unicodedata
from datetime import datetime, timedelta

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

_session = requests.Session()
_session.headers.update(HEADERS)


def http_get(url, **kwargs):
    kwargs.setdefault("timeout", 25)
    return _session.get(url, **kwargs)


def http_post(url, **kwargs):
    kwargs.setdefault("timeout", 25)
    return _session.post(url, **kwargs)


def pause(cfg: dict) -> None:
    time.sleep(float(cfg.get("busqueda", {}).get("pausa_entre_pedidos_seg", 1.0)))


def norm(text: str) -> str:
    """Minúsculas y sin acentos, para comparar palabras clave."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", raw)
    raw = re.sub(r"(?i)<li[^>]*>", "• ", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
    raw = re.sub(r"\n\s*\n+", "\n\n", raw)
    return raw.strip()


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def relative_date(text: str) -> str | None:
    """Convierte 'Hace 3 días', 'Ayer', 'Hace 5 horas' a fecha ISO (aproximada)."""
    t = norm(text)
    now = datetime.now()
    if not t:
        return None
    if "hoy" in t or "hora" in t or "minuto" in t:
        return now.date().isoformat()
    if "ayer" in t:
        return (now - timedelta(days=1)).date().isoformat()
    m = re.search(r"(\d+)\s*(dia|semana|mes)", t)
    if m:
        n = int(m.group(1))
        days = {"dia": 1, "semana": 7, "mes": 30}[m.group(2)] * n
        return (now - timedelta(days=days)).date().isoformat()
    m = re.search(r"\b(un|una)\s*(dia|semana|mes)", t)
    if m:
        days = {"dia": 1, "semana": 7, "mes": 30}[m.group(2)]
        return (now - timedelta(days=days)).date().isoformat()
    return None


def fingerprint(title: str, company: str) -> str:
    """Huella para detectar la misma oferta publicada en varios portales."""
    t = re.sub(r"[^a-z0-9 ]", " ", norm(title))
    t = re.sub(r"\b(a|o|de|la|el|en|para|con|y)\b", " ", t)
    c = re.sub(r"[^a-z0-9]", "", norm(company))
    return re.sub(r"\s+", " ", t).strip() + "|" + c
