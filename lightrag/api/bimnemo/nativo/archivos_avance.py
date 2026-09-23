"""Las barras de avance de la tabla de Archivos, una por fila.

## Por qué cada fila tiene la suya

Antes el motor solo publicaba **un** recuento para toda la tubería, así que
la única fila que podía enseñar un número era la que estuviera extrayendo, y
las demás se quedaban con una barra indeterminada —la que va y viene sin
decir nada—. Con dos documentos en cola eso es casi toda la tabla.

Ahora el motor publica avance **por documento y por fase**
(``lightrag/doc_progress.py``), ``/bimnemo/progress`` lo devuelve en ``docs``
y aquí cada fila busca el suyo por su ``doc_id``. El borrado también: purgar
un documento del grafo tarda segundos y antes no se veía nada moverse.

## Lo que se enseña, y lo que se guarda para el rótulo emergente

En la celda caben unos veinte caracteres al lado de la barra, así que ahí va
lo corto —«Extrayendo · 45 %»— y la frase entera del motor —«Extrayendo 3/7
fragmentos»— se guarda en el rótulo emergente. Quien quiere el detalle pasa
el ratón; quien solo mira de reojo ve el número.
"""

from __future__ import annotations

from time import monotonic
from typing import Any, Optional

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QWidget,
)

#: Cuánto se espera sin que nadie trabaje antes de decir que algo va mal.
#: Documentos en cola y la tubería parada es normal un instante —acaban de
#: encolarse— y sospechoso a los veinte segundos.
PACIENCIA = 20.0

#: Una palabra por fase para la celda. Las claves son las que viaja el motor
#: por HTTP; se escriben aquí a mano, sin importar el módulo del motor, para
#: que la pantalla no dependa de sus constantes.
CORTAS: dict[str, str] = {
    "parse": "Leyendo",
    "analyze": "Tablas",
    "extract": "Extrayendo",
    "merge": "Grafo",
    "delete": "Borrando",
}


class Barras:
    """Las barras vivas de la tabla y lo último que dijo el motor.

    Vive en la pantalla de Archivos y no sabe nada de ella: se le dan los
    datos de ``/bimnemo/progress`` y el estado de una fila, y devuelve —o
    mueve— su barra. Así el sondeo puede mover una fila sin rehacer la tabla
    entera, que es lo que le quita el ratón de encima a quien está a punto de
    pulsar un botón.
    """

    def __init__(self) -> None:
        #: Barra, rótulo del número y la celda entera, por nombre de fichero.
        self._filas: dict[str, tuple[QProgressBar, QLabel, QWidget]] = {}
        #: Lo último que contestó ``/bimnemo/progress``.
        self._datos: dict[str, Any] = {}
        #: El avance de cada documento, indexado por ``doc_id``.
        self._por_doc: dict[str, dict[str, Any]] = {}
        #: Desde cuándo el motor dice que está parado, o ``None``.
        self._parado_desde: Optional[float] = None

    # -- lo que llega del motor ---------------------------------------------

    def recordar(self, datos: dict[str, Any]) -> bool:
        """Guarda la última respuesta. Devuelve si hay trabajo en marcha.

        El «parado desde» se lleva aquí y no en la pantalla porque es lo que
        decide cómo se pinta una barra: hace falta que pasen unos segundos
        de atasco antes de decirlo, o cada encolado parecería un problema.
        """
        self._datos = datos
        self._por_doc = {
            str(fila.get("doc_id") or ""): fila
            for fila in (datos.get("docs") or [])
            if isinstance(fila, dict)
        }

        activo = bool(datos.get("busy")) or int(datos.get("working") or 0) > 0
        if activo and datos.get("stalled"):
            if self._parado_desde is None:
                self._parado_desde = monotonic()
        else:
            self._parado_desde = None
        return activo

    @property
    def parado(self) -> bool:
        """Lleva parado lo bastante como para decirlo en voz alta."""
        return (
            bool(self._datos.get("stalled"))
            and self._parado_desde is not None
            and monotonic() - self._parado_desde > PACIENCIA
        )

    # -- las barras de la tabla ---------------------------------------------

    def olvidar(self) -> None:
        """La tabla se va a repintar: las barras de antes ya no existen."""
        self._filas.clear()

    def tiene(self, nombre: str) -> bool:
        return nombre in self._filas

    def crear(self, nombre: str, celda: QWidget) -> QWidget:
        """La barra y su número, listos para meter en la celda de estado."""
        barra = QProgressBar()
        barra.setObjectName("avance")
        barra.setTextVisible(False)
        # El rótulo de al lado se queda con lo que necesita y la barra con el
        # resto; sin un mínimo, «Extrayendo · 100 %» la dejaría en nada y la
        # fila se leería como si no hubiera barra.
        barra.setMinimumWidth(48)
        texto = QLabel("")
        texto.setObjectName("avance-texto")

        debajo = QWidget()
        debajo.setObjectName("fila")
        caja = QHBoxLayout(debajo)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(6)
        caja.addWidget(barra, 1)
        caja.addWidget(texto)

        self._filas[nombre] = (barra, texto, celda)
        return debajo

    def pintar(
        self,
        nombre: str,
        doc_id: str,
        estado: str,
        subiendo: Optional[int] = None,
    ) -> None:
        """Pone la barra de una fila con lo último que se sabe de ella."""
        trio = self._filas.get(nombre)
        if trio is None:
            return
        barra, texto, celda = trio

        if subiendo is not None:
            # Subir no lo sabe el motor todavía: el porcentaje lo cuenta el
            # propio envío, y no hay fase ni rótulo que buscar.
            barra.setRange(0, 100)
            barra.setValue(subiendo)
            texto.setText("")
            texto.setToolTip("")
            self._marcar_parada(barra, False)
            return

        if self.parado:
            self._marcar_parada(barra, True)
            barra.setRange(0, 100)
            barra.setValue(0)
            texto.setText("Sin avanzar")
            texto.setToolTip(
                "El motor lleva un rato sin procesar. Puede que el modelo no "
                "responda o que falte configuración."
            )
            return

        self._marcar_parada(barra, False)
        fila = self._por_doc.get(doc_id) if doc_id else None
        if fila is None:
            # Hay trabajo, pero nadie sabe cuánto queda: indeterminada. Es
            # el caso de un fichero recién soltado, antes de que el motor le
            # dé un identificador.
            barra.setRange(0, 0)
            texto.setText("")
            texto.setToolTip("")
            return

        corta = CORTAS.get(str(fila.get("phase") or ""), "Trabajando")
        rotulo = str(fila.get("label") or corta)
        por_ciento = fila.get("percent")

        if por_ciento is None:
            barra.setRange(0, 0)
            texto.setText(corta)
        else:
            valor = max(0, min(100, int(por_ciento)))
            barra.setRange(0, 100)
            barra.setValue(valor)
            texto.setText(f"{corta} · {valor} %")

        # La frase entera del motor, donde sí cabe.
        texto.setToolTip(rotulo)
        if estado in ("deleting", "processing", "parsing", "analyzing"):
            celda.setToolTip(rotulo)

    @staticmethod
    def _marcar_parada(barra: QProgressBar, parado: bool) -> None:
        """Pinta la barra de gris, o la devuelve al azul.

        Se pone y se **quita**: la misma barra se reutiliza entre sondeos, y
        una que se quedara marcada seguiría gris después de que el motor
        volviera a moverse.
        """
        marca = "si" if parado else ""
        if barra.property("parado") == marca:
            return
        barra.setProperty("parado", marca)
        barra.style().unpolish(barra)
        barra.style().polish(barra)


__all__ = ["Barras", "CORTAS", "PACIENCIA"]
