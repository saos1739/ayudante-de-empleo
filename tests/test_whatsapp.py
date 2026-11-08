"""Canal de WhatsApp: formato y partición de mensajes, CallMeBot con HTTP mockeado y envíos parciales."""

import copy
import json
from datetime import date

import pytest
import requests

from radar import db, notifiers
from radar.config import CONFIG_PATH
from radar.notifiers import whatsapp
from radar.notifiers.whatsapp import CallMeBot, WhatsAppError, WhatsAppNotificador, armar_mensajes
from tests.helpers import guardar

TELEFONO = "+54 9 11 5555-1234"
APIKEY = "clave-secreta-123"
HOY = date(2026, 11, 8)
DESC = "Perfil junior con JavaScript y React. "


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    """Ningún test espera de verdad entre mensajes; se anotan las pausas pedidas."""
    pausas = []
    monkeypatch.setattr(whatsapp, "_pausar", pausas.append)
    return pausas


@pytest.fixture
def cfg():
    c = copy.deepcopy(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    c["notificaciones"]["canales"] = ["email", "whatsapp"]
    return c


@pytest.fixture
def credenciales(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PHONE", TELEFONO)
    monkeypatch.setenv("CALLMEBOT_APIKEY", APIKEY)


class RespuestaFalsa:
    def __init__(self, status=200, text="Message queued. You will receive it in a few seconds."):
        self.status_code = status
        self.text = text


@pytest.fixture
def http(monkeypatch):
    """Reemplaza requests.get: guarda los pedidos y devuelve las respuestas encoladas (200 por defecto)."""

    class Http:
        pedidos: list = []
        respuestas: list = []

    Http.pedidos, Http.respuestas = [], []

    def get(url, params=None, timeout=None):
        Http.pedidos.append({"url": url, "params": params, "timeout": timeout})
        accion = Http.respuestas.pop(0) if Http.respuestas else RespuestaFalsa()
        if isinstance(accion, Exception):
            raise accion
        return accion

    monkeypatch.setattr(whatsapp.requests, "get", get)
    return Http


def ofertas_guardadas(cantidad):
    ids = [guardar(DESC, uid=f"o{i}", titulo=f"Desarrollador Full Stack Jr {i}") for i in range(cantidad)]
    return [db.get_job(i) for i in ids]


class TestFormatoDelMensaje:
    def test_encabezado_con_fecha_y_cantidad(self, base):
        (texto, _), = armar_mensajes(ofertas_guardadas(2), HOY, hay_mail=True)
        assert texto.startswith("Radar de Empleo · 08/11/2026 · 2 ofertas nuevas")

    def test_encabezado_en_singular(self, base):
        (texto, _), = armar_mensajes(ofertas_guardadas(1), HOY, hay_mail=True)
        assert texto.splitlines()[0].endswith("1 oferta nueva")

    def test_cada_oferta_lleva_puntaje_etiqueta_titulo_empresa_modalidad_y_link(self, base):
        (oferta,) = ofertas_guardadas(1)
        (texto, ids), = armar_mensajes([oferta], HOY, hay_mail=True)
        bloque = texto.split("\n\n")[1]
        assert bloque.splitlines() == [
            f"1) [{oferta['rule_score']}] encaja · Desarrollador Full Stack Jr 0",
            "ACME · Híbrido",
            "https://example.com/o0",
        ]
        assert ids == [oferta["id"]]

    def test_sin_etiqueta_no_deja_un_separador_vacio(self, base):
        (oferta,) = ofertas_guardadas(1)
        con_etiqueta = dict(oferta) | {"etiqueta": None}
        (texto, _), = armar_mensajes([con_etiqueta], HOY, hay_mail=True)
        assert f"1) [{oferta['rule_score']}] Desarrollador" in texto

    def test_solo_las_cinco_mejores_y_cierre_con_las_restantes(self, base):
        ofertas = ofertas_guardadas(8)
        (texto, ids), = armar_mensajes(ofertas, HOY, hay_mail=True)
        assert ids == [o["id"] for o in ofertas[:5]]
        assert "6)" not in texto
        assert texto.endswith("+3 más en tu mail")

    def test_sin_restantes_no_hay_cierre(self, base):
        (texto, _), = armar_mensajes(ofertas_guardadas(5), HOY, hay_mail=True)
        assert "más en tu mail" not in texto

    def test_sin_canal_de_mail_no_promete_un_mail(self, base):
        (texto, _), = armar_mensajes(ofertas_guardadas(8), HOY, hay_mail=False)
        assert "mail" not in texto

    def test_si_supera_el_largo_se_parte_en_varios_mensajes_sin_cortar_ofertas(self, base):
        ofertas = ofertas_guardadas(5)
        mensajes = armar_mensajes(ofertas, HOY, hay_mail=True, max_caracteres=200)
        assert len(mensajes) > 1
        assert all(len(texto) <= 200 for texto, _ in mensajes)
        assert [i for _, ids in mensajes for i in ids] == [o["id"] for o in ofertas]
        assert mensajes[0][0].startswith("Radar de Empleo")
        assert not any(texto.startswith("Radar de Empleo") for texto, _ in mensajes[1:])
        links = [linea for texto, _ in mensajes for linea in texto.splitlines() if linea.startswith("https://")]
        assert links == [f"https://example.com/o{i}" for i in range(5)]  # ninguno cortado ni repetido

    def test_un_titulo_larguisimo_se_acorta_pero_el_link_queda_entero(self, base):
        (oferta,) = ofertas_guardadas(1)
        largo = dict(oferta) | {"title": "Desarrollador " + "muy " * 80 + "Jr"}
        (texto, _), = armar_mensajes([largo], HOY, hay_mail=True, max_caracteres=300)
        assert "…" in texto
        assert texto.endswith("https://example.com/o0")
        assert len(texto) <= 300
        assert texto.startswith("Radar de Empleo")  # encabezado y oferta en el mismo mensaje

    def test_el_cierre_que_no_entra_va_en_su_propio_mensaje(self, base):
        ofertas = ofertas_guardadas(7)
        mensajes = armar_mensajes(ofertas, HOY, hay_mail=True, max_caracteres=300)
        assert mensajes[-1][0].endswith("+2 más en tu mail")
        assert all(len(texto) <= 300 for texto, _ in mensajes)


class TestCallMeBot:
    def test_arma_el_pedido_con_telefono_texto_y_apikey(self, credenciales, http):
        CallMeBot().enviar_texto("Hola\nmundo")
        (pedido,) = http.pedidos
        assert pedido["url"] == "https://api.callmebot.com/whatsapp.php"
        assert pedido["params"] == {"phone": "+5491155551234", "text": "Hola\nmundo", "apikey": APIKEY}
        assert pedido["timeout"]

    def test_requests_codifica_el_texto_como_pide_callmebot(self, credenciales):
        pedido = requests.Request("GET", whatsapp.CALLMEBOT_URL,
                                  params={"phone": "+5491155551234", "text": "Hola mundo\nñ", "apikey": "k"}).prepare()
        assert "phone=%2B5491155551234" in pedido.url
        assert "text=Hola+mundo%0A%C3%B1" in pedido.url

    def test_sin_credenciales_no_esta_configurado_y_no_hace_pedidos(self, monkeypatch, http):
        monkeypatch.setenv("WHATSAPP_PHONE", "")
        monkeypatch.setenv("CALLMEBOT_APIKEY", "")
        assert not CallMeBot().configurado()
        with pytest.raises(WhatsAppError, match="WHATSAPP_PHONE"):
            CallMeBot().enviar_texto("x")
        assert http.pedidos == []

    def test_un_error_http_se_informa(self, credenciales, http):
        http.respuestas.append(RespuestaFalsa(500, "Internal error"))
        with pytest.raises(WhatsAppError, match="HTTP 500"):
            CallMeBot().enviar_texto("x")

    def test_una_respuesta_200_con_error_se_informa(self, credenciales, http):
        http.respuestas.append(RespuestaFalsa(200, "<html>ERROR: APIKey is invalid</html>"))
        with pytest.raises(WhatsAppError, match="rechazó"):
            CallMeBot().enviar_texto("x")

    def test_el_error_de_conexion_no_filtra_la_apikey_ni_el_telefono(self, credenciales, http):
        url = f"https://api.callmebot.com/whatsapp.php?phone=%2B5491155551234&apikey={APIKEY}"
        http.respuestas.append(requests.ConnectionError(f"HTTPSConnectionPool ... {url}"))
        with pytest.raises(WhatsAppError) as error:
            CallMeBot().enviar_texto("x")
        assert APIKEY not in str(error.value) and "5491155551234" not in str(error.value)
        assert "ConnectionError" in str(error.value)
        assert error.value.__suppress_context__  # el traceback tampoco arrastra la URL original

    def test_la_respuesta_del_servidor_se_muestra_sin_secretos(self, credenciales, http):
        http.respuestas.append(RespuestaFalsa(403, f"Wrong apikey {APIKEY} for +5491155551234"))
        with pytest.raises(WhatsAppError) as error:
            CallMeBot().enviar_texto("x")
        assert APIKEY not in str(error.value) and "5491155551234" not in str(error.value)

    def test_el_telefono_se_enmascara_para_los_logs(self):
        assert whatsapp.enmascarar(TELEFONO) == "***1234"


class TestNotificador:
    def test_envia_las_mejores_ofertas_y_devuelve_las_avisadas(self, cfg, credenciales, http, base):
        ofertas = ofertas_guardadas(8)
        r = WhatsAppNotificador(cfg).enviar(ofertas)
        assert r.enviado and r.motivo == "ok"
        assert r.ids_avisados == [o["id"] for o in ofertas[:5]]
        assert len(http.pedidos) == 1
        assert "+3 más en tu mail" in http.pedidos[0]["params"]["text"]

    def test_parte_en_varios_mensajes_con_pausa_entre_envios(self, cfg, credenciales, http, base, sin_esperas):
        cfg["notificaciones"]["whatsapp_max_caracteres"] = 200
        cfg["notificaciones"]["whatsapp_pausa_seg"] = 7
        r = WhatsAppNotificador(cfg).enviar(ofertas_guardadas(5))
        assert len(http.pedidos) > 1
        assert sin_esperas == [7.0] * (len(http.pedidos) - 1)
        assert len(r.ids_avisados) == 5

    def test_si_un_mensaje_intermedio_falla_informa_las_que_llegaron(self, cfg, credenciales, http, base):
        cfg["notificaciones"]["whatsapp_max_caracteres"] = 200
        http.respuestas += [RespuestaFalsa(), RespuestaFalsa(500, "caído")]
        ofertas = ofertas_guardadas(5)
        r = WhatsAppNotificador(cfg).enviar(ofertas)
        assert r.enviado and r.motivo.startswith("parcial: llegaron 1 de ")
        assert 0 < len(r.ids_avisados) < 5
        assert len(http.pedidos) == 2  # corta al primer error, no sigue insistiendo

    def test_si_falla_el_primer_mensaje_levanta_el_error(self, cfg, credenciales, http, base):
        http.respuestas.append(RespuestaFalsa(500, "caído"))
        with pytest.raises(WhatsAppError, match="HTTP 500"):
            WhatsAppNotificador(cfg).enviar(ofertas_guardadas(2))

    def test_sin_ofertas_no_manda_nada(self, cfg, credenciales, http, base):
        r = WhatsAppNotificador(cfg).enviar([])
        assert not r.enviado and r.ids_avisados == []
        assert http.pedidos == []

    def test_el_mensaje_de_prueba_se_envia(self, cfg, credenciales, http):
        WhatsAppNotificador(cfg).enviar_prueba()
        assert "mensaje de prueba" in http.pedidos[0]["params"]["text"]

    def test_proveedor_desconocido_no_esta_configurado_y_explica_por_que(self, cfg, credenciales):
        cfg["notificaciones"]["whatsapp_proveedor"] = "paloma-mensajera"
        notificador = WhatsAppNotificador(cfg)
        assert not notificador.configurado()
        with pytest.raises(WhatsAppError, match="callmebot"):
            notificador.enviar_prueba()

    def test_otro_proveedor_se_enchufa_sin_tocar_el_canal(self, cfg, base):
        enviados = []

        class Otro(whatsapp.ProveedorWhatsApp):
            def configurado(self):
                return True

            def enviar_texto(self, texto):
                enviados.append(texto)

        r = WhatsAppNotificador(cfg, proveedor=Otro()).enviar(ofertas_guardadas(2))
        assert r.enviado and len(enviados) == 1


class TestIntegracionConElOrquestador:
    @pytest.fixture
    def orquestador(self, cfg, monkeypatch):
        cfg["notificaciones"].update({"email_habilitado": True, "puntaje_minimo_email": 0})
        monkeypatch.setattr(notifiers, "load_config", lambda: cfg)
        monkeypatch.setenv("GMAIL_USER", "")  # el correo queda sin configurar: sólo WhatsApp
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
        return cfg

    def test_whatsapp_solo_avisa_las_cinco_y_las_demas_quedan_pendientes(self, orquestador, credenciales, http, base):
        orquestador["notificaciones"]["canales"] = ["whatsapp"]
        ofertas_guardadas(8)
        r = notifiers.send_digest(log=lambda *_: None)
        assert r["sent"] and r["count"] == 5
        assert len(notifiers.pending_jobs(0)) == 3

    def test_el_mensaje_de_prueba_por_la_interfaz_comun(self, orquestador, credenciales, http):
        notifiers.send_test("whatsapp")
        assert len(http.pedidos) == 1

    def test_whatsapp_sin_configurar_se_omite_y_se_sigue(self, orquestador, monkeypatch, http, base):
        monkeypatch.setenv("WHATSAPP_PHONE", "")
        monkeypatch.setenv("CALLMEBOT_APIKEY", "")
        ofertas_guardadas(2)
        log = []
        r = notifiers.send_digest(log=log.append)
        assert not r["sent"] and r["reason"] == "ningún canal configurado"
        assert any("whatsapp: sin configurar" in linea for linea in log)
        assert http.pedidos == []

    def test_un_envio_parcial_queda_avisado_en_el_log(self, orquestador, credenciales, http, base):
        orquestador["notificaciones"].update({"canales": ["whatsapp"], "whatsapp_max_caracteres": 200})
        http.respuestas += [RespuestaFalsa(), RespuestaFalsa(500, "caído")]
        ofertas_guardadas(5)
        log = []
        r = notifiers.send_digest(log=log.append)
        assert r["sent"] and 0 < r["count"] < 5
        assert any("parcial" in linea for linea in log)
        assert any("parcial" in e for e in r["errores"])


class TestFuentesFallidasEnWhatsApp:
    def test_el_cierre_menciona_las_fuentes_que_fallaron(self, base):
        (texto, _), = armar_mensajes(ofertas_guardadas(2), HOY, hay_mail=True, fuentes_fallidas=["Bumeran", "Talent"])
        assert texto.endswith("Fuentes con error hoy: Bumeran, Talent")

    def test_sin_fallas_no_hay_linea_de_fuentes(self, base):
        (texto, _), = armar_mensajes(ofertas_guardadas(2), HOY, hay_mail=True)
        assert "Fuentes con error" not in texto

    def test_va_despues_del_cierre_del_mail(self, base):
        (texto, _), = armar_mensajes(ofertas_guardadas(7), HOY, hay_mail=True, fuentes_fallidas=["Bumeran"])
        assert texto.endswith("+2 más en tu mail\n\nFuentes con error hoy: Bumeran")

    def test_el_notificador_las_toma_del_contexto(self, cfg, credenciales, http, base):
        from radar.notifiers.base import Contexto
        WhatsAppNotificador(cfg).enviar(ofertas_guardadas(2), Contexto(fuentes_fallidas=("Bumeran",)))
        assert "Fuentes con error hoy: Bumeran" in http.pedidos[0]["params"]["text"]
