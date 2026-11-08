"""Panel: el teléfono y la clave de WhatsApp van al .env (nunca a config.json, que se versiona)."""

import json

import pytest

from radar.notifiers import whatsapp

TELEFONO = "+5491155551234"
APIKEY = "clave-secreta-123"

FORM = {"accion": "whatsapp", "whatsapp_phone": TELEFONO, "callmebot_apikey": APIKEY,
        "canal_email": "on", "canal_whatsapp": "on"}


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    # setenv registra el valor original para que save_env_value no deje restos entre tests
    monkeypatch.setenv("WHATSAPP_PHONE", "")
    monkeypatch.setenv("CALLMEBOT_APIKEY", "")


def guardar(client, **cambios):
    return client.post("/config", data={**FORM, **cambios}, follow_redirects=True)


def test_guardar_escribe_telefono_y_clave_en_el_env(panel):
    client, _, env = panel
    guardar(client)
    contenido = env.read_text(encoding="utf-8")
    assert f"WHATSAPP_PHONE={TELEFONO}" in contenido
    assert f"CALLMEBOT_APIKEY={APIKEY}" in contenido


def test_guardar_no_escribe_secretos_en_config_json(panel):
    client, cfg_tmp, _ = panel
    guardar(client)
    texto = cfg_tmp.read_text(encoding="utf-8")
    assert TELEFONO not in texto and APIKEY not in texto and "5491155551234" not in texto


def test_guardar_actualiza_los_canales(panel):
    client, cfg_tmp, _ = panel
    guardar(client, canal_email="")
    assert json.loads(cfg_tmp.read_text(encoding="utf-8"))["notificaciones"]["canales"] == ["whatsapp"]
    guardar(client)
    assert json.loads(cfg_tmp.read_text(encoding="utf-8"))["notificaciones"]["canales"] == ["email", "whatsapp"]


def test_sin_ningun_canal_no_cambia_nada_y_avisa(panel):
    client, cfg_tmp, _ = panel
    antes = json.loads(cfg_tmp.read_text(encoding="utf-8"))["notificaciones"]["canales"]
    html = guardar(client, canal_email="", canal_whatsapp="").get_data(as_text=True)
    assert json.loads(cfg_tmp.read_text(encoding="utf-8"))["notificaciones"]["canales"] == antes
    assert "Elegí al menos un canal" in html


def test_dejar_los_campos_vacios_mantiene_las_credenciales(panel):
    client, _, env = panel
    guardar(client)
    guardar(client, whatsapp_phone="", callmebot_apikey="")
    contenido = env.read_text(encoding="utf-8")
    assert f"WHATSAPP_PHONE={TELEFONO}" in contenido and f"CALLMEBOT_APIKEY={APIKEY}" in contenido


def test_la_pagina_muestra_el_telefono_enmascarado_y_nunca_la_clave(panel):
    client, _, _ = panel
    html = guardar(client).get_data(as_text=True)
    assert "configurado ✔ (***1234)" in html
    assert APIKEY not in html and TELEFONO not in html


def test_sin_credenciales_la_pagina_lo_indica_y_no_ofrece_la_prueba(panel):
    client, _, _ = panel
    html = client.get("/config").get_data(as_text=True)
    assert "sin configurar" in html
    assert 'value="whatsapp_prueba"' not in html


def test_el_mensaje_de_prueba_usa_el_proveedor_y_avisa(panel, monkeypatch):
    client, _, _ = panel
    guardar(client)
    enviados = []

    class Respuesta:
        status_code, text = 200, "Message queued"

    monkeypatch.setattr(whatsapp.requests, "get", lambda url, params=None, timeout=None: enviados.append(params) or Respuesta())
    html = client.post("/config", data={"accion": "whatsapp_prueba"}, follow_redirects=True).get_data(as_text=True)
    assert len(enviados) == 1 and enviados[0]["phone"] == TELEFONO
    assert "Mensaje de prueba enviado" in html


def test_si_el_envio_de_prueba_falla_el_panel_muestra_el_error_sin_la_clave(panel, monkeypatch):
    client, _, _ = panel
    guardar(client)

    class Respuesta:
        status_code, text = 403, f"Wrong apikey {APIKEY}"

    monkeypatch.setattr(whatsapp.requests, "get", lambda url, params=None, timeout=None: Respuesta())
    html = client.post("/config", data={"accion": "whatsapp_prueba"}, follow_redirects=True).get_data(as_text=True)
    assert "Error al enviar por WhatsApp" in html and "HTTP 403" in html
    assert APIKEY not in html
