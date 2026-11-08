"""Guarda de la suite: si un test intenta salir a internet, tiene que fallar."""

import socket

import pytest
import requests


def test_un_pedido_http_real_queda_bloqueado():
    with pytest.raises(Exception, match="pedidos a internet"):
        requests.get("https://example.com", timeout=2)


def test_una_conexion_directa_queda_bloqueada():
    with pytest.raises(RuntimeError, match="pedidos a internet"):
        socket.create_connection(("example.com", 443), timeout=2)


def test_los_pedidos_mockeados_siguen_funcionando(monkeypatch):
    class Respuesta:
        status_code, text = 200, "ok"

    monkeypatch.setattr(requests, "get", lambda *a, **k: Respuesta())
    assert requests.get("https://example.com").text == "ok"


def test_la_suite_nunca_usa_la_base_real(monkeypatch):
    """Guarda: sin pedir ninguna fixture, la base apunta a un archivo temporal y no a %LOCALAPPDATA%."""
    from radar.config import db_path

    ruta = str(db_path())
    assert "RadarEmpleo" not in ruta
    assert "pytest" in ruta.lower()
