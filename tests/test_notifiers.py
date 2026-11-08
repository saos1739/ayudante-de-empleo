"""Orquestador de avisos y canal de correo. Ningún test envía nada real: canales falsos y SMTP simulado."""

import copy
import json
from datetime import date

import pytest

from radar import db, notifiers
from radar.config import CONFIG_PATH
from radar.notifiers import email as canal_email
from radar.notifiers.base import Contexto, Notificador, Resultado
from tests.helpers import guardar

DESC = "Perfil junior con JavaScript y React. "


@pytest.fixture
def cfg(monkeypatch):
    """Config real con avisos sobre los dos canales; el orquestador la lee desde acá."""
    c = copy.deepcopy(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    c["notificaciones"].update({"email_habilitado": True, "canales": ["email", "whatsapp"],
                                "puntaje_minimo_email": 0, "enviar_si_no_hay_novedades": False})
    monkeypatch.setattr(notifiers, "load_config", lambda: c)
    return c


def canal_falso(nombre, *, configurado=True, falla=None, maximo=None):
    """Clase de canal de mentira: avisa hasta `maximo` ofertas, o falla con `falla`."""

    class Falso(Notificador):
        def configurado(self):
            return configurado

        def enviar(self, ofertas, contexto=None):
            if falla:
                raise RuntimeError(falla)
            return Resultado(nombre, True, [o["id"] for o in ofertas][:maximo])

        def enviar_prueba(self):
            pass

    Falso.nombre = nombre
    return Falso


def instalar(monkeypatch, **canales):
    for nombre, clase in canales.items():
        monkeypatch.setitem(notifiers.CANALES, nombre, clase)


def avisadas():
    with db.connect() as conn:
        return [r["id"] for r in conn.execute("SELECT id FROM jobs WHERE notified_at IS NOT NULL ORDER BY id")]


@pytest.fixture
def tres_ofertas(base):
    return [guardar(DESC, uid=f"o{i}") for i in range(3)]


class TestOrquestador:
    def test_oferta_avisada_por_un_canal_queda_marcada(self, cfg, tres_ofertas, monkeypatch):
        instalar(monkeypatch, email=canal_falso("email"), whatsapp=canal_falso("whatsapp", configurado=False))
        r = notifiers.send_digest(log=lambda *_: None)
        assert r["sent"] and r["count"] == 3
        assert avisadas() == tres_ofertas
        assert db.get_meta("ultimo_resumen") == date.today().isoformat()

    def test_si_un_canal_falla_el_otro_igual_avisa(self, cfg, tres_ofertas, monkeypatch):
        instalar(monkeypatch, email=canal_falso("email", falla="SMTP caído"), whatsapp=canal_falso("whatsapp"))
        log = []
        r = notifiers.send_digest(log=log.append)
        assert r["sent"] and r["count"] == 3
        assert r["errores"] == ["email: SMTP caído"]
        assert any("SMTP caído" in linea for linea in log)

    def test_solo_se_marcan_las_ofertas_que_llegaron_por_algun_canal(self, cfg, tres_ofertas, monkeypatch):
        # WhatsApp avisa sólo las primeras 2 y el correo falla: la tercera tiene que seguir pendiente.
        instalar(monkeypatch, email=canal_falso("email", falla="caído"), whatsapp=canal_falso("whatsapp", maximo=2))
        r = notifiers.send_digest(log=lambda *_: None)
        assert r["count"] == 2
        assert len(avisadas()) == 2
        assert len(notifiers.pending_jobs(0)) == 1

    def test_la_union_de_canales_marca_todo_una_sola_vez(self, cfg, tres_ofertas, monkeypatch):
        instalar(monkeypatch, email=canal_falso("email"), whatsapp=canal_falso("whatsapp", maximo=1))
        assert notifiers.send_digest(log=lambda *_: None)["count"] == 3
        assert avisadas() == tres_ofertas

    def test_si_todos_los_canales_fallan_no_se_marca_nada(self, cfg, tres_ofertas, monkeypatch):
        instalar(monkeypatch, email=canal_falso("email", falla="a"), whatsapp=canal_falso("whatsapp", falla="b"))
        r = notifiers.send_digest(log=lambda *_: None)
        assert not r["sent"] and r["count"] == 0
        assert "email: a" in r["reason"] and "whatsapp: b" in r["reason"]
        assert avisadas() == []
        assert db.get_meta("ultimo_resumen") is None

    def test_un_canal_sin_configurar_se_omite(self, cfg, tres_ofertas, monkeypatch):
        instalar(monkeypatch, email=canal_falso("email", configurado=False),
                 whatsapp=canal_falso("whatsapp", configurado=False))
        r = notifiers.send_digest(log=lambda *_: None)
        assert not r["sent"] and r["reason"] == "ningún canal configurado"

    def test_sin_ofertas_no_envia_pero_cierra_el_dia(self, cfg, base, monkeypatch):
        instalar(monkeypatch, email=canal_falso("email"), whatsapp=canal_falso("whatsapp"))
        r = notifiers.send_digest(log=lambda *_: None)
        assert not r["sent"] and r["reason"] == "sin novedades"
        assert db.get_meta("ultimo_resumen") == date.today().isoformat()

    def test_deshabilitado_no_envia_salvo_que_se_fuerce(self, cfg, tres_ofertas, monkeypatch):
        cfg["notificaciones"]["email_habilitado"] = False
        instalar(monkeypatch, email=canal_falso("email"), whatsapp=canal_falso("whatsapp"))
        assert notifiers.send_digest(log=lambda *_: None)["reason"] == "avisos deshabilitados"
        assert notifiers.send_digest(force=True, log=lambda *_: None)["sent"]

    def test_solo_usa_los_canales_listados_en_la_config(self, cfg, tres_ofertas, monkeypatch):
        cfg["notificaciones"]["canales"] = ["email"]
        instalar(monkeypatch, email=canal_falso("email", maximo=1), whatsapp=canal_falso("whatsapp"))
        assert notifiers.send_digest(log=lambda *_: None)["count"] == 1

    def test_sin_clave_canales_usa_solo_el_correo(self, cfg):
        del cfg["notificaciones"]["canales"]
        assert [n.nombre for n in notifiers.crear_notificadores(cfg)] == ["email"]

    def test_los_canales_desconocidos_se_ignoran(self, cfg):
        cfg["notificaciones"]["canales"] = ["email", "telegrama"]
        assert [n.nombre for n in notifiers.crear_notificadores(cfg)] == ["email"]


class TestResumenPendiente:
    def test_toca_resumen_pasada_la_hora_y_si_no_se_envio_hoy(self, cfg, base, monkeypatch):
        instalar(monkeypatch, email=canal_falso("email"))
        cfg["notificaciones"]["hora_resumen"] = 0
        assert notifiers.digest_due(cfg)
        db.set_meta("ultimo_resumen", date.today().isoformat())
        assert not notifiers.digest_due(cfg)

    def test_no_toca_si_no_hay_ningun_canal_configurado(self, cfg, base, monkeypatch):
        instalar(monkeypatch, email=canal_falso("email", configurado=False))
        cfg["notificaciones"].update({"hora_resumen": 0, "canales": ["email"]})
        assert not notifiers.digest_due(cfg)


class FakeSMTP:
    """Reemplaza smtplib.SMTP_SSL: guarda los mensajes en vez de enviarlos."""

    enviados: list = []

    def __init__(self, host, port, context=None, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.password = password

    def send_message(self, msg):
        FakeSMTP.enviados.append(msg)


class TestCorreo:
    @pytest.fixture(autouse=True)
    def smtp_simulado(self, monkeypatch):
        FakeSMTP.enviados = []
        monkeypatch.setattr(canal_email.smtplib, "SMTP_SSL", FakeSMTP)
        monkeypatch.setenv("GMAIL_USER", "remitente@example.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
        monkeypatch.setenv("RADAR_DESTINATARIO", "dest@example.com")

    def test_envia_el_resumen_y_devuelve_las_ofertas_avisadas(self, cfg, tres_ofertas):
        filas = notifiers.pending_jobs(0)
        r = canal_email.EmailNotificador(cfg).enviar(filas)
        assert r.enviado and r.ids_avisados == [f["id"] for f in filas]
        (msg,) = FakeSMTP.enviados
        assert msg["To"] == "dest@example.com"
        assert "3 ofertas nuevas" in msg["Subject"]
        assert "Desarrollador Full Stack Jr" in msg.get_body(("plain",)).get_content()

    def test_sin_ofertas_manda_el_aviso_de_sin_novedades(self, cfg, base):
        r = canal_email.EmailNotificador(cfg).enviar([])
        assert r.enviado and r.ids_avisados == []
        assert "Sin ofertas nuevas" in FakeSMTP.enviados[0]["Subject"]

    def test_la_prueba_se_envia_al_destinatario(self, cfg, base):
        canal_email.EmailNotificador(cfg).enviar_prueba()
        assert FakeSMTP.enviados[0]["Subject"].endswith("Correo de prueba")

    def test_sin_credenciales_no_esta_configurado(self, cfg, monkeypatch):
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
        assert not canal_email.EmailNotificador(cfg).configurado()

    def test_en_ci_el_correo_no_incluye_links_al_panel_local(self, cfg, tres_ofertas):
        filas = notifiers.pending_jobs(0)
        canal_email.EmailNotificador(cfg).enviar(filas, Contexto(con_panel=False))
        html = FakeSMTP.enviados[0].get_body(("html",)).get_content()
        assert "127.0.0.1" not in html and "Abrir en el panel" not in html
        assert "GitHub Actions" in html

    def test_en_local_el_correo_sigue_incluyendo_el_link_al_panel(self, cfg, tres_ofertas):
        canal_email.EmailNotificador(cfg).enviar(notifiers.pending_jobs(0))
        html = FakeSMTP.enviados[0].get_body(("html",)).get_content()
        assert "Abrir en el panel" in html

    def test_el_correo_menciona_las_fuentes_que_fallaron(self, cfg, tres_ofertas):
        contexto = Contexto(con_panel=False, fuentes_fallidas=("Bumeran", "Talent (sin resultados)"))
        canal_email.EmailNotificador(cfg).enviar(notifiers.pending_jobs(0), contexto)
        mensaje = FakeSMTP.enviados[0]
        assert "Bumeran, Talent (sin resultados)" in mensaje.get_body(("html",)).get_content()
        assert "Bumeran, Talent (sin resultados)" in mensaje.get_body(("plain",)).get_content()

    def test_sin_fallas_el_correo_no_agrega_avisos_de_fuentes(self, cfg, tres_ofertas):
        canal_email.EmailNotificador(cfg).enviar(notifiers.pending_jobs(0))
        assert "Fuentes que fallaron" not in FakeSMTP.enviados[0].get_body(("plain",)).get_content()

    def test_el_aviso_de_sin_novedades_tambien_menciona_las_fuentes_caidas(self, cfg, base):
        canal_email.EmailNotificador(cfg).enviar([], Contexto(fuentes_fallidas=("Bumeran",)))
        assert "Bumeran" in FakeSMTP.enviados[0].get_body(("plain",)).get_content()
