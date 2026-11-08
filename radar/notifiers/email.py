"""Canal de correo: resumen diario con las ofertas nuevas que encajan con el perfil (Gmail SMTP)."""

import os
import smtplib
import ssl
from collections.abc import Sequence
from datetime import datetime
from email.message import EmailMessage
from html import escape

from ..config import destinatario
from .base import Notificador, Resultado
from .formato import etiqueta, motivos, puntaje

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
        "destinatario": destinatario(),
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


def _etiqueta_html(job) -> str:
    texto = etiqueta(job)
    if not texto:
        return ""
    colores = "background:#fef3c7;color:#92400e" if texto == "aplicá igual" else "background:#dbeafe;color:#1e40af"
    return (f'<span style="display:inline-block;padding:2px 8px;margin-left:6px;border-radius:6px;'
            f'{colores};font-size:12px;font-weight:600">{escape(texto)}</span>')


def _job_html(job) -> str:
    meta = " · ".join(escape(x) for x in (job["company"], job["location"], job["modality"], job["salary"]) if x)
    reasons = "".join(f"<li>{escape(r)}</li>" for r in motivos(job))
    return f"""
    <tr><td style="padding:14px 0;border-bottom:1px solid #e5e7eb">
      <div style="font-size:16px;font-weight:600;color:#111827">
        <span style="display:inline-block;min-width:38px;padding:2px 6px;margin-right:6px;border-radius:6px;
              background:#dcfce7;color:#166534;font-size:13px;text-align:center">{puntaje(job)}</span>
        {escape(job["title"])}
        {_etiqueta_html(job)}
      </div>
      <div style="color:#4b5563;font-size:13px;margin:4px 0">{meta} · <i>{escape(job["source"])}</i></div>
      <ul style="margin:6px 0 8px 18px;padding:0;color:#374151;font-size:13px">{reasons}</ul>
      <a href="{escape(job["url"] or "")}" style="color:#2563eb;font-size:13px">Ver aviso en {escape(job["source"])}</a>
      &nbsp;·&nbsp;
      <a href="{PANEL_URL}/oferta/{job["id"]}" style="color:#2563eb;font-size:13px">Abrir en el panel (carta lista)</a>
    </td></tr>"""


def _job_text(job) -> str:
    meta = " · ".join(x for x in (job["company"], job["location"], job["modality"], job["salary"]) if x)
    reasons = "\n".join(f"   - {r}" for r in motivos(job))
    marca = f" ({etiqueta(job)})" if etiqueta(job) else ""
    return f"[{puntaje(job)}]{marca} {job['title']}\n   {meta} ({job['source']})\n{reasons}\n   {job['url']}\n"


class EmailNotificador(Notificador):
    nombre = "email"

    def configurado(self) -> bool:
        return configured()

    def enviar(self, ofertas: Sequence) -> Resultado:
        """Envía el resumen. Sin ofertas manda el aviso de «sin novedades» (el orquestador decide si corresponde)."""
        st = _settings(self.cfg)
        today = datetime.now().strftime("%d/%m/%Y")
        n = len(ofertas)
        if ofertas:
            plural = "s" if n != 1 else ""
            subject = f"Radar de Empleo · {n} oferta{plural} nueva{plural} para vos ({today})"
            intro = (f"Encontré <b>{n}</b> oferta{plural} nueva{plural} "
                     "en Argentina (Junior / Trainee / Pasantía) que encajan con tu CV.")
            rows = "".join(_job_html(j) for j in ofertas)
            body_txt = "\n".join(_job_text(j) for j in ofertas)
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
        return Resultado(self.nombre, True, [j["id"] for j in ofertas])

    def enviar_prueba(self) -> None:
        st = _settings(self.cfg)
        _send(
            st["destinatario"],
            "Radar de Empleo · Correo de prueba",
            "<p>¡Funciona! A partir de ahora vas a recibir el resumen diario de ofertas nuevas "
            f"a las {st['hora']}:00 aprox.</p>",
            f"¡Funciona! Vas a recibir el resumen diario de ofertas nuevas a las {st['hora']}:00 aprox.",
        )
