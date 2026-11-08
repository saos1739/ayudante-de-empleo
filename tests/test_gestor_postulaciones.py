"""El gestor de postulaciones toma el contacto del entorno, no de datos escritos en el script."""

import importlib.util
from pathlib import Path

import pytest

from radar import config

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "gestor_postulaciones.py"


def cargar_gestor():
    spec = importlib.util.spec_from_file_location("gestor_postulaciones", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(autouse=True)
def sin_cv_local(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CV_PATH", tmp_path / "no_existe.md")


def test_el_perfil_toma_telefono_y_mail_del_entorno(monkeypatch):
    monkeypatch.setenv("CANDIDATO_TELEFONO", "+54 9 11 1111-2222")
    monkeypatch.setenv("CANDIDATO_EMAIL", "env@example.com")

    perfil = cargar_gestor().PERFIL_CANDIDATO

    assert perfil["telefono"] == "+54 9 11 1111-2222"
    assert perfil["email"] == "env@example.com"


def test_la_propuesta_generada_incluye_el_contacto_del_entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("CANDIDATO_TELEFONO", "+54 9 11 1111-2222")
    monkeypatch.setenv("CANDIDATO_EMAIL", "env@example.com")
    monkeypatch.chdir(tmp_path)  # el gestor escribe en ./postulaciones

    cargar_gestor().crear_propuesta("Acme", "Dev Jr", "LinkedIn", "Remoto", "python")

    texto = next((tmp_path / "postulaciones").glob("propuesta_acme_*.md")).read_text(encoding="utf-8")
    assert "env@example.com" in texto
    assert "+54 9 11 1111-2222" in texto
