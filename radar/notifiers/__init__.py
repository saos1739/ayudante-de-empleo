"""Avisos de ofertas nuevas por varios canales.

Cada canal implementa `Notificador` (ver `base.py`). Este módulo es el orquestador: elige las ofertas
pendientes, las manda por cada canal configurado y marca como avisada toda oferta que llegó por al menos
un canal. Si un canal falla se registra en el log y se sigue con el otro.
"""

from datetime import date, datetime

from .. import db
from ..config import load_config
from .base import Notificador, Resultado
from .email import EmailNotificador
from .whatsapp import WhatsAppNotificador

# Para sumar un canal nuevo: implementar `Notificador` y registrarlo acá.
CANALES: dict[str, type[Notificador]] = {
    "email": EmailNotificador,
    "whatsapp": WhatsAppNotificador,
}

CANALES_POR_DEFECTO = ["email"]


def _ajustes(cfg: dict) -> dict:
    n = cfg.get("notificaciones", {})
    return {
        "habilitado": n.get("email_habilitado", True),  # interruptor general del resumen diario
        "canales": [c for c in (n.get("canales") or CANALES_POR_DEFECTO) if c in CANALES],
        "hora": int(n.get("hora_resumen", 8)),
        "minimo": int(n.get("puntaje_minimo_email", 60)),
        "enviar_vacio": bool(n.get("enviar_si_no_hay_novedades", False)),
    }


def crear_notificadores(cfg: dict) -> list[Notificador]:
    """Un notificador por cada canal listado en `notificaciones.canales`."""
    return [CANALES[nombre](cfg) for nombre in _ajustes(cfg)["canales"]]


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
    """Envía el resumen con las ofertas aún no avisadas por todos los canales configurados.

    Devuelve {'sent': bool, 'count': n, 'reason': str, 'errores': [str]}. `sent` es True si llegó por al
    menos un canal; `count` es la cantidad de ofertas que quedaron marcadas como avisadas.
    """
    db.init_db()
    cfg = load_config()
    st = _ajustes(cfg)
    if not st["habilitado"] and not force:
        return {"sent": False, "count": 0, "reason": "avisos deshabilitados", "errores": []}

    notificadores = []
    for notificador in crear_notificadores(cfg):
        if notificador.configurado():
            notificadores.append(notificador)
        else:
            log(f"{notificador.nombre}: sin configurar, se omite.")
    if not notificadores:
        return {"sent": False, "count": 0, "reason": "ningún canal configurado", "errores": []}

    jobs = pending_jobs(st["minimo"])
    if not jobs and not (st["enviar_vacio"] or force):
        db.set_meta("ultimo_resumen", date.today().isoformat())
        log("Avisos: sin ofertas nuevas que encajen; no se envía resumen.")
        return {"sent": False, "count": 0, "reason": "sin novedades", "errores": []}

    resultados: list[Resultado] = []
    errores: list[str] = []
    for notificador in notificadores:
        try:
            resultado = notificador.enviar(jobs)
        except Exception as e:  # un canal caído no corta a los demás
            log(f"⚠ {notificador.nombre}: {e}")
            errores.append(f"{notificador.nombre}: {e}")
            continue
        resultados.append(resultado)
        if resultado.enviado:
            log(f"{notificador.nombre}: resumen enviado con {len(resultado.ids_avisados)} ofertas.")
            if resultado.motivo != "ok":  # llegó, pero incompleto
                log(f"⚠ {notificador.nombre}: {resultado.motivo}")
                errores.append(f"{notificador.nombre}: {resultado.motivo}")

    llegaron = [r for r in resultados if r.enviado]
    if not llegaron:
        motivos = [f"{r.canal}: {r.motivo}" for r in resultados] + errores
        return {"sent": False, "count": 0, "reason": "; ".join(motivos) or "sin novedades", "errores": errores}

    ids = sorted({i for r in llegaron for i in r.ids_avisados})
    with db.connect() as conn:
        conn.executemany("UPDATE jobs SET notified_at = ? WHERE id = ?", [(db.now(), i) for i in ids])
    db.set_meta("ultimo_resumen", date.today().isoformat())
    return {"sent": True, "count": len(ids), "reason": "ok", "errores": errores}


def send_test(canal: str) -> None:
    """Mensaje de prueba por un canal (para `probar-mail`, `probar-whatsapp` y el panel)."""
    CANALES[canal](load_config()).enviar_prueba()


def digest_due(cfg: dict | None = None) -> bool:
    """True si ya pasó la hora del resumen y todavía no se envió hoy."""
    cfg = cfg or load_config()
    st = _ajustes(cfg)
    if not (st["habilitado"] and any(n.configurado() for n in crear_notificadores(cfg))):
        return False
    return datetime.now().hour >= st["hora"] and db.get_meta("ultimo_resumen") != date.today().isoformat()
