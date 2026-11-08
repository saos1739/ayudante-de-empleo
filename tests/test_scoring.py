"""Reglas del scoring, con avisos de ejemplo escritos a mano (ningún pedido a internet)."""

import copy
import json

import pytest

from radar import scoring
from radar.config import CONFIG_PATH


@pytest.fixture
def cfg():
    """Copia de la config real del repo, para que cada test pueda modificarla."""
    return copy.deepcopy(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


def aviso(titulo="Desarrollador Full Stack Jr", descripcion="", ubicacion="CABA", modalidad="", **extra):
    """Aviso mínimo válido; cada test pisa sólo lo que le importa."""
    return {
        "title": titulo,
        "description": descripcion,
        "location": ubicacion,
        "modality": modalidad,
        "extra": extra,
    }


DESC_JS = "Buscamos perfil junior con JavaScript y React para sumarse a nuestro equipo de producto. "


class TestStackDesdeConfig:
    def test_sin_perfil_en_config_usa_los_defaults(self, cfg):
        del cfg["perfil"]
        r = scoring.evaluate(aviso(descripcion=DESC_JS), cfg)
        assert not r["excluded"]
        assert "React" in r["matched_stack"]

    def test_stack_core_se_lee_de_config(self, cfg):
        cfg["perfil"]["stack_core"] = {"Elixir propio": ["elixir"]}
        r = scoring.evaluate(aviso(descripcion="Junior con Elixir y JavaScript. "), cfg)
        assert r["matched_stack"] == ["Elixir propio"]

    def test_stack_ajeno_se_lee_de_config(self, cfg):
        cfg["perfil"]["stack_ajeno"] = ["fortran"]
        r = scoring.evaluate(aviso(titulo="Programador Fortran Jr", descripcion="Perfil junior, trainee. "), cfg)
        assert r["excluded"]
        assert "fortran" in r["exclude_reason"]


class TestRegla1ReactNative:
    def test_react_native_en_el_titulo_ya_no_excluye(self, cfg):
        r = scoring.evaluate(
            aviso(titulo="Desarrollador React Native Jr", descripcion="Perfil junior. Expo y TypeScript. "), cfg)
        assert not r["excluded"], r["exclude_reason"]

    @pytest.mark.parametrize("tecnologia, nombre", [
        ("React Native", "React Native"), ("TypeScript", "TypeScript"), ("Expo", "Expo"),
        ("Flask", "Flask"), ("Pandas", "Datos/BI"), ("scikit-learn", "scikit-learn"),
    ])
    def test_suma_las_tecnologias_nuevas_al_stack_propio(self, cfg, tecnologia, nombre):
        r = scoring.evaluate(aviso(descripcion=f"Perfil junior con {tecnologia}. "), cfg)
        assert nombre in r["matched_stack"]

    def test_react_native_no_figura_como_stack_ajeno(self, cfg):
        assert "react native" not in cfg["perfil"]["stack_ajeno"]
        assert "react native" not in scoring.TITULO_STACK_AJENO


class TestRegla2PuestosObjetivo:
    @pytest.mark.parametrize("palabra", [
        "analista de datos junior", "data analyst junior", "analista bi junior",
        "cloud junior", "cloud engineer junior", "devops junior",
    ])
    def test_palabras_clave_de_busqueda_incluyen_los_puestos_nuevos(self, cfg, palabra):
        assert palabra in cfg["busqueda"]["palabras_clave"]

    def test_se_mantienen_las_palabras_clave_full_stack(self, cfg):
        assert "full stack junior" in cfg["busqueda"]["palabras_clave"]

    @pytest.mark.parametrize("titulo, desc", [
        ("Analista de Datos Jr", "Trabajo con Python, Pandas y SQL. "),
        ("Analista BI Jr", "Armado de tableros en Power BI. "),
        ("Cloud Engineer Jr", "Trabajo con AWS y Google Cloud. "),
        ("DevOps Junior", "Pipelines y despliegues en AWS. "),
    ])
    def test_los_puestos_nuevos_no_se_filtran_como_no_tecnicos(self, cfg, titulo, desc):
        r = scoring.evaluate(aviso(titulo=titulo, descripcion=desc), cfg)
        assert not r["excluded"], r["exclude_reason"]


class TestRegla6Jornada:
    @pytest.mark.parametrize("texto", ["Part time", "part-time", "Medio tiempo", "Freelance"])
    def test_part_time_o_freelance_restan_sin_excluir(self, cfg, texto):
        base = scoring.evaluate(aviso(descripcion=DESC_JS), cfg)
        r = scoring.evaluate(aviso(descripcion=DESC_JS + f"Modalidad: {texto}. "), cfg)
        assert not r["excluded"], r["exclude_reason"]
        assert r["score"] < base["score"]
        assert any(m["p"] and m["p"] < 0 and "jornada" in m["t"].lower() for m in r["reasons"])

    def test_full_time_no_resta(self, cfg):
        r = scoring.evaluate(aviso(descripcion=DESC_JS + "Jornada full time. "), cfg)
        assert not any("jornada" in m["t"].lower() for m in r["reasons"])


class TestRegla3Experiencia:
    def test_hasta_un_anio_es_normal(self, cfg):
        r = scoring.evaluate(aviso(descripcion=DESC_JS + "Hasta 1 año de experiencia. "), cfg)
        assert not r["excluded"]
        assert r["etiqueta"] == "encaja"
        assert not any((m["p"] or 0) < 0 for m in r["reasons"])

    def test_dos_anios_no_excluye_y_marca_aplica_igual_con_penalizacion(self, cfg):
        base = scoring.evaluate(aviso(descripcion=DESC_JS), cfg)
        r = scoring.evaluate(aviso(descripcion=DESC_JS + "Requisitos: 2 años de experiencia en JavaScript. "), cfg)
        assert not r["excluded"], r["exclude_reason"]
        assert r["etiqueta"] == "aplicá igual"
        assert r["score"] < base["score"]
        assert any((m["p"] or 0) < 0 and "2 años" in m["t"] for m in r["reasons"])

    @pytest.mark.parametrize("anios", [3, 5])
    def test_tres_anios_o_mas_excluye(self, cfg, anios):
        r = scoring.evaluate(
            aviso(descripcion=DESC_JS + f"Requisitos: {anios} años de experiencia en JavaScript. "), cfg)
        assert r["excluded"]
        assert f"{anios}+ años" in r["exclude_reason"]
        assert r["etiqueta"] is None

    def test_sin_anios_pedidos_encaja(self, cfg):
        assert scoring.evaluate(aviso(descripcion=DESC_JS), cfg)["etiqueta"] == "encaja"


class TestRegla4RemotoDesdeElExterior:
    def test_remoto_que_acepta_latam_se_mantiene_con_penalizacion_leve(self, cfg):
        r = scoring.evaluate(
            aviso(descripcion=DESC_JS + "Trabajo 100% remoto, abierto a candidatos de LATAM. ",
                  ubicacion="Remoto - Estados Unidos", modalidad="Remoto"), cfg)
        assert not r["excluded"], r["exclude_reason"]
        assert any(m["p"] == -5 and "exterior" in m["t"].lower() for m in r["reasons"])

    def test_remoto_anywhere_se_mantiene(self, cfg):
        r = scoring.evaluate(
            aviso(descripcion=DESC_JS + "Fully remote, work from anywhere. ", ubicacion="Chile", modalidad="Remote"), cfg)
        assert not r["excluded"], r["exclude_reason"]

    def test_remoto_que_acepta_argentina_en_getonboard_se_mantiene(self, cfg):
        r = scoring.evaluate(
            aviso(descripcion=DESC_JS + "Remoto, podés vivir en Argentina. ", ubicacion="Remoto",
                  modalidad="Remoto", countries=["Chile"]), cfg)
        assert not r["excluded"], r["exclude_reason"]

    def test_remoto_que_no_aclara_si_acepta_argentina_se_excluye(self, cfg):
        r = scoring.evaluate(
            aviso(descripcion=DESC_JS + "Trabajo remoto. ", ubicacion="Colombia", modalidad="Remoto"), cfg)
        assert r["excluded"]

    def test_presencial_en_el_exterior_se_excluye_aunque_mencione_latam(self, cfg):
        r = scoring.evaluate(
            aviso(descripcion=DESC_JS + "Oficina en Madrid, abierto a LATAM. ", ubicacion="Madrid", modalidad="Presencial"),
            cfg)
        assert r["excluded"]
        assert "fuera de Argentina" in r["exclude_reason"]

    def test_hibrido_en_el_exterior_se_excluye(self, cfg):
        r = scoring.evaluate(
            aviso(descripcion=DESC_JS + "Esquema híbrido, LATAM bienvenido. ", ubicacion="Bogotá", modalidad="Híbrido"),
            cfg)
        assert r["excluded"]

    def test_remoto_que_exige_residir_en_otro_pais_se_excluye(self, cfg):
        r = scoring.evaluate(
            aviso(descripcion=DESC_JS + "100% remote, anywhere, but you must reside in the US. ",
                  ubicacion="Remoto - Estados Unidos", modalidad="Remote"), cfg)
        assert r["excluded"]
        assert "residir" in r["exclude_reason"]

    def test_oferta_argentina_no_se_ve_afectada(self, cfg):
        r = scoring.evaluate(aviso(descripcion=DESC_JS, ubicacion="Lomas de Zamora"), cfg)
        assert not r["excluded"]
        assert not any("exterior" in m["t"].lower() for m in r["reasons"])


class TestRegla5Ingles:
    @pytest.mark.parametrize("frase", [
        "Inglés intermedio.", "Inglés intermedio-avanzado.", "Upper intermediate English.",
        "Upper intermediate to advanced English.",
    ])
    def test_b2_alcanza(self, cfg, frase):
        r = scoring.evaluate(aviso(descripcion=DESC_JS + frase + " "), cfg)
        assert not r["excluded"], r["exclude_reason"]

    @pytest.mark.parametrize("frase", [
        "Inglés avanzado.", "Inglés fluido.", "Inglés bilingüe.", "Advanced English.", "Fluent English.",
        "Inglés C1.", "Inglés C2.", "English C1 required.",
    ])
    def test_siguen_excluyendo_avanzado_fluido_bilingue_c1_y_c2(self, cfg, frase):
        r = scoring.evaluate(aviso(descripcion=DESC_JS + frase + " "), cfg)
        assert r["excluded"]
        assert "inglés" in r["exclude_reason"].lower()


class TestRegla7Portfolio:
    @pytest.mark.parametrize("titulo", [
        "Desarrollador Backend Jr", "Analista de Datos Jr", "Analista BI Jr", "Cloud Engineer Jr", "DevOps Junior",
    ])
    def test_puesto_objetivo_sin_tecnologias_en_el_aviso_se_mantiene(self, cfg, titulo):
        r = scoring.evaluate(aviso(titulo=titulo, descripcion="Sumate a un equipo joven, perfil junior. "), cfg)
        assert not r["excluded"], r["exclude_reason"]

    def test_tecnologia_core_alcanza_aunque_el_titulo_no_sea_un_puesto_objetivo(self, cfg):
        r = scoring.evaluate(
            aviso(titulo="Analista Funcional Jr", descripcion="Perfil junior. Consultas SQL y documentación. "), cfg)
        assert not r["excluded"], r["exclude_reason"]

    def test_ni_tecnologia_ni_puesto_objetivo_se_descarta(self, cfg):
        r = scoring.evaluate(
            aviso(titulo="Analista Funcional Jr", descripcion="Perfil junior. Relevamiento de software interno. "), cfg)
        assert r["excluded"]
        assert "puestos objetivo" in r["exclude_reason"]

    def test_trainee_it_sin_tecnologia_ni_puesto_se_descarta(self, cfg):
        r = scoring.evaluate(
            aviso(titulo="Trainee IT", descripcion="Programa trainee en el área de tecnología. "), cfg)
        assert r["excluded"]

    def test_los_puestos_objetivo_se_leen_de_config(self, cfg):
        cfg["perfil"]["puestos_objetivo"] = {"Otro": ["tester"]}
        r = scoring.evaluate(aviso(titulo="Tester Jr", descripcion="Perfil junior, testing manual. "), cfg)
        assert not r["excluded"], r["exclude_reason"]
        r = scoring.evaluate(aviso(titulo="Analista de Datos Jr", descripcion="Perfil junior. "), cfg)
        assert r["excluded"]
