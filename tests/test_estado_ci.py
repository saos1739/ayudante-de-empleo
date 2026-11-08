"""Estado entre corridas: sólo hashes, poda a los 45 días y archivo estable."""

import json
from datetime import date, timedelta

import pytest

from radar import db, estado_ci
from radar.estado_ci import Estado, hash_oferta
from radar.util import fingerprint
from tests.helpers import guardar

HOY = date(2026, 11, 8)


def job(uid="1", fuente="getonbrd", titulo="Desarrollador Full Stack Jr", empresa="ACME"):
    return {"uid": uid, "source": fuente, "title": titulo, "company": empresa,
            "fingerprint": fingerprint(titulo, empresa)}


class TestHash:
    def test_es_estable_y_corto(self):
        assert hash_oferta(job()) == hash_oferta(job())
        assert len(hash_oferta(job())) == 16

    def test_la_misma_oferta_en_dos_portales_tiene_el_mismo_hash(self):
        assert hash_oferta(job(uid="1", fuente="getonbrd")) == hash_oferta(job(uid="99", fuente="bumeran"))

    def test_ofertas_distintas_tienen_hash_distinto(self):
        assert hash_oferta(job()) != hash_oferta(job(titulo="Backend Jr"))
        assert hash_oferta(job()) != hash_oferta(job(empresa="Otra SA"))

    def test_con_empresa_confidencial_se_usa_el_id_del_portal(self):
        a = job(uid="1", empresa="")
        b = job(uid="2", empresa="")
        assert hash_oferta(a) != hash_oferta(b)  # mismo título, distintas ofertas
        assert hash_oferta(a) == hash_oferta(job(uid="1", empresa=""))

    def test_funciona_con_filas_de_la_base(self, base):
        fila = db.get_job(guardar("Perfil junior con JavaScript. ", uid="x"))
        assert len(hash_oferta(fila)) == 16


class TestArchivo:
    def test_sin_archivo_el_estado_arranca_vacio(self, tmp_path):
        assert Estado.cargar(tmp_path / "no_existe.json").notificados == {}

    def test_guardar_y_cargar_conserva_las_entradas(self, tmp_path):
        ruta = tmp_path / "estado" / "notificados.json"
        estado = Estado()
        estado.registrar([job(), job(titulo="Backend Jr")], HOY)
        assert estado.guardar(ruta)
        assert Estado.cargar(ruta).notificados == estado.notificados

    def test_el_archivo_no_guarda_titulos_ni_empresas_ni_urls(self, tmp_path):
        ruta = tmp_path / "n.json"
        estado = Estado()
        estado.registrar([job(titulo="Desarrollador Full Stack Jr", empresa="ACME")], HOY)
        estado.guardar(ruta)
        texto = ruta.read_text(encoding="utf-8").lower()
        for privado in ("desarrollador", "acme", "http", "full stack"):
            assert privado not in texto
        assert set(json.loads(texto)) == {"version", "notificados"}

    def test_sin_cambios_no_reescribe_el_archivo(self, tmp_path):
        ruta = tmp_path / "n.json"
        inicial = Estado()
        inicial.registrar([job()], HOY)
        inicial.guardar(ruta)
        otra_vez = Estado.cargar(ruta)
        assert otra_vez.ya_avisada(job(), HOY)  # dentro del plazo: no cambia la fecha
        assert not otra_vez.guardar(ruta)

    def test_el_contenido_es_estable_sin_importar_el_orden(self, tmp_path):
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        uno, dos = job(), job(titulo="Backend Jr")
        e1, e2 = Estado(), Estado()
        e1.registrar([uno, dos], HOY)
        e2.registrar([dos, uno], HOY)
        e1.guardar(a)
        e2.guardar(b)
        assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")

    def test_un_archivo_danado_es_un_error_claro_y_no_un_estado_vacio(self, tmp_path):
        ruta = tmp_path / "n.json"
        ruta.write_text("{esto no es json", encoding="utf-8")
        with pytest.raises(ValueError, match="dañado"):
            Estado.cargar(ruta)
        ruta.write_text('{"version": 1}', encoding="utf-8")
        with pytest.raises(ValueError, match="dañado"):
            Estado.cargar(ruta)

    def test_la_ruta_sale_de_la_variable_de_entorno(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RADAR_ESTADO", str(tmp_path / "x.json"))
        assert estado_ci.ruta_estado() == tmp_path / "x.json"


class TestVencimiento:
    def test_se_borran_las_entradas_de_mas_de_45_dias(self):
        estado = Estado({"viejo": (HOY - timedelta(days=46)).isoformat(),
                         "limite": (HOY - timedelta(days=45)).isoformat(),
                         "reciente": (HOY - timedelta(days=3)).isoformat()})
        assert estado.podar(HOY) == 1
        assert set(estado.notificados) == {"limite", "reciente"}

    def test_una_oferta_que_sigue_publicada_renueva_su_fecha(self):
        vieja = job()
        estado = Estado({hash_oferta(vieja): (HOY - timedelta(days=30)).isoformat()})
        assert estado.ya_avisada(vieja, HOY)
        estado.podar(HOY)
        assert estado.notificados[hash_oferta(vieja)] == HOY.isoformat()

    def test_una_oferta_que_ya_no_aparece_se_olvida_y_puede_volver_a_avisarse(self):
        vieja = job()
        estado = Estado({hash_oferta(vieja): (HOY - timedelta(days=60)).isoformat()})
        estado.podar(HOY)
        assert not estado.ya_avisada(vieja, HOY)

    def test_una_oferta_nueva_no_figura_como_avisada(self):
        assert not Estado().ya_avisada(job(), HOY)
