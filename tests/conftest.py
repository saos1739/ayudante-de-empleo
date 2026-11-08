import shutil
import socket

import pytest

from radar import config, db, web


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Base SQLite temporal: ningún test toca tu base real."""
    monkeypatch.setenv("RADAR_DB", str(tmp_path / "radar.db"))
    db.init_db()
    return tmp_path / "radar.db"


@pytest.fixture
def panel(tmp_path, monkeypatch):
    """Cliente de Flask que lee y escribe un config.json y un .env temporales."""
    cfg_tmp = tmp_path / "config.json"
    shutil.copy(config.CONFIG_PATH, cfg_tmp)
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_tmp)
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("RADAR_DB", str(tmp_path / "radar.db"))
    db.init_db()
    # setenv registra el valor original para que save_env_value no deje restos entre tests
    for var in ("RADAR_DESTINATARIO", "GMAIL_USER", "GMAIL_APP_PASSWORD"):
        monkeypatch.setenv(var, "")
    web.app.config["TESTING"] = True
    return web.app.test_client(), cfg_tmp, tmp_path / ".env"


@pytest.fixture(autouse=True)
def sin_internet(monkeypatch):
    """Ningún test puede salir a internet: un pedido real falla en vez de pegarle a un portal, a Gemini o a CallMeBot."""

    def bloqueado(*args, **kwargs):
        raise RuntimeError("Los tests no pueden hacer pedidos a internet: simulá la respuesta con un mock.")

    monkeypatch.setattr(socket.socket, "connect", bloqueado)
    monkeypatch.setattr(socket.socket, "connect_ex", bloqueado)
    monkeypatch.setattr(socket, "getaddrinfo", bloqueado)
