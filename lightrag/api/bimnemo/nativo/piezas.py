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
    QGridLayout,
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


def insignia(texto: str, color: str, fondo: str, punto: bool = False) -> QLabel:
    """Una etiqueta de color: categoría, estado del motor, lo que sea.

    El estilo va en el propio widget y no en la hoja general porque el color
    cambia en cada uso; una regla por cada categoría y cada estado serían
    veinte reglas para decir lo mismo.
    """
    etiqueta = QLabel()
    etiqueta.setObjectName("insignia")
    pintar_insignia(etiqueta, texto, color, fondo, punto)
    return etiqueta


def pintar_insignia(
    etiqueta: QLabel, texto: str, color: str, fondo: str, punto: bool = False
) -> None:
    """Vuelve a pintar una insignia que ya existe, con otro color y otro texto.

    Lo necesita lo que cambia sin rehacerse —el estado del motor, arriba a la
    derecha— y es el mismo estilo que `insignia`, escrito una sola vez.
    """
    etiqueta.setText(f"●  {texto}" if punto else texto)
    etiqueta.setStyleSheet(
        f"background: {fondo}; border-radius: 9px; color: {color};"
        " font-size: 11px; font-weight: 600; padding: 2px 9px;"
    )


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

    def __init__(
        self, separacion: int = 12, salto: int = 6, centrado: bool = False
    ) -> None:
        super().__init__()
        self._piezas: list = []
        self._separacion = separacion
        self._salto = salto
        self._centrado = centrado
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

    def _filas(self, rect) -> list[tuple[list, int, int]]:
        """Reparte las piezas en filas: cuáles van juntas, y cuánto miden.

        Se calculan **antes** de colocar nada porque para centrar una fila
        hay que saber su ancho total, y eso no se sabe hasta haberla
        cerrado.
        """
        filas: list[tuple[list, int, int]] = []
        actual: list = []
        ancho_fila = 0
        alto_fila = 0

        for pieza in self._piezas:
            medida = pieza.sizeHint()
            siguiente = (
                ancho_fila + medida.width() + (self._separacion if actual else 0)
            )
            if actual and siguiente > rect.width():
                filas.append((actual, ancho_fila, alto_fila))
                actual, ancho_fila, alto_fila = [], 0, 0
                siguiente = medida.width()
            actual.append(pieza)
            ancho_fila = siguiente
            alto_fila = max(alto_fila, medida.height())

        if actual:
            filas.append((actual, ancho_fila, alto_fila))
        return filas

    def _repartir(self, rect, medir: bool) -> int:
        y = rect.y()
        for piezas, ancho_fila, alto_fila in self._filas(rect):
            x = rect.x()
            if self._centrado:
                x += max(0, (rect.width() - ancho_fila) // 2)
            for pieza in piezas:
                if not medir:
                    pieza.setGeometry(QRect(QPoint(x, y), pieza.sizeHint()))
                x += pieza.sizeHint().width() + self._separacion
            y += alto_fila + self._salto

        return max(0, y - self._salto - rect.y())


#: Por debajo de este ancho de la rejilla, las tarjetas van de una en una: dos
#: de cuatrocientos píxeles ya no dejan leer ni el nombre de un proveedor.
ANCHO_DOS_COLUMNAS = 900


class RejillaTarjetas(QWidget):
    """Tarjetas de dos en dos, y de una en una cuando no caben.

    Es lo que hacen Configuración IA y Motor, que en una sola columna dejaban
    cada dato en una línea de mil píxeles con el valor perdido al otro
    extremo.

    Dos tarjetas de la misma fila miden lo que la más alta, y la baja
    **se rellena por abajo**: sin eso repartía ese alto entre sus líneas —el
    título por un lado, el primer dato por otro y un hueco entre medias—.
    Por eso las tarjetas tienen que llegar ya completas; lo que se les añada
    después quedaría debajo del relleno.

    Se mide por su propio ancho, no por el de la pantalla: una página del
    apilado que no está a la vista no recibe los cambios de tamaño hasta que
    se enseña, y la rejilla sí los recibe entonces.
    """

    def __init__(
        self,
        tarjetas: list[QWidget],
        ancho_dos_columnas: int = ANCHO_DOS_COLUMNAS,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("fila")
        self.tarjetas = list(tarjetas)
        self._umbral = ancho_dos_columnas
        self._columnas = 0

        self.rejilla = QGridLayout(self)
        self.rejilla.setContentsMargins(0, 0, 0, 0)
        self.rejilla.setHorizontalSpacing(16)
        self.rejilla.setVerticalSpacing(16)

        for tarjeta in self.tarjetas:
            # Una sección de Configuración envuelve su tarjeta; una tarjeta
            # suelta es ella misma.
            interior = getattr(tarjeta, "tarjeta", tarjeta)
            interior.columna.addStretch(1)

        self._colocar(2)

    @property
    def columnas(self) -> int:
        return self._columnas

    def posiciones(self) -> list[tuple[int, int]]:
        """Fila y columna de cada tarjeta, en el orden en que llegaron."""
        sitio = []
        for tarjeta in self.tarjetas:
            fila, columna, _alto, _ancho = self.rejilla.getItemPosition(
                self.rejilla.indexOf(tarjeta)
            )
            sitio.append((fila, columna))
        return sitio

    def resizeEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        super().resizeEvent(evento)
        self._colocar(2 if self.width() >= self._umbral else 1)

    def _colocar(self, columnas: int) -> None:
        if columnas == self._columnas:
            return
        self._columnas = columnas
        for puesto, tarjeta in enumerate(self.tarjetas):
            self.rejilla.addWidget(tarjeta, puesto // columnas, puesto % columnas)
        for columna in range(2):
            self.rejilla.setColumnStretch(columna, 1 if columna < columnas else 0)


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
