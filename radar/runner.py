"""Orquestador de búsquedas: recorre fuentes, filtra, puntúa, guarda y lanza el análisis con IA."""

import threading
import time
import traceback
from collections import deque
from datetime import datetime

from . import ai, db, scoring
from .config import load_config
from .sources import ALL_SOURCES
from .util import pause

import sys

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


def run_search(trigger: str = "manual") -> dict:
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
        log(f"Búsqueda iniciada ({trigger}).")

        for name in cfg["busqueda"]["fuentes_activas"]:
            cls = ALL_SOURCES.get(name)
            if not cls:
                continue
            source = cls(cfg, log)
            STATE["source"] = source.label
            log(f"→ {source.label}: buscando…")
            found = new = 0
            try:
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
            except Exception as e:
                msg = f"{source.label}: {e}"
                errors.append(msg)
                log(f"   ⚠ {msg}")
                traceback.print_exc()

        STATE["source"] = "IA"
        _auto_analyze(cfg, errors)
        db.finish_run(run_id, STATE["found"], STATE["new"], STATE["relevant"], errors)
        log(f"Listo: {STATE['new']} ofertas nuevas, {STATE['relevant']} relevantes para vos.")
        return {"found": STATE["found"], "new": STATE["new"], "relevant": STATE["relevant"], "errors": errors}
    finally:
        STATE.update(running=False, source=None)
        _lock.release()


def _auto_analyze(cfg: dict, errors: list) -> None:
    ia = cfg.get("ia", {})
    if not (ia.get("analizar_automaticamente") and ai.available()):
        return
    pending = db.pending_ai(ia.get("puntaje_minimo_para_ia", 50), ia.get("max_analisis_por_busqueda", 12))
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
            from . import notify
            if not STATE["running"] and notify.digest_due(cfg):
                try:
                    notify.send_digest(log=log)
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
