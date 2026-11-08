"""Estado entre corridas de GitHub Actions: qué ofertas ya se avisaron.

Cada corrida de Actions arranca sin base de datos, así que sin esto se reenviaría todo cada día. El estado es un
`notificados.json` con sólo hashes y la fecha en que se vieron por última vez (ni títulos, ni empresas, ni el estado
de tus postulaciones). El workflow lo guarda en la rama huérfana `radar-state`.

Una oferta se olvida a los 45 días de no aparecer. Mientras siga publicada, se renueva la fecha de vez en cuando
para que no se vuelva a avisar sólo porque pasó el tiempo.
"""

import hashlib
import json
import os
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

from .config import BASE_DIR

VERSION = 1
DIAS_DE_VIDA = 45
DIAS_PARA_RENOVAR = 15  # evita reescribir el archivo todos los días por una fecha


def ruta_estado() -> Path:
    """RADAR_ESTADO, o `.estado/notificados.json` dentro del repo (carpeta ignorada por git)."""
    return Path(os.environ.get("RADAR_ESTADO") or BASE_DIR / ".estado" / "notificados.json")


def hash_oferta(job) -> str:
    """Identifica una oferta entre corridas y entre portales (título + empresa).

    Si la empresa es confidencial no alcanza el título, así que se usa el identificador del portal.
    Acepta un dict o una fila de la base.
    """
    fp = job["fingerprint"] or ""
    clave = f"fp:{fp}" if fp and not fp.endswith("|") else f"uid:{job['source']}:{job['uid']}"
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()[:16]


class Estado:
    def __init__(self, notificados: dict[str, str] | None = None):
        self.notificados: dict[str, str] = dict(notificados or {})
        self._original = dict(self.notificados)

    @classmethod
    def cargar(cls, ruta: Path | None = None) -> "Estado":
        """Estado guardado, o uno vacío si todavía no hay (primera corrida). Un archivo roto es un error."""
        ruta = ruta or ruta_estado()
        if not ruta.exists():
            return cls()
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            notificados = datos["notificados"]
            if not isinstance(notificados, dict):
                raise TypeError("notificados no es un objeto")
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(f"El archivo de estado {ruta} está dañado ({e}); revisalo antes de seguir "
                             "para no reenviar todas las ofertas.") from None
        return cls(notificados)

    def ya_avisada(self, job, hoy: date | None = None) -> bool:
        """True si la oferta ya se avisó. Si todavía está publicada, renueva su fecha cuando se está por vencer."""
        hoy = hoy or date.today()
        h = hash_oferta(job)
        visto = self.notificados.get(h)
        if visto is None:
            return False
        if (hoy - date.fromisoformat(visto)).days >= DIAS_PARA_RENOVAR:
            self.notificados[h] = hoy.isoformat()
        return True

    def registrar(self, jobs: Iterable, hoy: date | None = None) -> None:
        """Anota como avisadas estas ofertas (dicts o filas de la base)."""
        fecha = (hoy or date.today()).isoformat()
        for job in jobs:
            self.notificados[hash_oferta(job)] = fecha

    def podar(self, hoy: date | None = None) -> int:
        """Borra las entradas de más de 45 días. Devuelve cuántas borró."""
        limite = ((hoy or date.today()) - timedelta(days=DIAS_DE_VIDA)).isoformat()
        vencidas = [h for h, visto in self.notificados.items() if visto < limite]
        for h in vencidas:
            del self.notificados[h]
        return len(vencidas)

    def guardar(self, ruta: Path | None = None) -> bool:
        """Escribe el archivo sólo si hubo cambios (así el workflow no hace commits vacíos)."""
        if self.notificados == self._original:
            return False
        ruta = ruta or ruta_estado()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        contenido = {"version": VERSION, "notificados": dict(sorted(self.notificados.items()))}
        temporal = ruta.with_suffix(".tmp")
        temporal.write_text(json.dumps(contenido, indent=1) + "\n", encoding="utf-8")
        temporal.replace(ruta)
        self._original = dict(self.notificados)
        return True
