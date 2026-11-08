"""Carga de configuración, variables de entorno y rutas del proyecto."""

import json
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
CV_PATH = BASE_DIR / "perfil" / "cv.md"
ENV_PATH = BASE_DIR / ".env"


def load_env() -> None:
    """Carga variables desde .env sin dependencias externas (no pisa las ya definidas)."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def save_env_value(key: str, value: str) -> None:
    """Guarda o reemplaza una variable en .env y la aplica al proceso actual."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    lines = [linea for linea in lines if not linea.strip().startswith(f"{key}=")]
    if value:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if value:
        os.environ[key] = value
    else:
        os.environ.pop(key, None)


def db_path() -> Path:
    """La base se guarda fuera de Google Drive para evitar conflictos de sincronización con SQLite."""
    custom = os.environ.get("RADAR_DB")
    if custom:
        path = Path(custom)
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        path = Path(os.environ["LOCALAPPDATA"]) / "RadarEmpleo" / "radar.db"
    else:
        path = BASE_DIR / "data" / "radar.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_config() -> dict:
    """Se relee en cada búsqueda para que los cambios del panel apliquen sin reiniciar."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_cv() -> str:
    return CV_PATH.read_text(encoding="utf-8") if CV_PATH.exists() else ""


def gemini_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


_LINEA_CONTACTO_CV = re.compile(r"^\*\*Contacto:\*\*\s*(.+)$", re.MULTILINE)
_TELEFONO = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _contacto_del_cv() -> dict:
    """Lee teléfono y mail de la línea '**Contacto:**' del cv local (si existe)."""
    linea = _LINEA_CONTACTO_CV.search(load_cv())
    texto = linea.group(1) if linea else ""
    telefono = _TELEFONO.search(texto)
    email = _EMAIL.search(texto)
    return {"telefono": telefono.group(0) if telefono else "", "email": email.group(0) if email else ""}


def contacto_candidato() -> dict:
    """Contacto que firma las cartas. Cada dato sale de CANDIDATO_TELEFONO / CANDIDATO_EMAIL
    y, si falta, del cv local. Si no está en ninguno queda vacío: nunca se escribe en el código."""
    del_cv = _contacto_del_cv()
    return {
        "telefono": os.environ.get("CANDIDATO_TELEFONO", "").strip() or del_cv["telefono"],
        "email": os.environ.get("CANDIDATO_EMAIL", "").strip() or del_cv["email"],
    }


def destinatario() -> str:
    """Destinatario del resumen por mail: RADAR_DESTINATARIO o, si no existe, GMAIL_USER."""
    return os.environ.get("RADAR_DESTINATARIO", "").strip() or os.environ.get("GMAIL_USER", "").strip()


load_env()
