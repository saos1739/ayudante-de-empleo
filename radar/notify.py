"""Aviso por correo: resumen diario con las ofertas nuevas que encajan con el perfil (Gmail SMTP)."""

import json
import os
import smtplib
import ssl
from datetime import date, datetime
from email.message import EmailMessage
from html import escape

from . import db
from .config import load_config

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
PANEL_URL = "http://127.0.0.1:5050"


def gmail_user() -> str:
    return os.environ.get("GMAIL_USER", "").strip()


def gmail_password() -> str:
    # Las contraseñas de aplicación de Google se muestran con espacios: se quitan.
    return os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()


def configured() -> bool:
    return bool(gmail_user() and gmail_password())


def _settings(cfg: dict) -> dict:
    n = cfg.get("notificaciones", {})
    return {
        "habilitado": n.get("email_habilitado", True),
        "destinatario": n.get("destinatario") or gmail_user(),
        "hora": int(n.get("hora_resumen", 8)),
        "minimo": int(n.get("puntaje_minimo_email", 60)),
        "enviar_vacio": bool(n.get("enviar_si_no_hay_novedades", False)),
    }


def _send(to: str, subject: str, html: str, text: str) -> None:
    if not configured():
        raise RuntimeError("Falta configurar GMAIL_USER y GMAIL_APP_PASSWORD (Configuración → Correo).")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Radar de Empleo <{gmail_user()}>"
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=30) as s:
        s.login(gmail_user(), gmail_password())
        s.send_message(msg)


def _score(job) -> int:
    return job["ai_score"] if job["ai_score"] is not None else job["rule_score"]


def _reasons(job, limit: int = 3) -> list:
    try:
        items = json.loads(job["rule_reasons"] or "[]")
    except ValueError:
        return []
    return [r["t"] for r in items if (r.get("p") or 0) > 0][:limit]


def _job_html(job) -> str:
    meta = " · ".join(escape(x) for x in (job["company"], job["location"], job["modality"], job["salary"]) if x)
    reasons = "".join(f"<li>{escape(r)}</li>" for r in _reasons(job))
    return f"""
    <tr><td style="padding:14px 0;border-bottom:1px solid #e5e7eb">
      <div style="font-size:16px;font-weight:600;color:#111827">
        <span style="display:inline-block;min-width:38px;padding:2px 6px;margin-right:6px;border-radius:6px;
              background:#dcfce7;color:#166534;font-size:13px;text-align:center">{_score(job)}</span>
        {escape(job["title"])}
      </div>
      <div style="color:#4b5563;font-size:13px;margin:4px 0">{meta} · <i>{escape(job["source"])}</i></div>
      <ul style="margin:6px 0 8px 18px;padding:0;color:#374151;font-size:13px">{reasons}</ul>
      <a href="{escape(job["url"] or "")}" style="color:#2563eb;font-size:13px">Ver aviso en {escape(job["source"])}</a>
      &nbsp;·&nbsp;
      <a href="{PANEL_URL}/oferta/{job["id"]}" style="color:#2563eb;font-size:13px">Abrir en el panel (carta lista)</a>
    </td></tr>"""


def _job_text(job) -> str:
    meta = " · ".join(x for x in (job["company"], job["location"], job["modality"], job["salary"]) if x)
    reasons = "\n".join(f"   - {r}" for r in _reasons(job))
    return f"[{_score(job)}] {job['title']}\n   {meta} ({job['source']})\n{reasons}\n   {job['url']}\n"


def pending_jobs(minimo: int):
    with db.connect() as conn:
        return conn.execute(
            """SELECT * FROM jobs
               WHERE excluded = 0 AND notified_at IS NULL AND status IN ('nueva', 'interesa')
                 AND COALESCE(ai_score, rule_score) >= ?
               ORDER BY COALESCE(ai_score, rule_score) DESC, found_at DESC LIMIT 25""",
            (minimo,),
        ).fetchall()


def send_digest(force: bool = False, log=print) -> dict:
    """Envía el resumen con las ofertas aún no avisadas. Devuelve {'sent': bool, 'count': n, 'reason': str}."""
    db.init_db()
    cfg = load_config()
    st = _settings(cfg)
    if not st["habilitado"] and not force:
        return {"sent": False, "count": 0, "reason": "avisos por correo deshabilitados"}
    if not configured():
        return {"sent": False, "count": 0, "reason": "correo sin configurar"}

    jobs = pending_jobs(st["minimo"])
    if not jobs and not (st["enviar_vacio"] or force):
        db.set_meta("ultimo_resumen", date.today().isoformat())
        log("Correo: sin ofertas nuevas que encajen; no se envía resumen.")
        return {"sent": False, "count": 0, "reason": "sin novedades"}

    today = datetime.now().strftime("%d/%m/%Y")
    if jobs:
        subject = f"Radar de Empleo · {len(jobs)} oferta{'s' if len(jobs) != 1 else ''} nueva{'s' if len(jobs) != 1 else ''} para vos ({today})"
        intro = (f"Encontré <b>{len(jobs)}</b> oferta{'s' if len(jobs) != 1 else ''} nueva{'s' if len(jobs) != 1 else ''} "
                 "en Argentina (Junior / Trainee / Pasantía) que encajan con tu CV.")
        rows = "".join(_job_html(j) for j in jobs)
        body_txt = "\n".join(_job_text(j) for j in jobs)
    else:
        subject = f"Radar de Empleo · Sin ofertas nuevas hoy ({today})"
        intro = "Hoy no aparecieron ofertas nuevas que encajen con tu perfil. El radar sigue buscando."
        rows = ""
        body_txt = "Hoy no aparecieron ofertas nuevas que encajen con tu perfil."

    html = f"""<div style="font-family:Segoe UI,Arial,sans-serif;max-width:640px;margin:auto;color:#111827">
      <h2 style="margin:0 0 6px">Radar de Empleo</h2>
      <p style="color:#374151;margin:0 0 10px">{intro}</p>
      <table style="width:100%;border-collapse:collapse">{rows}</table>
      <p style="color:#6b7280;font-size:12px;margin-top:18px">
        Los links “Abrir en el panel” funcionan con el Radar abierto en tu PC (iniciar_radar.bat).
        Puntaje mínimo para avisar: {st["minimo"]}. Podés cambiarlo en Configuración → Correo.
      </p></div>"""

    _send(st["destinatario"], subject, html, f"{subject}\n\n{body_txt}")
    ids = [j["id"] for j in jobs]
    with db.connect() as conn:
        conn.executemany("UPDATE jobs SET notified_at = ? WHERE id = ?", [(db.now(), i) for i in ids])
    db.set_meta("ultimo_resumen", date.today().isoformat())
    log(f"Correo: resumen enviado a {st['destinatario']} con {len(ids)} ofertas.")
    return {"sent": True, "count": len(ids), "reason": "ok"}


def send_test() -> None:
    cfg = load_config()
    st = _settings(cfg)
    _send(
        st["destinatario"],
        "Radar de Empleo · Correo de prueba",
        "<p>¡Funciona! A partir de ahora vas a recibir el resumen diario de ofertas nuevas "
        f"a las {st['hora']}:00 aprox.</p>",
        f"¡Funciona! Vas a recibir el resumen diario de ofertas nuevas a las {st['hora']}:00 aprox.",
    )


def digest_due(cfg: dict | None = None) -> bool:
    """True si ya pasó la hora del resumen y todavía no se envió hoy."""
    cfg = cfg or load_config()
    st = _settings(cfg)
    if not (st["habilitado"] and configured()):
        return False
    return datetime.now().hour >= st["hora"] and db.get_meta("ultimo_resumen") != date.today().isoformat()
