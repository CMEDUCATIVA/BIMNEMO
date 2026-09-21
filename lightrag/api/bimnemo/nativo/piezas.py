"""Piezas que se repiten en las pantallas nativas.

Tarjetas, filas de dato, avisos y encabezados. Están aquí y no copiadas en
cada pantalla por lo de siempre: seis copias de una tarjeta son seis sitios
donde arreglar el mismo margen.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class Tarjeta(QFrame):
    """Un bloque con título y contenido, como las tarjetas de la web."""

    def __init__(self, titulo: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("tarjeta")

        self.columna = QVBoxLayout(self)
        self.columna.setContentsMargins(18, 16, 18, 16)
        self.columna.setSpacing(10)

        if titulo:
            etiqueta = QLabel(titulo)
            etiqueta.setObjectName("subtitulo")
            self.columna.addWidget(etiqueta)

    def anadir(self, widget: QWidget) -> None:
        self.columna.addWidget(widget)

    def dato(self, nombre: str, valor: str) -> QLabel:
        """Una fila «nombre … valor». Devuelve el valor para poder cambiarlo.

        Se devuelve la etiqueta en vez de guardarla en un diccionario interno
        para que cada pantalla nombre sus datos como quiera; buscar por texto
        rompe en cuanto alguien cambia una tilde.
        """
        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(12)

        izquierda = QLabel(nombre)
        izquierda.setObjectName("dato-nombre")
        izquierda.setMinimumWidth(190)
        izquierda.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        caja.addWidget(izquierda)

        derecha = QLabel(valor)
        derecha.setObjectName("dato-valor")
        derecha.setWordWrap(True)
        derecha.setTextInteractionFlags(Qt.TextSelectableByMouse)
        derecha.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        caja.addWidget(derecha, 1)

        self.columna.addWidget(fila)
        return derecha


class Aviso(QLabel):
    """Una línea de estado que se puede pintar de tres maneras.

    Empieza oculta: un aviso que siempre ocupa sitio deja un hueco vacío que
    parece un fallo de dibujo.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("aviso")
        self.setWordWrap(True)
        self.hide()

    def informar(self, texto: str) -> None:
        self._mostrar(texto, "info")

    def acertar(self, texto: str) -> None:
        self._mostrar(texto, "bien")

    def fallar(self, texto: str) -> None:
        self._mostrar(texto, "mal")

    def callar(self) -> None:
        self.clear()
        self.hide()

    def _mostrar(self, texto: str, tono: str) -> None:
        self.setText(texto)
        self.setProperty("tono", tono)
        # Qt no recalcula el estilo al cambiar una propiedad: hay que
        # pedírselo. Sin esto el color se queda en el de la vez anterior.
        self.style().unpolish(self)
        self.style().polish(self)
        self.show()


class Fluida(QLayout):
    """Coloca en fila y **salta de línea** cuando no cabe, como el CSS.

    Qt no trae ninguna disposición que envuelva: `QHBoxLayout` aprieta los
    elementos hasta recortarles el texto. Se vio en la leyenda del grafo, que
    al estrechar la ventana pasaba de «concepto 79» a «conce 79».

    Es el patrón `FlowLayout` de la documentación de Qt, con los nombres en
    castellano y sin las opciones que aquí no se usan.
    """

    def __init__(self, separacion: int = 12, salto: int = 6) -> None:
        super().__init__()
        self._piezas: list = []
        self._separacion = separacion
        self._salto = salto
        self.setContentsMargins(0, 0, 0, 0)

    # -- lo que `QLayout` exige --------------------------------------------

    def addItem(self, pieza) -> None:  # noqa: N802 (nombre de Qt)
        self._piezas.append(pieza)

    def count(self) -> int:
        return len(self._piezas)

    def itemAt(self, indice: int):  # noqa: N802
        return self._piezas[indice] if 0 <= indice < len(self._piezas) else None

    def takeAt(self, indice: int):  # noqa: N802
        if 0 <= indice < len(self._piezas):
            return self._piezas.pop(indice)
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, ancho: int) -> int:  # noqa: N802
        return self._repartir(QRect(0, 0, ancho, 0), medir=True)

    def setGeometry(self, rect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._repartir(rect, medir=False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        medida = QSize()
        for pieza in self._piezas:
            medida = medida.expandedTo(pieza.minimumSize())
        return medida

    def _repartir(self, rect, medir: bool) -> int:
        x, y, alto_fila = rect.x(), rect.y(), 0

        for pieza in self._piezas:
            ancho = pieza.sizeHint().width()
            alto = pieza.sizeHint().height()
            if x + ancho > rect.right() and alto_fila > 0:
                x = rect.x()
                y += alto_fila + self._salto
                alto_fila = 0
            if not medir:
                pieza.setGeometry(QRect(QPoint(x, y), pieza.sizeHint()))
            x += ancho + self._separacion
            alto_fila = max(alto_fila, alto)

        return y + alto_fila - rect.y()


class Pantalla(QWidget):
    """Base de las pantallas: título, descripción y contenido con desplazamiento.

    El desplazamiento va aquí y no en cada pantalla porque la ventana se
    puede achicar hasta 620 píxeles de alto, y sin él las pantallas largas
    quedan cortadas sin que se pueda llegar al final.
    """

    def __init__(self, titulo: str, descripcion: str = "") -> None:
        super().__init__()

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        raiz.addWidget(area)

        dentro = QWidget()
        self.columna = QVBoxLayout(dentro)
        self.columna.setContentsMargins(32, 28, 32, 28)
        self.columna.setSpacing(16)
        area.setWidget(dentro)

        encabezado = QVBoxLayout()
        encabezado.setSpacing(4)

        etiqueta = QLabel(titulo)
        etiqueta.setObjectName("titulo")
        encabezado.addWidget(etiqueta)

        if descripcion:
            texto = QLabel(descripcion)
            texto.setObjectName("descripcion")
            texto.setWordWrap(True)
            encabezado.addWidget(texto)

        self.columna.addLayout(encabezado)

    def anadir(self, widget: QWidget) -> None:
        self.columna.addWidget(widget)

    def cerrar_con_espacio(self) -> None:
        """Empuja todo hacia arriba. Se llama al terminar de montar."""
        self.columna.addStretch(1)
