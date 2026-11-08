"""El panel guarda el destinatario en .env (RADAR_DESTINATARIO), no en config.json (que se versiona)."""

import json
import shutil

import pytest

from radar import config, db, web


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


FORM_CORREO = {
    "accion": "correo",
    "gmail_user": "remitente@example.com",
    "destinatario": "dest@example.com",
    "habilitado": "on",
    "hora": "8",
    "minimo_email": "60",
}


def test_guardar_el_correo_escribe_el_destinatario_en_el_env(panel):
    client, _, env = panel

    client.post("/config", data=FORM_CORREO)

    assert "RADAR_DESTINATARIO=dest@example.com" in env.read_text(encoding="utf-8")


def test_guardar_el_correo_no_escribe_el_destinatario_en_config_json(panel):
    client, cfg_tmp, _ = panel

    client.post("/config", data=FORM_CORREO)

    guardado = json.loads(cfg_tmp.read_text(encoding="utf-8"))
    assert "destinatario" not in guardado["notificaciones"]


def test_el_formulario_muestra_el_destinatario_configurado(panel, monkeypatch):
    client, _, _ = panel
    monkeypatch.setenv("RADAR_DESTINATARIO", "dest@example.com")

    html = client.get("/config").get_data(as_text=True)

    assert 'name="destinatario" value="dest@example.com"' in html
