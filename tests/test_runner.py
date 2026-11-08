"""Runner: fuentes que fallan, fuentes de CI y ofertas ya avisadas. Fuentes falsas: ningún pedido a internet."""

import pytest

from radar import db, runner
from radar.util import fingerprint

DESC = "Perfil junior con JavaScript y React. "


def oferta(uid, titulo="Desarrollador Full Stack Jr", empresa="ACME"):
    return {"uid": uid, "source": "falsa", "title": titulo, "company": empresa, "location": "CABA",
            "modality": "Híbrido", "url": f"https://example.com/{uid}", "description": DESC, "salary": None,
            "published_at": None, "fingerprint": fingerprint(titulo, empresa), "extra": {}}


def fuente(nombre, ofertas=(), falla=None, necesita_detalle=False):
    """Clase de fuente de mentira. Anota en `Fuente.detalles` cuántas veces se pidió el detalle."""

    class Fuente:
        name = nombre
        label = nombre.capitalize()
        needs_detail = necesita_detalle
        detalles = 0

        def __init__(self, cfg, log):
            pass

        def search(self):
            if falla:
                raise RuntimeError(falla)
            yield from ofertas

        def fetch_detail(self, job):
            Fuente.detalles += 1
            return job

    return Fuente


@pytest.fixture
def entorno(base, monkeypatch):
    """Sin IA, sin esperas y con un registro de fuentes vacío que cada test completa."""
    monkeypatch.setattr(runner.ai, "available", lambda: False)
    monkeypatch.setattr(runner, "pause", lambda cfg: None)
    monkeypatch.setattr(runner, "log", lambda *_: None)
    registro = {}
    monkeypatch.setattr(runner, "ALL_SOURCES", registro)
    return registro


def filas():
    with db.connect() as conn:
        return conn.execute("SELECT * FROM jobs ORDER BY id").fetchall()


class TestFuentesQueFallan:
    def test_una_fuente_caida_se_saltea_y_la_corrida_sigue(self, entorno):
        entorno["rota"] = fuente("rota", falla="403 bloqueado")
        entorno["sana"] = fuente("sana", [oferta("a")])
        r = runner.run_search("prueba", fuentes=["rota", "sana"])
        assert r["new"] == 1
        assert r["fuentes_fallidas"] == ["Rota"]
        assert any("403 bloqueado" in e for e in r["errors"])

    def test_una_fuente_sin_resultados_se_marca_como_sospechosa(self, entorno):
        entorno["vacia"] = fuente("vacia", [])
        r = runner.run_search("prueba", fuentes=["vacia"])
        assert r["fuentes_fallidas"] == ["Vacia (sin resultados)"]

    def test_si_todo_sale_bien_no_hay_fuentes_fallidas(self, entorno):
        entorno["sana"] = fuente("sana", [oferta("a")])
        assert runner.run_search("prueba", fuentes=["sana"])["fuentes_fallidas"] == []

    def test_un_error_al_crear_la_fuente_tampoco_corta_la_corrida(self, entorno):
        class Mala:
            name, label = "mala", "Mala"

            def __init__(self, cfg, log):
                raise RuntimeError("sin configurar")

        entorno["mala"] = Mala
        entorno["sana"] = fuente("sana", [oferta("a")])
        r = runner.run_search("prueba", fuentes=["mala", "sana"])
        assert r["new"] == 1 and r["fuentes_fallidas"] == ["Mala"]


class TestSeleccionDeFuentes:
    def test_sin_parametro_usa_las_fuentes_activas_de_la_config(self, entorno, monkeypatch):
        monkeypatch.setattr(runner, "load_config", lambda: {
            "busqueda": {"fuentes_activas": ["a"]}, "filtros": runner_cfg()["filtros"]})
        entorno["a"] = fuente("a", [oferta("1")])
        entorno["b"] = fuente("b", [oferta("2", empresa="Otra")])
        assert runner.run_search("prueba")["new"] == 1

    def test_el_parametro_fuentes_pisa_a_las_activas(self, entorno):
        entorno["a"] = fuente("a", [oferta("1")])
        entorno["b"] = fuente("b", [oferta("2", empresa="Otra")])
        runner.run_search("prueba", fuentes=["b"])
        assert [f["uid"] for f in filas()] == ["2"]


def runner_cfg():
    from radar.config import load_config
    return load_config()


class TestOfertasYaAvisadas:
    def test_una_oferta_ya_avisada_se_guarda_como_avisada_y_no_cuenta_como_nueva(self, entorno):
        entorno["a"] = fuente("a", [oferta("1"), oferta("2", titulo="Backend Jr", empresa="Otra")])
        r = runner.run_search("prueba", fuentes=["a"], ya_avisada=lambda job: job["uid"] == "1")
        assert r["new"] == 1 and r["relevant"] == 1
        avisada, nueva = filas()
        assert avisada["notified_at"] is not None
        assert nueva["notified_at"] is None

    def test_a_las_ya_avisadas_no_se_les_pide_el_detalle(self, entorno):
        listado = [oferta("1") | {"description": ""}, oferta("2", titulo="Backend Jr", empresa="Otra") | {"description": ""}]
        clase = entorno["a"] = fuente("a", listado, necesita_detalle=True)
        runner.run_search("prueba", fuentes=["a"], ya_avisada=lambda job: job["uid"] == "1")
        assert clase.detalles == 1  # sólo la oferta nueva

    def test_sin_ya_avisada_se_pide_el_detalle_de_todas(self, entorno):
        listado = [oferta("1") | {"description": ""}, oferta("2", titulo="Backend Jr", empresa="Otra") | {"description": ""}]
        clase = entorno["a"] = fuente("a", listado, necesita_detalle=True)
        runner.run_search("prueba", fuentes=["a"])
        assert clase.detalles == 2

    def test_las_avisadas_no_vuelven_a_los_pendientes_de_un_resumen(self, entorno):
        from radar import notifiers
        entorno["a"] = fuente("a", [oferta("1")])
        runner.run_search("prueba", fuentes=["a"], ya_avisada=lambda job: True)
        assert notifiers.pending_jobs(0) == []

    def test_sin_ya_avisada_todo_lo_nuevo_queda_pendiente(self, entorno):
        from radar import notifiers
        entorno["a"] = fuente("a", [oferta("1")])
        runner.run_search("prueba", fuentes=["a"])
        assert len(notifiers.pending_jobs(0)) == 1


class TestAnalisisConIA:
    def test_en_ci_no_se_analizan_las_ofertas_ya_avisadas(self, base):
        from tests.helpers import guardar
        nueva, avisada = guardar(DESC, uid="n"), guardar(DESC, uid="v", titulo="Backend Jr")
        with db.connect() as conn:
            conn.execute("UPDATE jobs SET notified_at = '2026-01-01' WHERE id = ?", (avisada,))
        todas = {f["id"] for f in db.pending_ai(0, 10)}
        solo_nuevas = {f["id"] for f in db.pending_ai(0, 10, sin_avisadas=True)}
        assert todas == {nueva, avisada}
        assert solo_nuevas == {nueva}
