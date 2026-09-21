"""Saber que hay una versión nueva en GitHub, y traerla sin reinstalar.

La mitad del motor ya existía: ``GET /bimnemo/update`` compara la versión
instalada con la última publicada, y ``POST /bimnemo/update/apply`` la
descarga, la copia encima y se reinicia. Esto es la mitad que se ve.

## Qué se toca y qué no

El paquete que se descarga es lo que el repositorio versiona, y eso deja
fuera por construcción el ``.env``, ``inputs/`` y ``rag_storage/``: la
configuración, los documentos y las memorias no viajan en él, así que no se
pueden pisar. Ver ``bimnemo/paquete.py``.

## Por qué la aplicación entera vuelve a abrirse

El motor se reinicia solo y carga el código nuevo. La ventana no: su código
ya está en memoria, y seguiría enseñando la versión de antes hasta cerrarla.
Así que, cuando el motor nuevo contesta, la aplicación se relanza a sí misma.
La copia nueva espera a que la vieja termine de cerrarse —``--esperar-pid``—
para no engancharse a un motor que está a punto de apagarse.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Optional
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QProgressBar, QPushButton, QWidget

from lightrag.api.bimnemo.nativo import iconos
from lightrag.api.bimnemo.nativo.memorias import _Dialogo
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.reinicio import Reinicio, conectar_barra

#: La primera consulta, poco después de abrir: no en el mismo instante, que
#: es cuando la ventana tiene más cosas que pedir al motor.
PRIMERA_MS = 5_000

#: Y después, cada media hora. Una versión nueva no corre prisa, y GitHub
#: limita las consultas sin credencial a 60 por hora.
INTERVALO_MS = 30 * 60 * 1_000

#: El ritmo del parpadeo del botón.
PARPADEO_MS = 650


class Actualizando(Reinicio):
    """El mismo sondeo del reinicio, pidiendo la actualización.

    Lo que se espera es idéntico: que conteste un motor con otro `boot_id`.
    Mientras descarga contesta el de antes, y eso es lo normal.
    """

    RUTA = "/bimnemo/update/apply"
    PASO = "Descargando la versión nueva…"
    #: Descargar y, si cambiaron las dependencias, instalarlas con pip puede
    #: tardar varios minutos en una conexión lenta.
    PLAZO = 15 * 60 * 1_000

    def _pedido(self, datos: object) -> None:
        # Ya al día: el motor no se reinicia, así que no hay nada que esperar.
        if isinstance(datos, dict) and datos.get("status") == "up_to_date":
            self._terminar(False, str(datos.get("message") or "Ya está al día."))
            return
        super()._pedido(datos)

    def _mirar(self) -> None:
        super()._mirar()
        # Y si la descarga falló, el motor tampoco se reinicia: se pregunta en
        # qué va para decirlo enseguida, en vez de al agotar el plazo.
        if not self._acabado:
            self.motor.get("/bimnemo/update/progress", self._progreso, lambda _m: None)

    def _progreso(self, datos: object) -> None:
        if isinstance(datos, dict) and datos.get("state") == "failed":
            self._terminar(False, str(datos.get("message") or "La descarga falló."))


class Vigia(QObject):
    """Pregunta de vez en cuando si hay una versión nueva."""

    #: El estado del motor cuando hay una versión más nueva publicada.
    disponible = Signal(dict)

    def __init__(self, motor: Motor, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.motor = motor
        self.estado: dict[str, Any] = {}
        self._reloj = QTimer(self)
        self._reloj.setInterval(INTERVALO_MS)
        self._reloj.timeout.connect(self.mirar)

    def arrancar(self) -> None:
        QTimer.singleShot(PRIMERA_MS, self.mirar)
        self._reloj.start()

    def mirar(self) -> None:
        # Sin red, GitHub no contesta y el motor lo dice sin error: no hay
        # nada que avisar, que es exactamente lo que se hace.
        self.motor.get("/bimnemo/update", self._llego, lambda _motivo: None)

    def _llego(self, datos: Any) -> None:
        if isinstance(datos, dict) and datos.get("behind"):
            self.estado = datos
            self.disponible.emit(datos)


class BotonActualizar(QPushButton):
    """«Actualizar», en la barra de arriba, parpadeando mientras haya una."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("  Actualizar", parent)
        self.setObjectName("actualizar")
        iconos.poner(self, "subir", 14, "sobre_azul")
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("encendido", True)
        self._parpadeo = QTimer(self)
        self._parpadeo.setInterval(PARPADEO_MS)
        self._parpadeo.timeout.connect(self._latir)
        self.hide()

    def mostrar(self, estado: dict[str, Any]) -> None:
        nueva = estado.get("latest") or "una versión nueva"
        tienes = estado.get("installed") or "?"
        self.setToolTip(
            f"Hay una versión nueva: {nueva} (tienes {tienes}). "
            "Pulsa para actualizar sin reinstalar."
        )
        self.show()
        self._parpadeo.start()

    def _latir(self) -> None:
        encendido = not self.property("encendido")
        self.setProperty("encendido", encendido)
        # El icono cambia con el fondo: blanco sobre azul, azul sobre claro.
        iconos.poner(self, "subir", 14, "sobre_azul" if encendido else "azul")
        # Una propiedad nueva no repinta sola: Qt aplica la hoja de estilo al
        # pulir, y hay que pedírselo.
        self.style().unpolish(self)
        self.style().polish(self)


class DialogoActualizar(_Dialogo):
    """Confirmar, descargar, esperar al motor y volver a abrir."""

    def __init__(
        self, motor: Motor, estado: dict[str, Any], padre: Optional[QWidget] = None
    ) -> None:
        super().__init__("Hay una versión nueva", "subir", padre)
        self.motor = motor
        self._trabajo: Optional[Actualizando] = None

        nueva = estado.get("latest") or "?"
        tienes = estado.get("installed") or "?"
        self.parrafo(f"Tienes la {tienes} y está publicada la {nueva}.", "dato-valor")
        titulo = str(estado.get("message") or "").strip()
        if titulo and titulo != nueva:
            self.parrafo(f"«{titulo}»")
        self.parrafo(
            "Se descarga y se instala encima, sin reinstalar. Tus memorias, tus "
            "documentos y tu configuración no se tocan. Al terminar, BIMNEMO se "
            "cierra y vuelve a abrirse solo."
        )

        self.estado = self.parrafo("")
        self.barra = QProgressBar()
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(6)
        self.barra.hide()
        self.columna.addWidget(self.barra)

        self.botonera("Ahora no", "Actualizar").clicked.connect(self._actualizar)

    def _actualizar(self) -> None:
        self.aceptar.setEnabled(False)
        self.aceptar.setText("Actualizando…")
        self.fallar("")
        self.barra.show()

        self._trabajo = Actualizando(self.motor, self)
        conectar_barra(
            self._trabajo,
            self.estado.setText,
            lambda hecho, tope: (
                self.barra.setMaximum(tope),
                self.barra.setValue(hecho),
            ),
        )
        self._trabajo.terminado.connect(self._terminado)
        self._trabajo.arrancar()

    def _terminado(self, bien: bool, motivo: str) -> None:
        if not bien:
            self.barra.hide()
            self.aceptar.setEnabled(True)
            self.aceptar.setText("Actualizar")
            self.fallar(f"No se pudo actualizar: {motivo}")
            return
        self.estado.setText("Listo. Volviendo a abrir BIMNEMO…")
        relanzar(self.motor.base)


def relanzar(base: str) -> None:
    """Abre una copia nueva de la aplicación y cierra ésta.

    La copia nueva espera a que ésta termine (``--esperar-pid``): al cerrarse,
    ésta apaga el motor que arrancó, y la nueva tiene que arrancar el suyo.
    """
    puerto = urlparse(base).port or 9621
    orden = [
        sys.executable,
        "-m",
        "lightrag.api.bimnemo.desktop",
        "--esperar-pid",
        str(os.getpid()),
        "--port",
        str(puerto),
    ]
    banderas = 0
    if os.name == "nt":
        # Suelta del todo: si este proceso vive en un trabajo de Windows que
        # mata a sus hijos al cerrarse, la copia nueva moriría con él.
        banderas = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | 0x01000000  # CREATE_BREAKAWAY_FROM_JOB
        )
    try:
        subprocess.Popen(orden, close_fds=True, creationflags=banderas, cwd=os.getcwd())
    except OSError:
        # Hay trabajos que no dejan escapar. Sin esa bandera se intenta igual.
        subprocess.Popen(
            orden,
            close_fds=True,
            creationflags=banderas & ~0x01000000,
            cwd=os.getcwd(),
        )
    QApplication.quit()


__all__ = [
    "Actualizando",
    "BotonActualizar",
    "DialogoActualizar",
    "Vigia",
    "relanzar",
]
