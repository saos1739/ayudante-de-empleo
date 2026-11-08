"""Interfaz común de los canales de aviso (correo, WhatsApp, y los que se sumen más adelante)."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field

from ..config import load_config


@dataclass
class Resultado:
    """Qué pasó al enviar por un canal. `ids_avisados` son las ofertas que de verdad llegaron."""

    canal: str
    enviado: bool
    ids_avisados: list[int] = field(default_factory=list)
    motivo: str = "ok"


class Notificador(ABC):
    """Un canal de aviso. El orquestador (`radar.notifiers`) los usa a todos por igual."""

    nombre: str

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg if cfg is not None else load_config()

    @abstractmethod
    def configurado(self) -> bool:
        """True si están las credenciales necesarias para enviar."""

    @abstractmethod
    def enviar(self, ofertas: Sequence) -> Resultado:
        """Envía el resumen con estas ofertas (ya ordenadas por puntaje). Si falla, levanta una excepción."""

    @abstractmethod
    def enviar_prueba(self) -> None:
        """Manda un mensaje de prueba para verificar la configuración."""
