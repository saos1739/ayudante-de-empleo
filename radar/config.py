"""Carga de configuración, variables de entorno y rutas del proyecto."""

import json
import os
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
    lines = [l for l in lines if not l.strip().startswith(f"{key}=")]
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


load_env()
