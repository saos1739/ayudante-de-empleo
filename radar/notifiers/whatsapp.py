"""Canal de WhatsApp.

El canal (formato del mensaje, partición, pausas) es independiente del proveedor que lo entrega. Hoy hay uno,
CallMeBot (gratis, uso personal: sólo manda a tu propio número, en texto plano). Para sumar Twilio o la Meta
Cloud API más adelante alcanza con una clase nueva que implemente `ProveedorWhatsApp` y registrarla en
`PROVEEDORES`; nada de lo demás cambia.

CallMeBot (https://www.callmebot.com/blog/free-api-whatsapp-messages/):
    GET https://api.callmebot.com/whatsapp.php?phone=<tel con código de país>&text=<urlencoded>&apikey=<clave>
Su documentación no publica el largo máximo del mensaje, los límites de envío ni el formato de las respuestas.
Por eso el largo y la pausa entre mensajes son configurables y conservadores
(`notificaciones.whatsapp_max_caracteres`, `notificaciones.whatsapp_pausa_seg`), y los errores se detectan por
el código HTTP y por palabras de error en la respuesta.
"""

import os
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date, datetime

import requests

from .base import Notificador, Resultado
from .formato import etiqueta, puntaje

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"
MAX_OFERTAS = 5
MAX_CARACTERES = 900
PAUSA_SEG = 5.0
TIMEOUT_SEG = 30

_RESPUESTA_DE_ERROR = re.compile(r"\b(error|invalid|incorrect|not valid)\b", re.IGNORECASE)

_pausar = time.sleep  # los tests lo reemplazan para no esperar


class WhatsAppError(Exception):
    """Falla al enviar por WhatsApp. El mensaje nunca incluye la apikey ni el teléfono completo."""


class ProveedorWhatsApp(ABC):
    @abstractmethod
    def configurado(self) -> bool:
        """True si están las credenciales del proveedor."""

    @abstractmethod
    def enviar_texto(self, texto: str) -> None:
        """Entrega un mensaje de texto plano. Levanta WhatsAppError si no se pudo."""


class CallMeBot(ProveedorWhatsApp):
    """Lee WHATSAPP_PHONE y CALLMEBOT_APIKEY del entorno en cada uso (el panel puede cambiarlas)."""

    @staticmethod
    def telefono() -> str:
        return re.sub(r"[\s().-]", "", os.environ.get("WHATSAPP_PHONE", ""))

    @staticmethod
    def apikey() -> str:
        return os.environ.get("CALLMEBOT_APIKEY", "").strip()

    def configurado(self) -> bool:
        return bool(self.telefono() and self.apikey())

    def _sin_secretos(self, texto: str) -> str:
        """Respuesta del servidor en una línea corta y sin la apikey ni el teléfono."""
        texto = re.sub(r"<[^>]+>", " ", texto)
        for secreto in (self.apikey(), self.telefono()):
            if secreto:
                texto = texto.replace(secreto, "***")
        return re.sub(r"\s+", " ", texto).strip()[:200]

    def enviar_texto(self, texto: str) -> None:
        if not self.configurado():
            raise WhatsAppError("Falta configurar WHATSAPP_PHONE y CALLMEBOT_APIKEY.")
        try:
            r = requests.get(
                CALLMEBOT_URL,
                params={"phone": self.telefono(), "text": texto, "apikey": self.apikey()},
                timeout=TIMEOUT_SEG,
            )
        except requests.RequestException as e:
            # El texto de la excepción de requests incluye la URL completa (con la apikey): no se propaga.
            raise WhatsAppError(f"no se pudo conectar con CallMeBot ({type(e).__name__})") from None
        cuerpo = self._sin_secretos(r.text)
        if r.status_code != 200:
            raise WhatsAppError(f"CallMeBot respondió HTTP {r.status_code}: {cuerpo}")
        if _RESPUESTA_DE_ERROR.search(r.text):
            raise WhatsAppError(f"CallMeBot rechazó el mensaje: {cuerpo}")


PROVEEDORES: dict[str, type[ProveedorWhatsApp]] = {"callmebot": CallMeBot}


def enmascarar(telefono: str) -> str:
    """Deja sólo los últimos 4 dígitos (***1234) para poder poner el número en logs sin exponerlo."""
    digitos = re.sub(r"\D", "", telefono)
    return "***" + digitos[-4:] if digitos else "***"


def _bloque(posicion: int, job, max_caracteres: int) -> str:
    """Una oferta: puntaje, etiqueta, título, empresa, modalidad y link. Si no entra, se acorta el título."""
    marca = etiqueta(job)
    prefijo = f"{posicion}) [{puntaje(job)}] " + (f"{marca} · " if marca else "")
    detalle = f"{job['company'] or 'Empresa no informada'} · {job['modality'] or job['location'] or 'Modalidad no informada'}"
    resto = f"\n{detalle}\n{job['url'] or ''}"
    titulo = job["title"]
    disponible = max_caracteres - len(prefijo) - len(resto)
    if len(titulo) > disponible:
        titulo = titulo[: max(disponible - 1, 10)].rstrip() + "…"
    return prefijo + titulo + resto


def armar_mensajes(ofertas: Sequence, hoy: date, hay_mail: bool, max_caracteres: int = MAX_CARACTERES,
                   max_ofertas: int = MAX_OFERTAS) -> list[tuple[str, list[int]]]:
    """Arma los mensajes del resumen como [(texto, ids de las ofertas que lleva)].

    Encabezado con fecha y cantidad, las `max_ofertas` de mejor puntaje (las recibe ya ordenadas) y el cierre
    «+N más en tu mail». Si todo junto supera `max_caracteres` se parte en varios mensajes sin cortar ofertas.
    """
    total = len(ofertas)
    incluidas = ofertas[:max_ofertas]
    plural = "" if total == 1 else "s"
    encabezado = f"Radar de Empleo · {hoy:%d/%m/%Y} · {total} oferta{plural} nueva{plural}"
    # La primera oferta comparte mensaje con el encabezado: se acorta contando ese espacio.
    piezas = [
        (_bloque(i, job, max_caracteres - (len(encabezado) + 2 if i == 1 else 0)), job["id"])
        for i, job in enumerate(incluidas, 1)
    ]
    restantes = total - len(incluidas)
    if restantes and hay_mail:
        piezas.append((f"+{restantes} más en tu mail", None))

    mensajes: list[tuple[str, list[int]]] = []
    texto, ids = encabezado, []
    for pieza, oferta_id in piezas:
        if len(texto) + 2 + len(pieza) > max_caracteres:
            mensajes.append((texto, ids))
            texto, ids = pieza, []
        else:
            texto += "\n\n" + pieza
        if oferta_id is not None:
            ids.append(oferta_id)
    mensajes.append((texto, ids))
    return mensajes


class WhatsAppNotificador(Notificador):
    nombre = "whatsapp"

    def __init__(self, cfg: dict | None = None, proveedor: ProveedorWhatsApp | None = None):
        super().__init__(cfg)
        n = self.cfg.get("notificaciones", {})
        self.max_caracteres = int(n.get("whatsapp_max_caracteres", MAX_CARACTERES))
        self.pausa = float(n.get("whatsapp_pausa_seg", PAUSA_SEG))
        self.hay_mail = "email" in (n.get("canales") or ["email"])
        clase = PROVEEDORES.get(n.get("whatsapp_proveedor", "callmebot"))
        self.proveedor = proveedor or (clase() if clase else None)

    def configurado(self) -> bool:
        return self.proveedor is not None and self.proveedor.configurado()

    def _proveedor(self) -> ProveedorWhatsApp:
        if self.proveedor is None:
            raise WhatsAppError(f"Proveedor de WhatsApp desconocido ({', '.join(PROVEEDORES)} disponibles).")
        return self.proveedor

    def enviar(self, ofertas: Sequence) -> Resultado:
        """Manda las mejores ofertas. Si falla un mensaje intermedio, informa las que sí llegaron."""
        if not ofertas:
            return Resultado(self.nombre, False, [], "sin ofertas nuevas")
        proveedor = self._proveedor()
        mensajes = armar_mensajes(ofertas, datetime.now().date(), self.hay_mail, self.max_caracteres)
        avisadas: list[int] = []
        for i, (texto, ids) in enumerate(mensajes):
            if i:
                _pausar(self.pausa)
            try:
                proveedor.enviar_texto(texto)
            except WhatsAppError as e:
                if not avisadas:
                    raise
                return Resultado(self.nombre, True, avisadas, f"parcial: llegaron {i} de {len(mensajes)} mensajes ({e})")
            avisadas += ids
        return Resultado(self.nombre, True, avisadas)

    def enviar_prueba(self) -> None:
        self._proveedor().enviar_texto("Radar de Empleo: mensaje de prueba. Si lo ves, WhatsApp quedó configurado.")
