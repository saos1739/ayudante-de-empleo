"""El prompt de análisis evalúa contra los 3 puestos objetivo y respeta la regla de «aplicá igual»."""

import pytest

from radar import ai

OFERTA = {"title": "Analista de Datos Jr", "company": "ACME", "location": "CABA", "modality": "Híbrido",
          "source": "Prueba", "description": "Python, Pandas y SQL. 2 años de experiencia."}


@pytest.fixture
def prompt(monkeypatch):
    """Captura el prompt que se enviaría a Gemini, sin hacer ningún pedido."""
    enviados = []

    def falso_generate(texto, temperature=0.4):
        enviados.append(texto)
        return {"puntaje": 70, "veredicto": "evaluar"}

    monkeypatch.setattr(ai, "_generate", falso_generate)
    ai.analyze(OFERTA)
    return enviados[0]


def test_evalua_contra_los_tres_puestos_objetivo(prompt):
    assert "Full Stack / Frontend / Backend" in prompt
    assert "Analista de Datos Jr / BI Jr" in prompt
    assert "Cloud Jr" in prompt
    assert '"puesto_objetivo"' in prompt


def test_respeta_la_regla_aplica_igual(prompt):
    assert "aplicá igual" in prompt
    assert "2 años: NO la descartes" in prompt
    assert "3 años o más" in prompt


def test_el_perfil_enviado_incluye_los_tres_puestos(prompt):
    assert "Analista de Datos / BI Jr o Cloud Jr" in prompt


def test_la_carta_de_plantilla_no_cita_certificaciones_que_no_estan_en_el_perfil():
    carta = ai.template_letter({"title": "Dev Jr", "company": None}, [])["carta"]
    assert "AWS Academy Cloud Foundations" in carta
    assert "Cloud Security" not in carta
