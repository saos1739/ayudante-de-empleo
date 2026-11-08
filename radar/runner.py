"""Orquestador de búsquedas: recorre fuentes, filtra, puntúa, guarda y lanza el análisis con IA."""

import sys
import threading
import time
import traceback
from collections import deque
from datetime import datetime

from . import ai, db, scoring
from .config import load_config
from .sources import ALL_SOURCES
from .util import pause

_lock = threading.Lock()
STATE = {
    "running": False,
    "started_at": None,
    "source": None,
    "found": 0,
    "new": 0,
    "relevant": 0,
    "log": deque(maxlen=200),
}


def log(msg: str) -> None:
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    STATE["log"].append(line)
    try:
        print(line, flush=True)
    except Exception:
        try:
            enc = getattr(sys.stdout, "encoding", None) or "ascii"
            print(line.encode(enc, errors="replace").decode(enc), flush=True)
        except Exception:
            pass


def is_running() -> bool:
    return STATE["running"]


def start_background(trigger: str = "manual") -> bool:
    """Lanza una búsqueda en un hilo. Devuelve False si ya había una corriendo."""
    if STATE["running"]:
        return False
    threading.Thread(target=run_search, args=(trigger,), daemon=True).start()
    return True


def run_search(trigger: str = "manual", fuentes: list | None = None, ya_avisada=None, en_ci: bool = False) -> dict:
    """Recorre las fuentes y guarda las ofertas nuevas.

    `fuentes` pisa `busqueda.fuentes_activas` (CI usa `fuentes_ci`). `ya_avisada(job) -> bool` dice si una oferta
    ya se avisó en una corrida anterior: se guarda como avisada y no se le pide el detalle ni se le gasta IA.
    Una fuente que falla se registra y se saltea; el resultado trae `fuentes_fallidas` con sus nombres.
    """
    if not _lock.acquire(blocking=False):
        log("Ya hay una búsqueda en curso.")
        return {}
    try:
        STATE.update(running=True, started_at=datetime.now().isoformat(timespec="seconds"),
                     found=0, new=0, relevant=0, source=None)
        STATE["log"].clear()
        db.init_db()
        cfg = load_config()
        min_visible = cfg["filtros"].get("puntaje_minimo_visible", 35)
        run_id = db.start_run(trigger)
        errors = []
        fuentes_fallidas = []
        log(f"Búsqueda iniciada ({trigger}).")

        for name in fuentes if fuentes is not None else cfg["busqueda"]["fuentes_activas"]:
            cls = ALL_SOURCES.get(name)
            if not cls:
                continue
            label = getattr(cls, "label", name)
            found = new = 0
            try:
                source = cls(cfg, log)
                STATE["source"] = source.label
                log(f"→ {source.label}: buscando…")
                for job in source.search():
                    if not job or not job.get("title"):
                        continue
                    found += 1
                    STATE["found"] += 1
                    if db.get_by_uid(job["uid"]):
                        db.touch(job["uid"])
                        continue
                    dup = db.find_duplicate(job["fingerprint"], job["source"])
                    if dup:
                        db.add_alt_url(dup["id"], job["source"], job["url"])
                        continue
                    pre = scoring.evaluate(job, cfg)
                    if ya_avisada and ya_avisada(job):
                        db.insert_job(job, pre, ya_avisada=True)  # ya llegó antes: sin detalle, sin IA, sin aviso
                        continue
                    # Sólo se pide el detalle de las que pasan el filtro por título/zona (ahorra pedidos).
                    if source.needs_detail and not pre["excluded"] and not job["description"]:
                        try:
                            job = source.fetch_detail(job)
                            pause(cfg)
                        except Exception as e:  # el detalle es opcional
                            log(f"   detalle no disponible: {e}")
                    result = scoring.evaluate(job, cfg) if job["description"] else pre
                    db.insert_job(job, result)
                    new += 1
                    STATE["new"] += 1
                    if not result["excluded"] and result["score"] >= min_visible:
                        STATE["relevant"] += 1
                log(f"   {source.label}: {found} vistas, {new} nuevas.")
                if not found:  # sin excepción pero sin nada: típico de un portal que bloquea la IP
                    fuentes_fallidas.append(f"{label} (sin resultados)")
            except Exception as e:
                msg = f"{label}: {e}"
                errors.append(msg)
                fuentes_fallidas.append(label)
                log(f"   ⚠ {msg}")
                traceback.print_exc()

        STATE["source"] = "IA"
        _auto_analyze(cfg, errors, sin_avisadas=en_ci)
        db.finish_run(run_id, STATE["found"], STATE["new"], STATE["relevant"], errors)
        log(f"Listo: {STATE['new']} ofertas nuevas, {STATE['relevant']} relevantes para vos.")
        return {"found": STATE["found"], "new": STATE["new"], "relevant": STATE["relevant"], "errors": errors,
                "fuentes_fallidas": fuentes_fallidas}
    finally:
        STATE.update(running=False, source=None)
        _lock.release()


def _auto_analyze(cfg: dict, errors: list, sin_avisadas: bool = False) -> None:
    ia = cfg.get("ia", {})
    if not (ia.get("analizar_automaticamente") and ai.available()):
        return
    pending = db.pending_ai(ia.get("puntaje_minimo_para_ia", 50), ia.get("max_analisis_por_busqueda", 12),
                            sin_avisadas=sin_avisadas)
    if not pending:
        return
    log(f"IA: analizando {len(pending)} ofertas prometedoras…")
    for job in pending:
        try:
            db.set_ai(job["id"], ai.analyze(job))
            time.sleep(4)  # respeta el límite gratuito por minuto
        except ai.AIRateLimit as e:
            log(f"   IA pausada: {e}")
            break
        except Exception as e:
            errors.append(f"IA: {e}")
            log(f"   ⚠ IA: {e}")
            break


def rescore_all() -> int:
    """Recalcula el puntaje por reglas de todas las ofertas (tras cambiar filtros)."""
    import json
    cfg = load_config()
    n = 0
    for row in db.all_jobs():
        job = dict(row)
        job["extra"] = json.loads(row["extra"] or "{}")
        db.update_rule_score(row["id"], scoring.evaluate(job, cfg))
        n += 1
    return n


def scheduler_loop() -> None:
    """Corre en segundo plano mientras el panel está abierto."""
    cfg = load_config()
    if cfg["busqueda"].get("buscar_al_iniciar", True):
        last = db.last_run()
        hours = cfg["busqueda"].get("intervalo_horas", 6)
        if not last or _hours_since(last["finished_at"]) >= min(hours, 2):
            start_background("al iniciar")
    while True:
        time.sleep(60)
        try:
            cfg = load_config()
            # Resumen diario por correo (si el panel está abierto a la hora configurada)
            from . import notifiers
            if not STATE["running"] and notifiers.digest_due(cfg):
                try:
                    notifiers.send_digest(log=log)
                except Exception as e:
                    log(f"⚠ Correo: {e}")
            hours = float(cfg["busqueda"].get("intervalo_horas", 6))
            if hours <= 0 or STATE["running"]:
                continue
            last = db.last_run()
            if not last or _hours_since(last["finished_at"]) >= hours:
                start_background("automática")
        except Exception as e:
            log(f"Programador: {e}")


def _hours_since(iso: str) -> float:
    try:
        return (datetime.now() - datetime.fromisoformat(iso)).total_seconds() / 3600
    except (TypeError, ValueError):
        return 1e9
