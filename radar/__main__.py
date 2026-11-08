"""Punto de entrada:
    python -m radar panel        abre el panel web local
    python -m radar buscar       busca ofertas una vez
    python -m radar resumen      busca y envía el resumen diario (si no se envió hoy)
    python -m radar resumen --ci igual, pero sin panel y con el estado de GitHub Actions (ver radar/ci.py)
    python -m radar probar-mail  envía un correo de prueba
    python -m radar probar-whatsapp  envía un mensaje de prueba por WhatsApp
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
    elif cmd == "resumen" and "--ci" in sys.argv:
        from . import ci
        sys.exit(ci.main())
    elif cmd == "resumen":
        from . import db, notifiers, runner
        from .config import load_config
        modo = notifiers.modo(load_config())
        if modo != "local" and "--forzar" not in sys.argv:
            print(f"Los avisos los manda GitHub Actions (notificaciones.modo = «{modo}»). Usá --forzar para enviar igual.")
            return
        db.init_db()
        if db.get_meta("ultimo_resumen") == __import__("datetime").date.today().isoformat() and "--forzar" not in sys.argv:
            print("El resumen de hoy ya se envió.")
            return
        runner.run_search("resumen diario")
        print(notifiers.send_digest(force="--forzar" in sys.argv))
    elif cmd == "probar-mail":
        from . import notifiers
        notifiers.send_test("email")
        print("Correo de prueba enviado.")
    elif cmd == "probar-whatsapp":
        from . import notifiers
        from .notifiers.whatsapp import WhatsAppError
        try:
            notifiers.send_test("whatsapp")
        except WhatsAppError as e:
            print(f"No se pudo enviar el mensaje de prueba: {e}")
            sys.exit(1)
        print("Mensaje de prueba enviado: revisá tu WhatsApp.")
    elif cmd == "recalcular":
        from . import db, runner
        db.init_db()
        print(f"Recalculadas {runner.rescore_all()} ofertas.")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
