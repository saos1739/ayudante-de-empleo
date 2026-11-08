"""Contacto del candidato y destinatario del resumen: salen del entorno o del cv local, nunca del código."""

import re
from pathlib import Path

import pytest

from radar import ai, config, notify

RAIZ = Path(__file__).resolve().parent.parent

CV_DE_PRUEBA = """# CV de prueba

**Contacto:** +54 9 11 5555-0000 | ana.cv@example.com
"""


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    """Cada test arranca sin variables de contacto, aunque el .env real las tenga."""
    for var in ("CANDIDATO_TELEFONO", "CANDIDATO_EMAIL", "RADAR_DESTINATARIO", "GMAIL_USER"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def cv_local(tmp_path, monkeypatch):
    ruta = tmp_path / "cv.md"
    ruta.write_text(CV_DE_PRUEBA, encoding="utf-8")
    monkeypatch.setattr(config, "CV_PATH", ruta)
    return ruta


@pytest.fixture
def sin_cv(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CV_PATH", tmp_path / "no_existe.md")


def test_contacto_prefiere_variables_de_entorno_al_cv(cv_local, monkeypatch):
    monkeypatch.setenv("CANDIDATO_TELEFONO", "+54 9 11 1111-2222")
    monkeypatch.setenv("CANDIDATO_EMAIL", "env@example.com")

    assert config.contacto_candidato() == {
        "telefono": "+54 9 11 1111-2222",
        "email": "env@example.com",
    }


def test_contacto_cae_al_cv_local_si_faltan_las_variables(cv_local):
    assert config.contacto_candidato() == {
        "telefono": "+54 9 11 5555-0000",
        "email": "ana.cv@example.com",
    }


def test_contacto_resuelve_cada_dato_por_separado(cv_local, monkeypatch):
    monkeypatch.setenv("CANDIDATO_EMAIL", "env@example.com")

    assert config.contacto_candidato() == {
        "telefono": "+54 9 11 5555-0000",
        "email": "env@example.com",
    }


def test_contacto_queda_vacio_si_no_hay_ninguna_fuente(sin_cv):
    assert config.contacto_candidato() == {"telefono": "", "email": ""}


def test_destinatario_usa_radar_destinatario(monkeypatch):
    monkeypatch.setenv("RADAR_DESTINATARIO", "dest@example.com")
    monkeypatch.setenv("GMAIL_USER", "remitente@example.com")

    assert config.destinatario() == "dest@example.com"


def test_destinatario_cae_a_gmail_user(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "remitente@example.com")

    assert config.destinatario() == "remitente@example.com"


def test_destinatario_vacio_si_no_hay_variables():
    assert config.destinatario() == ""


def test_el_resumen_por_mail_ignora_el_destinatario_del_config_json(monkeypatch):
    monkeypatch.setenv("RADAR_DESTINATARIO", "dest@example.com")
    cfg = {"notificaciones": {"destinatario": "viejo@example.com"}}

    assert notify._settings(cfg)["destinatario"] == "dest@example.com"


def test_la_carta_sin_ia_firma_con_el_contacto_configurado(monkeypatch, sin_cv):
    monkeypatch.setenv("CANDIDATO_TELEFONO", "+54 9 11 1111-2222")
    monkeypatch.setenv("CANDIDATO_EMAIL", "env@example.com")
    oferta = {"title": "Desarrollador Jr", "company": "Acme"}

    carta = ai.template_letter(oferta, [])["carta"]

    assert "env@example.com | +54 9 11 1111-2222" in carta


def test_la_carta_sin_ia_omite_la_linea_de_contacto_si_no_hay_datos(sin_cv):
    oferta = {"title": "Desarrollador Jr", "company": "Acme"}

    carta = ai.template_letter(oferta, [])["carta"]

    assert " | " not in carta.splitlines()[-1]
    assert "@" not in carta


def test_el_codigo_versionado_no_tiene_telefonos_ni_mails_fijos():
    """Guarda: ningún .py de radar/ o scripts/ ni config.json trae contacto escrito a mano."""
    telefono = re.compile(r"\+54 ?9 ?\d")
    mail = re.compile(r"[\w.+-]+@(?:gmail|hotmail|outlook|yahoo)\.com")
    archivos = [*RAIZ.glob("radar/**/*.py"), *RAIZ.glob("scripts/*.py"), RAIZ / "config.json"]

    infractores = [
        str(a.relative_to(RAIZ))
        for a in archivos
        if telefono.search(a.read_text(encoding="utf-8")) or mail.search(a.read_text(encoding="utf-8"))
    ]

    assert infractores == []
