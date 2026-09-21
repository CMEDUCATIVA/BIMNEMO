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
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote

from PySide6.QtCore import QByteArray, QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

#: Qué se considera «ha tardado demasiado». El motor contesta en
#: milisegundos salvo cuando está indexando, que puede tardar.
ESPERA_MS = 30_000

#: Endpoints con **ruta espejo** por memoria. El resto se apunta a una
#: memoria con `?nemo=`, pero estos tres tienen su propio camino y hay que
#: usarlo: mandarles el parámetro no da error, y ahí está el peligro — el
#: motor lo ignora y contesta desde la memoria por defecto mientras la
#: pantalla dice que está en otra.
ESPEJOS = {
    "/query": "/nemo/{id}/query",
    "/documents/upload": "/nemo/{id}/documents/upload",
    "/bimnemo/memory/search": "/nemo/{id}/memory/search",
}

#: Lo que se contesta cuando el motor pide autenticación. Es una constante y
#: no un texto suelto porque la barra superior la compara para enseñar
#: «Requiere clave» en vez de «Motor no disponible»: son dos problemas
#: distintos y se arreglan de formas distintas.
PIDE_CLAVE = "El motor pide una clave de acceso."

#: Rutas que **nombran** una memoria en vez de trabajar dentro de una. El
#: registro de memorias se administra desde fuera de cualquiera de ellas.
SIN_MEMORIA = ("/bimnemo/nemos",)


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
        self._memoria: str = ""

    def usar_clave(self, clave: str) -> None:
        """La clave de acceso, si el usuario la tiene activada."""
        self._clave = clave or ""

    @property
    def clave(self) -> str:
        """La que se está presentando ahora. Vacía si la API está abierta."""
        return self._clave

    # -- memoria activa -----------------------------------------------------

    @property
    def memoria(self) -> str:
        """Identificador de la memoria a la que se le está hablando."""
        return self._memoria

    def usar_memoria(self, nemo: str) -> None:
        """Cambia de memoria. Vacío significa «la de por defecto».

        Se pone **aquí y no en cada pantalla** por lo mismo que la clave de
        acceso: son doce llamadas repartidas por seis pantallas, y la que se
        olvidara de añadir el parámetro seguiría funcionando —contestando
        desde la memoria equivocada— sin que nada fallara.
        """
        self._memoria = nemo or ""

    def _resolver(self, ruta: str) -> str:
        """La ruta de verdad para la memoria activa.

        Tres casos: la que tiene ruta espejo se reescribe, la que administra
        el registro de memorias se deja en paz, y a las demás se les añade
        `?nemo=`. Una ruta que ya trae `nemo=` escrito también se respeta:
        la ha construido quien sabía a qué memoria apuntaba.
        """
        if not self._memoria:
            return ruta

        camino = ruta.split("?", 1)[0]
        espejo = ESPEJOS.get(camino)
        if espejo is not None:
            resto = ruta[len(camino) :]
            return espejo.format(id=quote(self._memoria, safe="")) + resto

        if camino.startswith(SIN_MEMORIA) or "nemo=" in ruta:
            return ruta

        separador = "&" if "?" in ruta else "?"
        return f"{ruta}{separador}nemo={quote(self._memoria, safe='')}"

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

    def borrar(
        self,
        ruta: str,
        cuerpo: Any,
        bien: Callable[[Any], None],
        mal: Optional[Callable[[str], None]] = None,
    ) -> None:
        """DELETE con cuerpo, que es lo que piden los endpoints de borrado."""
        peticion = self._peticion(ruta)
        datos = QByteArray(json.dumps(cuerpo or {}).encode("utf-8"))
        respuesta = self._red.sendCustomRequest(peticion, b"DELETE", datos)
        respuesta.finished.connect(lambda: self._recoger(respuesta, ruta, bien, mal))

    def parchear(
        self,
        ruta: str,
        cuerpo: Any,
        bien: Callable[[Any], None],
        mal: Optional[Callable[[str], None]] = None,
    ) -> None:
        """PATCH, que es lo que pide renombrar una memoria."""
        peticion = self._peticion(ruta)
        datos = QByteArray(json.dumps(cuerpo or {}).encode("utf-8"))
        respuesta = self._red.sendCustomRequest(peticion, b"PATCH", datos)
        respuesta.finished.connect(lambda: self._recoger(respuesta, ruta, bien, mal))

    def subir(
        self,
        ruta: str,
        fichero: str,
        bien: Callable[[Any], None],
        mal: Optional[Callable[[str], None]] = None,
        avance: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Sube un fichero como `multipart/form-data`, informando del avance.

        El fichero se lee **según se envía**, no entero a memoria: hay
        documentos de cientos de megas y cargarlos enteros para subirlos a
        `127.0.0.1` sería gastar el doble por nada.
        """
        from PySide6.QtCore import QFile
        from PySide6.QtNetwork import QHttpMultiPart, QHttpPart

        multi = QHttpMultiPart(QHttpMultiPart.FormDataType)

        parte = QHttpPart()
        nombre = Path(fichero).name
        parte.setHeader(
            QNetworkRequest.ContentDispositionHeader,
            f'form-data; name="file"; filename="{nombre}"',
        )

        # El `QFile` se cuelga del multipart a propósito: Qt lo va leyendo
        # mientras sube, y si lo recogiera el recolector de basura antes de
        # terminar la subida se cortaría a mitad sin decir por qué.
        origen = QFile(fichero)
        if not origen.open(QFile.ReadOnly):
            if mal:
                mal(f"No se pudo leer {nombre}.")
            return
        origen.setParent(multi)
        parte.setBodyDevice(origen)
        multi.append(parte)

        peticion = QNetworkRequest(QUrl(f"{self.base}{self._resolver(ruta)}"))
        # Sin cabecera de tipo: la pone el propio multipart, con su frontera.
        peticion.setTransferTimeout(0)  # sin plazo: un fichero grande tarda
        if self._clave:
            peticion.setRawHeader(b"X-API-Key", self._clave.encode("utf-8"))

        respuesta = self._red.post(peticion, multi)
        multi.setParent(respuesta)
        if avance is not None:
            respuesta.uploadProgress.connect(
                lambda hecho, total: avance(int(hecho), int(total))
            )
        respuesta.finished.connect(lambda: self._recoger(respuesta, ruta, bien, mal))

    def _peticion(self, ruta: str) -> QNetworkRequest:
        peticion = QNetworkRequest(QUrl(f"{self.base}{self._resolver(ruta)}"))
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

        respuesta.finished.connect(lambda: self._recoger(respuesta, ruta, bien, mal))

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
            estado = respuesta.attribute(QNetworkRequest.HttpStatusCodeAttribute)
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
            return PIDE_CLAVE
        return f"El motor respondió {estado} en {ruta}."
