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
