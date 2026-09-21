"""Hablar con el motor de BIMNEMO desde la ventana nativa.

La ventana **no importa LightRAG**: le pide las cosas por HTTP al motor, que
es otro proceso. Está explicado en `docs/BIMNEMO_INTERFAZ_NATIVA.md`, pero en
corto: el reinicio del motor funciona porque el motor se puede matar y
levantar sin tocar la ventana, y son los mismos endpoints que usa la interfaz
web — un solo camino que mantener.

## Por qué `QNetworkAccessManager` y no `urllib` en un hilo

Porque es asíncrono de serie y la respuesta llega en el hilo de la interfaz.
Con `urllib` dentro de un `QThread` hay que vigilar en cada sitio que nadie
toque un widget desde el hilo equivocado, y ese fallo no avisa: la aplicación
se cierra sola, sin rastro, en el ordenador de otro.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from PySide6.QtCore import QByteArray, QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

#: Qué se considera «ha tardado demasiado». El motor contesta en
#: milisegundos salvo cuando está indexando, que puede tardar.
ESPERA_MS = 30_000


class Motor(QObject):
    """Cliente del motor local.

    Cada petición recibe dos funciones: una para cuando sale bien y otra para
    cuando no. No hay excepciones que suban hasta la interfaz — en una
    aplicación de ventanas una excepción sin recoger cierra el programa, y
    perder la ventana porque el motor tardó un segundo de más es inaceptable.
    """

    #: Se emite cuando una petición falla por algo que no es culpa de quien
    #: la pidió: el motor no está, o no contesta. La ventana lo usa para
    #: enseñar el aviso de «motor caído» en un solo sitio.
    caido = Signal(str)

    def __init__(self, base: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.base = base.rstrip("/")
        self._red = QNetworkAccessManager(self)
        self._clave: str = ""

    def usar_clave(self, clave: str) -> None:
        """La clave de acceso, si el usuario la tiene activada."""
        self._clave = clave or ""

    # -- peticiones ---------------------------------------------------------

    def get(
        self,
        ruta: str,
        bien: Callable[[Any], None],
        mal: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._lanzar("GET", ruta, None, bien, mal)

    def post(
        self,
        ruta: str,
        cuerpo: Any,
        bien: Callable[[Any], None],
        mal: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._lanzar("POST", ruta, cuerpo, bien, mal)

    def _peticion(self, ruta: str) -> QNetworkRequest:
        peticion = QNetworkRequest(QUrl(f"{self.base}{ruta}"))
        peticion.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        peticion.setTransferTimeout(ESPERA_MS)
        if self._clave:
            peticion.setRawHeader(b"X-API-Key", self._clave.encode("utf-8"))
        return peticion

    def _lanzar(
        self,
        metodo: str,
        ruta: str,
        cuerpo: Any,
        bien: Callable[[Any], None],
        mal: Optional[Callable[[str], None]],
    ) -> None:
        peticion = self._peticion(ruta)
        if metodo == "GET":
            respuesta = self._red.get(peticion)
        else:
            datos = QByteArray(json.dumps(cuerpo or {}).encode("utf-8"))
            respuesta = self._red.post(peticion, datos)

        respuesta.finished.connect(
            lambda: self._recoger(respuesta, ruta, bien, mal)
        )

    def _recoger(
        self,
        respuesta: QNetworkReply,
        ruta: str,
        bien: Callable[[Any], None],
        mal: Optional[Callable[[str], None]],
    ) -> None:
        # `deleteLater` y no `del`: la respuesta sigue viva dentro de Qt
        # mientras se ejecuta esta función, y borrarla aquí es un cierre
        # inmediato de los que no dejan ni mensaje.
        try:
            estado = respuesta.attribute(
                QNetworkRequest.HttpStatusCodeAttribute
            )
            crudo = bytes(respuesta.readAll().data())

            if respuesta.error() != QNetworkReply.NoError and not estado:
                aviso = f"El motor no responde ({respuesta.errorString()})."
                self.caido.emit(aviso)
                if mal:
                    mal(aviso)
                return

            if estado and estado >= 400:
                if mal:
                    mal(self._motivo(crudo, estado, ruta))
                return

            if not crudo:
                bien(None)
                return

            try:
                bien(json.loads(crudo.decode("utf-8")))
            except (ValueError, UnicodeDecodeError):
                # Hay endpoints que devuelven texto plano. Que la ventana
                # decida qué hacer con él en vez de tratarlo como un error.
                bien(crudo.decode("utf-8", errors="replace"))
        finally:
            respuesta.deleteLater()

    @staticmethod
    def _motivo(crudo: bytes, estado: int, ruta: str) -> str:
        """El motivo que dio el motor, si lo dio, y no un número a secas."""
        try:
            datos = json.loads(crudo.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            datos = None

        if isinstance(datos, dict):
            for clave in ("detail", "message", "error"):
                valor = datos.get(clave)
                if isinstance(valor, str) and valor.strip():
                    return valor
        if estado in (401, 403):
            return "El motor pide una clave de acceso."
        return f"El motor respondió {estado} en {ruta}."
