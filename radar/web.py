"""Panel web local (Flask) para revisar, decidir y preparar postulaciones."""

import json
import threading
import webbrowser
from datetime import date, datetime

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from . import ai, db, runner, scoring
from .config import CV_PATH, gemini_key, load_config, load_cv, save_config, save_env_value

app = Flask(__name__)
app.secret_key = "radar-empleo-local"
PORT = 5050

TABS = [
    ("nueva", "Nuevas"),
    ("interesa", "Me interesan"),
    ("postulada", "Postulé"),
    ("entrevista", "Entrevista"),
    ("descartada", "Descartadas"),
]


@app.template_filter("fromjson")
def fromjson(value):
    try:
        return json.loads(value) if value else None
    except (TypeError, ValueError):
        return None


@app.template_filter("ago")
def ago(value):
    if not value:
        return ""
    try:
        d = datetime.fromisoformat(value[:19]).date() if "T" in value else date.fromisoformat(value[:10])
    except ValueError:
        return value
    days = (date.today() - d).days
    if days <= 0:
        return "hoy"
    if days == 1:
        return "ayer"
    if days < 30:
        return f"hace {days} días"
    return d.strftime("%d/%m/%Y")


def score_of(job):
    return job["ai_score"] if job["ai_score"] is not None else job["rule_score"]


app.jinja_env.globals.update(score_of=score_of, ESTADOS=db.ESTADOS)


@app.context_processor
def inject_globals():
    return {"ai_ready": ai.available(), "last_run": db.last_run(), "running": runner.is_running()}


# ---------------- vistas ----------------

@app.route("/")
def index():
    cfg = load_config()
    min_default = cfg["filtros"].get("puntaje_minimo_visible", 35)
    status = request.args.get("estado", "nueva")
    show_excluded = status == "filtradas"
    source = request.args.get("fuente") or None
    q = request.args.get("q") or None
    order = request.args.get("orden", "score")
    try:
        min_score = int(request.args.get("min", min_default))
    except ValueError:
        min_score = min_default
    jobs = db.list_jobs(status=None if show_excluded else status, source=source, min_score=min_score,
                        q=q, show_excluded=show_excluded, order=order)
    return render_template(
        "index.html", jobs=jobs, tabs=TABS, status=status, counts=db.counts(min_score),
        sources=db.sources(), source=source, q=q or "", order=order, min_score=min_score,
    )


@app.route("/oferta/<int:job_id>")
def job_detail(job_id):
    job = db.get_job(job_id)
    if not job:
        flash("La oferta no existe.", "error")
        return redirect(url_for("index"))
    return render_template("job.html", job=job, back=request.args.get("back") or url_for("index"))


@app.post("/oferta/<int:job_id>/estado")
def job_status(job_id):
    db.set_status(job_id, request.form["estado"])
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True)
    return redirect(request.form.get("next") or url_for("job_detail", job_id=job_id))


@app.post("/oferta/<int:job_id>/notas")
def job_notes(job_id):
    db.set_notes(job_id, request.form.get("notas", ""))
    flash("Notas guardadas.", "ok")
    return redirect(url_for("job_detail", job_id=job_id) + "#notas")


@app.post("/oferta/<int:job_id>/analizar")
def job_analyze(job_id):
    job = db.get_job(job_id)
    try:
        db.set_ai(job_id, ai.analyze(job))
        flash("Análisis con IA listo.", "ok")
    except ai.AIError as e:
        flash(str(e), "error")
    return redirect(url_for("job_detail", job_id=job_id) + "#ia")


@app.post("/oferta/<int:job_id>/carta")
def job_letter(job_id):
    job = db.get_job(job_id)
    use_ai = request.form.get("modo") != "plantilla" and ai.available()
    try:
        if use_ai:
            out = ai.write_letter(job)
        else:
            extra = json.loads(job["extra"] or "{}")
            matched = scoring.evaluate({**dict(job), "extra": extra}, load_config())["matched_stack"]
            out = ai.template_letter(job, matched)
        db.set_letter(job_id, out.get("carta", ""), out.get("mensaje_recruiter", ""), use_ai,
                      out.get("preguntas_probables", []))
        flash("Carta generada. Revisala y editala antes de enviarla.", "ok")
    except ai.AIError as e:
        flash(str(e), "error")
    return redirect(url_for("job_detail", job_id=job_id) + "#carta")


@app.post("/oferta/<int:job_id>/carta/guardar")
def job_letter_save(job_id):
    job = db.get_job(job_id)
    db.set_letter(job_id, request.form.get("carta", ""), request.form.get("mensaje", ""),
                  bool(job["letter_by_ai"]))
    flash("Cambios guardados.", "ok")
    return redirect(url_for("job_detail", job_id=job_id) + "#carta")


@app.post("/buscar")
def search_now():
    if runner.start_background("manual"):
        flash("Búsqueda iniciada. Podés seguir usando el panel.", "ok")
    else:
        flash("Ya hay una búsqueda en curso.", "info")
    return redirect(request.form.get("next") or url_for("index"))


@app.get("/api/estado")
def api_state():
    s = runner.STATE
    last = db.last_run()
    return jsonify(
        running=s["running"], source=s["source"], found=s["found"], new=s["new"],
        relevant=s["relevant"], log=list(s["log"])[-12:],
        last_run=dict(last) if last else None,
    )


@app.route("/config", methods=["GET", "POST"])
def config_view():
    cfg = load_config()
    if request.method == "POST":
        action = request.form.get("accion")
        if action == "busqueda":
            kws = [k.strip() for k in request.form.get("palabras", "").splitlines() if k.strip()]
            cfg["busqueda"]["palabras_clave"] = kws or cfg["busqueda"]["palabras_clave"]
            cfg["busqueda"]["fuentes_activas"] = request.form.getlist("fuentes")
            cfg["busqueda"]["intervalo_horas"] = float(request.form.get("intervalo", 6) or 0)
            cfg["busqueda"]["paginas_por_palabra"] = int(request.form.get("paginas", 1) or 1)
            cfg["filtros"]["puntaje_minimo_visible"] = int(request.form.get("minimo", 35) or 0)
            excl = [k.strip() for k in request.form.get("excluir", "").splitlines() if k.strip()]
            if excl:
                cfg["filtros"]["excluir_titulo"] = excl
            save_config(cfg)
            n = runner.rescore_all()
            flash(f"Configuración guardada. Se recalcularon {n} ofertas.", "ok")
        elif action == "ia":
            key = request.form.get("clave", "").strip()
            if key:
                save_env_value("GEMINI_API_KEY", key)
            elif request.form.get("borrar_clave"):
                save_env_value("GEMINI_API_KEY", "")
            cfg["ia"]["habilitada"] = bool(request.form.get("habilitada"))
            cfg["ia"]["analizar_automaticamente"] = bool(request.form.get("auto"))
            cfg["ia"]["max_analisis_por_busqueda"] = int(request.form.get("max_ia", 12) or 0)
            cfg["ia"]["puntaje_minimo_para_ia"] = int(request.form.get("min_ia", 50) or 0)
            save_config(cfg)
            flash("Configuración de IA guardada.", "ok")
        elif action == "cv":
            CV_PATH.parent.mkdir(parents=True, exist_ok=True)
            CV_PATH.write_text(request.form.get("cv", ""), encoding="utf-8")
            flash("CV actualizado. La IA usará esta versión.", "ok")
        elif action in ("correo", "correo_prueba", "correo_ahora"):
            from . import notify
            if action == "correo":
                user = request.form.get("gmail_user", "").strip()
                pwd = request.form.get("gmail_pass", "").replace(" ", "").strip()
                if user:
                    save_env_value("GMAIL_USER", user)
                if pwd:
                    save_env_value("GMAIL_APP_PASSWORD", pwd)
                n = cfg.setdefault("notificaciones", {})
                n["email_habilitado"] = bool(request.form.get("habilitado"))
                n["destinatario"] = request.form.get("destinatario", "").strip() or user
                n["hora_resumen"] = int(request.form.get("hora", 8) or 8)
                n["puntaje_minimo_email"] = int(request.form.get("minimo_email", 60) or 0)
                n["enviar_si_no_hay_novedades"] = bool(request.form.get("vacio"))
                save_config(cfg)
                flash("Configuración de correo guardada.", "ok")
            try:
                if action == "correo_prueba":
                    notify.send_test()
                    flash("Correo de prueba enviado. Revisá tu bandeja (y Spam).", "ok")
                elif action == "correo_ahora":
                    r = notify.send_digest(force=True)
                    flash(f"Resumen enviado con {r['count']} ofertas." if r["sent"] else f"No se envió: {r['reason']}.", "ok" if r["sent"] else "info")
            except Exception as e:
                flash(f"Error al enviar el correo: {e}", "error")
            return redirect(url_for("config_view") + "#correo")
        return redirect(url_for("config_view"))
    from .sources import ALL_SOURCES
    from . import notify
    return render_template("config.html", cfg=cfg, all_sources=ALL_SOURCES, cv=load_cv(),
                           has_key=bool(gemini_key()), mail_ok=notify.configured(),
                           gmail_user=notify.gmail_user(), last_digest=db.get_meta("ultimo_resumen"))


# ---------------- arranque ----------------

def serve(open_browser: bool = True) -> None:
    db.init_db()
    threading.Thread(target=runner.scheduler_loop, daemon=True).start()
    url = f"http://127.0.0.1:{PORT}"
    try:
        print(f"\n  Radar de Empleo corriendo en {url}  (cerrar esta ventana para detenerlo)\n", flush=True)
    except Exception:
        pass
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
