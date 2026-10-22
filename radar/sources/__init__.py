"""Fuentes de ofertas. Cada módulo expone una clase con search() y, si hace falta, fetch_detail()."""

from .computrabajo import Computrabajo
from .empleosit import EmpleosIT
from .getonbrd import GetOnBoard
from .linkedin import LinkedIn
from .navent import Bumeran, Zonajobs
from .talent import Talent

ALL_SOURCES = {
    cls.name: cls
    for cls in (GetOnBoard, Bumeran, Zonajobs, Computrabajo, LinkedIn, EmpleosIT, Talent)
}
