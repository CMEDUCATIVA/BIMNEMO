"""Saber si los datos de la memoria han cambiado desde que se pintaron.

El Panel se pintaba al abrirse y al pulsar «Releer», y nada más. Subir
documentos en Archivos y volver al Panel enseñaba el grafo de antes: había que
refrescar a mano para ver lo que se acababa de indexar.

Esto pregunta a ``GET /bimnemo/progress``, que es barato y trae un sello
(``revision``) que cambia cuando entra o sale un fichero o un documento cambia
de estado. Comparando el sello se sabe si hay algo nuevo sin volver a pedir
todos los datos.

## Cuándo se recarga el grafo y cuándo solo las cifras

- **Al volver a la pantalla**, si cambió algo mientras no se miraba: todo.
  Es lo que se espera al volver de subir documentos.
- **Con la pantalla a la vista y el motor indexando**: solo las cifras. El
  grafo se redibujaría con cada documento, deshaciendo lo que el usuario
  estuviera mirando cada pocos segundos.
- **Cuando el motor termina**: todo. Se vigila también el paso de ocupado a
  libre, porque el último cambio de estado de un documento puede llegar con
  el motor aún ocupado, y después ya no cambia el sello.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget

from lightrag.api.bimnemo.nativo.motor import Motor

#: Cada cuánto se pregunta con la pantalla a la vista.
SONDEO_MS = 2_000


class Frescura(QObject):
    """Vigila una pantalla y avisa cuando sus datos se han quedado viejos."""

    #: Hay datos nuevos. ``True`` si hay que recargar también el grafo.
    cambiaron = Signal(bool)

    def __init__(self, motor: Motor, pantalla: QWidget) -> None:
        super().__init__(pantalla)
        self.motor = motor
        self.pantalla = pantalla
        self._visto: Optional[str] = None
        self._ocupado = False
        self._al_volver = False

        self._reloj = QTimer(self)
        self._reloj.setInterval(SONDEO_MS)
        self._reloj.timeout.connect(self._sondear)
        self._reloj.start()
        pantalla.installEventFilter(self)

    def olvidar(self) -> None:
        """La pantalla acaba de pedirlo todo: lo próximo que llegue es la base."""
        self._visto = None

    def eventFilter(self, objeto: QObject, evento: QEvent) -> bool:  # noqa: N802
        # Con `getattr`: si Python suelta este objeto antes que Qt, Qt sigue
        # llamando al filtro con un envoltorio sin atributos. Un filtro que
        # lanza ahí rompe el reparto de eventos de toda la aplicación.
        pantalla = getattr(self, "pantalla", None)
        if pantalla is not None and objeto is pantalla and evento.type() == QEvent.Show:
            self._al_volver = True
            self.mirar()
        return False

    def _sondear(self) -> None:
        # Una pantalla que nadie mira no necesita estar al día: ya se pondrá
        # al volver.
        if self.pantalla.isVisible():
            self.mirar()

    def mirar(self) -> None:
        self.motor.get("/bimnemo/progress", self._llego, None)

    def _llego(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        sello = str(datos.get("revision") or "")
        ocupado = bool(datos.get("busy"))
        al_volver, self._al_volver = self._al_volver, False

        if self._visto is None:
            self._visto, self._ocupado = sello, ocupado
            return

        cambio = sello != self._visto
        termino = self._ocupado and not ocupado
        self._visto, self._ocupado = sello, ocupado
        if cambio or termino:
            self.cambiaron.emit(al_volver or not ocupado)


__all__ = ["Frescura", "SONDEO_MS"]
