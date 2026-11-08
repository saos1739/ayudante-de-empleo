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
