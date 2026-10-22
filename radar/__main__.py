"""Punto de entrada:
    python -m radar panel        abre el panel web local
    python -m radar buscar       busca ofertas una vez
    python -m radar resumen      busca y envía el resumen diario por correo (si no se envió hoy)
    python -m radar probar-mail  envía un correo de prueba
    python -m radar recalcular   recalcula puntajes tras cambiar filtros
"""

import sys


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else "panel"
    if cmd == "panel":
        from .web import serve
        serve(open_browser="--no-browser" not in sys.argv)
    elif cmd == "buscar":
        from . import runner
        runner.run_search("consola")
    elif cmd == "resumen":
        from . import db, notify, runner
        db.init_db()
        if db.get_meta("ultimo_resumen") == __import__("datetime").date.today().isoformat() and "--forzar" not in sys.argv:
            print("El resumen de hoy ya se envió.")
            return
        runner.run_search("resumen diario")
        print(notify.send_digest(force="--forzar" in sys.argv))
    elif cmd == "probar-mail":
        from . import notify
        notify.send_test()
        print("Correo de prueba enviado.")
    elif cmd == "recalcular":
        from . import db, runner
        db.init_db()
        print(f"Recalculadas {runner.rescore_all()} ofertas.")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
