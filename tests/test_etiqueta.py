"""La etiqueta («encaja» / «aplicá igual») y sus motivos se guardan en la base y salen en el mail."""

import json
import sqlite3

from radar import db, scoring
from radar.config import load_config
from radar.notifiers import email as canal_email
from radar.notifiers import formato
from tests.helpers import guardar, oferta

DESC = "Perfil junior con JavaScript y React. "


def test_la_etiqueta_se_guarda_al_insertar(base):
    assert db.get_job(guardar(DESC))["etiqueta"] == "encaja"
    assert db.get_job(guardar(DESC + "2 años de experiencia. ", uid="b"))["etiqueta"] == "aplicá igual"


def test_recalcular_actualiza_la_etiqueta(base):
    job_id = guardar(DESC)
    job = oferta("a", DESC + "2 años de experiencia. ")
    db.update_rule_score(job_id, scoring.evaluate(job, load_config()))
    assert db.get_job(job_id)["etiqueta"] == "aplicá igual"


def test_migra_una_base_anterior_sin_la_columna(tmp_path, monkeypatch):
    ruta = tmp_path / "vieja.db"
    monkeypatch.setenv("RADAR_DB", str(ruta))
    lineas = [linea for linea in db.SCHEMA.splitlines() if not linea.strip().startswith("etiqueta ")]
    esquema_anterior = "\n".join(lineas)
    with sqlite3.connect(ruta) as conn:
        conn.executescript(esquema_anterior)
        assert "etiqueta" not in {fila[1] for fila in conn.execute("PRAGMA table_info(jobs)")}
    db.init_db()
    with sqlite3.connect(ruta) as conn:
        assert "etiqueta" in {fila[1] for fila in conn.execute("PRAGMA table_info(jobs)")}


def test_el_mail_muestra_etiqueta_y_advertencias(base):
    fila = db.get_job(guardar(DESC + "2 años de experiencia. "))
    html, texto = canal_email._job_html(fila), canal_email._job_text(fila)
    assert "aplicá igual" in html and "aplicá igual" in texto
    assert "⚠ Piden 2 años de experiencia" in html and "⚠ Piden 2 años de experiencia" in texto


def test_el_mail_no_inventa_etiqueta_en_ofertas_viejas(base):
    job_id = guardar(DESC)
    with sqlite3.connect(base) as conn:
        conn.execute("UPDATE jobs SET etiqueta = NULL WHERE id = ?", (job_id,))
    fila = db.get_job(job_id)
    assert formato.etiqueta(fila) == ""
    assert "encaja" not in canal_email._job_text(fila).split("\n")[0]


def test_motivos_a_favor_siguen_limitados_a_tres(base):
    fila = db.get_job(guardar(DESC))
    a_favor = [m for m in formato.motivos(fila) if not m.startswith("⚠")]
    assert 0 < len(a_favor) <= 3
    assert json.loads(fila["rule_reasons"])
