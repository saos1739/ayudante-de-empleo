"""Corrida diaria sin panel, pensada para GitHub Actions: `python -m radar resumen --ci`.

Cada corrida de Actions arranca vacía (sin base de datos), así que el estado de «qué ofertas ya avisé» viene de un
archivo (ver `estado_ci.py`) que el workflow guarda en la rama `radar-state`. Flujo:

1. Respeta `notificaciones.modo`: si los avisos los manda tu PC, esta corrida no hace nada.
2. Busca sólo en `busqueda.fuentes_ci` (LinkedIn queda afuera: bloquea IPs de servidores). Una fuente que falla se
   saltea y el resumen la menciona.
3. Las ofertas que el estado ya conoce se guardan como avisadas: no se reenvían ni gastan IA.
4. Manda el resumen por los canales configurados, sin links al panel local.
5. Anota en el estado lo que llegó, borra lo viejo y guarda.
"""

from datetime import date

from . import db, notifiers, runner
from .config import load_config
from .estado_ci import Estado


def fuentes_ci(cfg: dict) -> list:
    """`busqueda.fuentes_ci`; si no existe, las activas menos LinkedIn."""
    busqueda = cfg["busqueda"]
    if busqueda.get("fuentes_ci") is not None:
        return list(busqueda["fuentes_ci"])
    return [f for f in busqueda.get("fuentes_activas", []) if f != "linkedin"]


def resumen_ci(log=print) -> dict:
    """Corrida completa. Devuelve el resultado de `send_digest` más `fuentes_fallidas`."""
    cfg = load_config()
    if not notifiers.modo_permite(cfg, en_ci=True):
        razon = f"modo «{notifiers.modo(cfg)}»: los avisos los manda tu PC (cambiá notificaciones.modo a «ci»)"
        log(f"Corrida en la nube omitida: {razon}.")
        return {"sent": False, "count": 0, "reason": razon, "errores": [], "ids": [], "fuentes_fallidas": []}

    db.init_db()
    hoy = date.today()
    estado = Estado.cargar()
    try:
        busqueda = runner.run_search("ci", fuentes=fuentes_ci(cfg), en_ci=True,
                                     ya_avisada=lambda job: estado.ya_avisada(job, hoy))
        fallidas = busqueda.get("fuentes_fallidas", [])
        if fallidas:
            log(f"⚠ Fuentes que fallaron: {', '.join(fallidas)}")
        resultado = notifiers.send_digest(log=log, en_ci=True, fuentes_fallidas=fallidas)
        if resultado["ids"]:
            with db.connect() as conn:
                marcadores = ",".join("?" * len(resultado["ids"]))
                filas = conn.execute(f"SELECT * FROM jobs WHERE id IN ({marcadores})", resultado["ids"]).fetchall()
            estado.registrar(filas, hoy)
    finally:  # aunque algo falle, lo ya avisado se guarda para no repetirlo en la próxima corrida
        borradas = estado.podar(hoy)
        if estado.guardar():
            log(f"Estado guardado ({len(estado.notificados)} ofertas recordadas, {borradas} vencidas).")
    return {**resultado, "fuentes_fallidas": fallidas}


def main() -> int:
    """Punto de entrada de `resumen --ci`.

    Código de salida 1 si algún canal falló o si no hay ningún canal configurado (faltan los secrets):
    así Actions queda en rojo y se nota, en vez de terminar «bien» sin mandar nada.
    """
    resultado = resumen_ci()
    print({k: v for k, v in resultado.items() if k != "ids"})
    sin_canales = resultado["reason"] == "ningún canal configurado"
    return 1 if resultado["errores"] or sin_canales else 0
