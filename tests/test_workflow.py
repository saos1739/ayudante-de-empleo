"""El workflow diario cumple lo que pide la spec: horario, concurrencia, permisos, secrets y estado."""

import re
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
RUTA = RAIZ / ".github" / "workflows" / "radar-diario.yml"


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(RUTA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pasos(workflow):
    return workflow["jobs"]["radar"]["steps"]


def paso(pasos, nombre):
    return next(p for p in pasos if p.get("name") == nombre)


def test_corre_todos_los_dias_a_las_10_17_de_argentina(workflow):
    disparadores = workflow.get("on") or workflow[True]  # YAML 1.1 lee «on» como True
    (programado,) = disparadores["schedule"]
    assert programado["cron"] == "17 13 * * *"  # 13:17 UTC = 10:17 UTC-3


def test_evita_el_minuto_cero(workflow):
    disparadores = workflow.get("on") or workflow[True]
    minuto = disparadores["schedule"][0]["cron"].split()[0]
    assert minuto != "0"


def test_se_puede_correr_a_mano(workflow):
    assert "workflow_dispatch" in (workflow.get("on") or workflow[True])


def test_dos_corridas_no_se_pisan(workflow):
    assert workflow["concurrency"]["group"] == "radar-diario"
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_permiso_de_escritura_solo_para_el_contenido(workflow):
    assert workflow["permissions"] == {"contents": "write"}


def test_usa_python_3_12_con_cache_de_pip(pasos):
    configuracion = next(p for p in pasos if str(p.get("uses", "")).startswith("actions/setup-python"))
    assert configuracion["with"] == {"python-version": "3.12", "cache": "pip"}


def test_ejecuta_el_resumen_sin_panel(pasos):
    assert paso(pasos, "Buscar y avisar")["run"].strip() == "python -m radar resumen --ci"


def test_pasa_todos_los_secrets_que_pide_la_spec(pasos):
    entorno = paso(pasos, "Buscar y avisar")["env"]
    for secreto in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "RADAR_DESTINATARIO", "WHATSAPP_PHONE",
                    "CALLMEBOT_APIKEY", "GEMINI_API_KEY"):
        assert entorno[secreto] == f"${{{{ secrets.{secreto} }}}}"


def test_no_hay_valores_secretos_escritos_en_el_workflow():
    texto = RUTA.read_text(encoding="utf-8")
    sin_referencias = re.sub(r"\$\{\{[^}]*\}\}", "", texto)
    assert not re.search(r"AIza|ghp_|app.?password[ \t]*[:=][ \t]*\w{8,}", sin_referencias, re.IGNORECASE)


def test_la_base_y_el_estado_se_guardan_en_lugares_temporales_conocidos(pasos):
    entorno = paso(pasos, "Buscar y avisar")["env"]
    assert entorno["RADAR_DB"].startswith("${{ runner.temp }}")
    assert entorno["RADAR_ESTADO"].endswith(".estado/notificados.json")


def test_el_estado_vive_en_la_rama_huerfana_radar_state(pasos):
    traer = paso(pasos, "Traer el estado")["run"]
    guardar = paso(pasos, "Guardar el estado")["run"]
    assert "radar-state" in traer and "--orphan" in traer
    assert "git push origin HEAD:radar-state" in guardar
    assert not re.search(r"git push\b.*(--force|--force-with-lease|\s-f\b)", guardar)


def test_el_estado_se_guarda_aunque_falle_el_aviso(pasos):
    assert paso(pasos, "Guardar el estado")["if"] == "always()"


def test_solo_se_versiona_el_archivo_de_hashes_en_la_rama_de_estado(pasos):
    assert "git add notificados.json" in paso(pasos, "Guardar el estado")["run"]


def test_la_carpeta_de_estado_esta_ignorada_en_main():
    assert ".estado/" in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()


@pytest.fixture(scope="module")
def tests_yml():
    return yaml.safe_load((RAIZ / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))


class TestWorkflowDeTests:
    def test_corre_en_cada_push_y_en_cada_pull_request(self, tests_yml):
        disparadores = tests_yml.get("on") or tests_yml[True]
        assert "push" in disparadores and "pull_request" in disparadores

    def test_corre_ruff_y_pytest_con_python_3_12(self, tests_yml):
        pasos = tests_yml["jobs"]["tests"]["steps"]
        comandos = [p["run"] for p in pasos if "run" in p]
        assert "ruff check ." in comandos
        assert "python -m pytest -q" in comandos
        python = next(p for p in pasos if str(p.get("uses", "")).startswith("actions/setup-python"))
        assert python["with"]["python-version"] == "3.12"

    def test_instala_las_dependencias_de_desarrollo(self, tests_yml):
        comandos = [p["run"] for p in tests_yml["jobs"]["tests"]["steps"] if "run" in p]
        assert "pip install -r requirements-dev.txt" in comandos

    def test_solo_necesita_permiso_de_lectura(self, tests_yml):
        assert tests_yml["permissions"] == {"contents": "read"}
