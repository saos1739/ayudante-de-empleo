"""Corrida diaria en CI: modo, fuentes, estado entre corridas y exclusión de links al panel."""

import copy
import json

import pytest

from radar import ci, db, notifiers, runner
from radar.config import CONFIG_PATH
from radar.estado_ci import Estado
from radar.notifiers.base import Notificador, Resultado
from tests.fuentes_falsas import fuente, oferta


@pytest.fixture
def cfg(monkeypatch):
    c = copy.deepcopy(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    c["notificaciones"].update({"modo": "ci", "canales": ["email"], "email_habilitado": True,
                                "puntaje_minimo_email": 0, "enviar_si_no_hay_novedades": False})
    monkeypatch.setattr(ci, "load_config", lambda: c)
    monkeypatch.setattr(notifiers, "load_config", lambda: c)
    return c


@pytest.fixture
def canal(monkeypatch):
    """Canal de mentira: anota cada envío (ofertas y contexto) y puede fallar a pedido."""

    class Canal(Notificador):
        nombre = "email"
        envios: list = []
        falla = False

        def configurado(self):
            return True

        def enviar(self, ofertas, contexto=None):
            if Canal.falla:
                raise RuntimeError("SMTP caído")
            Canal.envios.append({"titulos": [o["title"] for o in ofertas], "contexto": contexto})
            return Resultado("email", True, [o["id"] for o in ofertas])

        def enviar_prueba(self):
            pass

    Canal.envios, Canal.falla = [], False
    monkeypatch.setitem(notifiers.CANALES, "email", Canal)
    return Canal


@pytest.fixture
def nube(cfg, canal, tmp_path, monkeypatch):
    """Entorno de Actions: base vacía en cada corrida, estado en un archivo y fuentes de mentira."""
    monkeypatch.setenv("RADAR_ESTADO", str(tmp_path / "estado" / "notificados.json"))
    monkeypatch.setattr(runner.ai, "available", lambda: False)
    monkeypatch.setattr(runner, "pause", lambda cfg: None)
    monkeypatch.setattr(runner, "log", lambda *_: None)
    registro = {}
    monkeypatch.setattr(runner, "ALL_SOURCES", registro)
    cfg["busqueda"]["fuentes_ci"] = ["a"]

    def nueva_corrida():
        """Cada corrida de Actions arranca con una base nueva; el estado sí persiste en el archivo."""
        nueva = tmp_path / f"radar_{len(list(tmp_path.glob('radar_*.db')))}.db"
        monkeypatch.setenv("RADAR_DB", str(nueva))
        return ci.resumen_ci(log=lambda *_: None)

    nueva_corrida.fuentes = registro
    return nueva_corrida


class TestModo:
    def test_en_modo_local_la_corrida_en_la_nube_no_hace_nada(self, cfg, canal, monkeypatch, base):
        cfg["notificaciones"]["modo"] = "local"
        monkeypatch.setattr(runner, "run_search", lambda *a, **k: pytest.fail("no debería buscar"))
        r = ci.resumen_ci(log=lambda *_: None)
        assert not r["sent"] and "modo «local»" in r["reason"]
        assert canal.envios == []

    def test_en_modo_ci_la_corrida_local_no_manda_avisos(self, cfg, canal, base):
        guardar_pendiente()
        r = notifiers.send_digest(log=lambda *_: None)
        assert not r["sent"] and "GitHub Actions" in r["reason"]
        assert canal.envios == []

    def test_en_modo_ci_el_panel_tampoco_dispara_el_resumen_automatico(self, cfg, canal, base):
        cfg["notificaciones"]["hora_resumen"] = 0
        assert not notifiers.digest_due(cfg)

    def test_forzar_manda_igual_aunque_el_modo_no_coincida(self, cfg, canal, base):
        guardar_pendiente()
        assert notifiers.send_digest(force=True, log=lambda *_: None)["sent"]

    def test_un_modo_desconocido_cuenta_como_local(self, cfg):
        cfg["notificaciones"]["modo"] = "nube"
        assert notifiers.modo(cfg) == "local"


def guardar_pendiente():
    from tests.helpers import guardar
    return guardar("Perfil junior con JavaScript y React. ", uid="p")


class TestFuentes:
    def test_sin_fuentes_ci_usa_las_activas_menos_linkedin(self, cfg):
        del cfg["busqueda"]["fuentes_ci"]
        cfg["busqueda"]["fuentes_activas"] = ["getonbrd", "linkedin", "bumeran"]
        assert ci.fuentes_ci(cfg) == ["getonbrd", "bumeran"]

    def test_la_config_del_repo_deja_linkedin_afuera_de_ci_pero_activo_en_local(self):
        repo = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["busqueda"]
        assert "linkedin" not in repo["fuentes_ci"]
        assert "linkedin" in repo["fuentes_activas"]

    def test_la_corrida_usa_fuentes_ci_y_no_las_activas(self, nube, cfg):
        cfg["busqueda"]["fuentes_activas"] = ["b"]
        nube.fuentes["a"] = fuente("a", [oferta("1")])
        nube.fuentes["b"] = fuente("b", [oferta("2", empresa="Otra")])
        assert nube()["count"] == 1


class TestSinRepeticiones:
    def test_la_segunda_corrida_no_repite_las_ofertas(self, nube, canal):
        nube.fuentes["a"] = fuente("a", [oferta("1"), oferta("2", titulo="Backend Jr", empresa="Otra")])
        primera = nube()
        segunda = nube()
        assert primera["sent"] and primera["count"] == 2
        assert not segunda["sent"] and segunda["reason"] == "sin novedades"
        assert len(canal.envios) == 1

    def test_una_oferta_nueva_si_se_avisa_en_la_segunda_corrida(self, nube, canal):
        listado = [oferta("1")]
        nube.fuentes["a"] = fuente("a", listado)
        nube()
        listado.append(oferta("2", titulo="Backend Jr", empresa="Otra"))
        nube()
        assert [e["titulos"] for e in canal.envios] == [["Desarrollador Full Stack Jr"], ["Backend Jr"]]

    def test_el_estado_guarda_hashes_y_no_datos_de_las_ofertas(self, nube, tmp_path):
        nube.fuentes["a"] = fuente("a", [oferta("1")])
        nube()
        texto = (tmp_path / "estado" / "notificados.json").read_text(encoding="utf-8").lower()
        assert "desarrollador" not in texto and "acme" not in texto and "example.com" not in texto
        assert len(json.loads(texto)["notificados"]) == 1

    def test_si_el_aviso_falla_la_oferta_no_se_da_por_avisada(self, nube, canal):
        nube.fuentes["a"] = fuente("a", [oferta("1")])
        canal.falla = True
        assert nube()["errores"]
        canal.falla = False
        assert nube()["count"] == 1  # al día siguiente se reintenta

    def test_las_entradas_vencidas_se_borran_al_guardar(self, nube, tmp_path):
        ruta = tmp_path / "estado" / "notificados.json"
        ruta.parent.mkdir()
        ruta.write_text(json.dumps({"version": 1, "notificados": {"viejo": "2020-01-01"}}), encoding="utf-8")
        nube.fuentes["a"] = fuente("a", [oferta("1")])
        nube()
        assert "viejo" not in Estado.cargar(ruta).notificados

    def test_un_estado_danado_corta_la_corrida_en_vez_de_reenviar_todo(self, nube, canal, tmp_path):
        ruta = tmp_path / "estado" / "notificados.json"
        ruta.parent.mkdir()
        ruta.write_text("{roto", encoding="utf-8")
        nube.fuentes["a"] = fuente("a", [oferta("1")])
        with pytest.raises(ValueError, match="dañado"):
            nube()
        assert canal.envios == []


class TestContextoDelResumen:
    def test_el_resumen_en_ci_no_incluye_links_al_panel(self, nube, canal):
        nube.fuentes["a"] = fuente("a", [oferta("1")])
        nube()
        assert canal.envios[0]["contexto"].con_panel is False

    def test_el_resumen_dice_que_fuentes_fallaron_y_la_corrida_sigue(self, nube, canal, cfg):
        cfg["busqueda"]["fuentes_ci"] = ["a", "rota"]
        nube.fuentes["a"] = fuente("a", [oferta("1")])
        nube.fuentes["rota"] = fuente("rota", falla="403 bloqueado")
        r = nube()
        assert r["sent"] and r["fuentes_fallidas"] == ["Rota"]
        assert canal.envios[0]["contexto"].fuentes_fallidas == ("Rota",)


class TestCodigoDeSalida:
    def test_sale_con_error_si_un_canal_falla_para_que_actions_avise(self, nube, canal):
        nube.fuentes["a"] = fuente("a", [oferta("1")])
        canal.falla = True
        assert ci.main() == 1

    def test_sale_bien_si_todo_funciona(self, nube, canal, monkeypatch, tmp_path):
        nube.fuentes["a"] = fuente("a", [oferta("1")])
        monkeypatch.setenv("RADAR_DB", str(tmp_path / "radar_x.db"))
        assert ci.main() == 0


def test_el_resumen_de_ci_funciona_sin_panel_ni_navegador(nube, monkeypatch):
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: pytest.fail("no debe abrir el navegador"))
    nube.fuentes["a"] = fuente("a", [oferta("1")])
    assert nube()["sent"]
    assert db.get_meta("ultimo_resumen")
