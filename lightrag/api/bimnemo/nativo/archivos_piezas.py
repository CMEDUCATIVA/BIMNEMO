"""Las piezas de la pantalla «Archivos»: zona de arrastre, filtros, insignias.

Están aquí y no dentro de `pantalla_archivos.py` por el mismo motivo por el
que la web parte `archivos.js` en tres: aquella pantalla **enseña y cambia**
la memoria, y mezclarlo con cómo se dibuja un chip deja un fichero en el que
ya no se encuentra nada.

Ningún color se elige aquí: salen de `tema.CATEGORIA` y `tema.color_estado`,
que son la traducción de `ui/css/tokens.css`.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo import iconos, tema
from lightrag.api.bimnemo.nativo.piezas import Fluida, insignia  # noqa: F401

#: La categoría de descarte, la misma que `catalog.UNKNOWN`. No viene en el
#: catálogo —no ocupa una de las ocho ranuras— pero sí aparece en las filas.
OTROS: dict[str, Any] = {"key": "other", "label": "Otros", "color": "slate"}


def categoria_de(catalogo: list[dict[str, Any]], clave: Any) -> dict[str, Any]:
    """La categoría de una fila, o «Otros» si no se reconoce.

    Nunca devuelve `None`: una fila sin categoría también se pinta, y lo hace
    con la etiqueta gris de descarte en vez de dejar el hueco en blanco.
    """
    for categoria in catalogo:
        if categoria.get("key") == clave:
            return categoria
    return OTROS


def icono_categoria(color: str) -> QIcon:
    """El cuadradito de color que va delante del nombre del fichero.

    La web pone ahí un icono de Lucide por categoría. Qt no trae ese juego de
    iconos y dibujar ocho a mano no se paga solo: lo que aporta esa marca es
    **el color**, que es lo que permite barrer la lista con la vista, y eso
    sí cabe en cuatro líneas.
    """
    lienzo = QPixmap(16, 16)
    lienzo.fill(Qt.transparent)
    pintor = QPainter(lienzo)
    pintor.setRenderHint(QPainter.Antialiasing)
    pintor.setPen(Qt.NoPen)
    pintor.setBrush(tema.color_categoria(color)[0])
    pintor.drawRoundedRect(2, 2, 12, 12, 3, 3)
    pintor.end()
    return QIcon(lienzo)


class ZonaSoltar(QFrame):
    """El recuadro de «arrastra aquí», con lo que el motor admite.

    La lista de formatos **no está escrita aquí**: la manda el motor en
    `GET /bimnemo/catalog`, derivada viva del registro de parsers. Copiarla
    sería tener dos listas, y la de la pantalla se quedaría vieja el día que
    se añada un parser.
    """

    #: Rutas locales que se acaban de soltar.
    soltados = Signal(list)
    #: Alguien ha pulsado la zona: se abre el diálogo de elegir ficheros.
    pulsada = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("zona")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)

        columna = QVBoxLayout(self)
        columna.setContentsMargins(24, 22, 24, 22)
        columna.setSpacing(6)

        marca = QLabel()
        marca.setPixmap(iconos.pixmap("subir", 28, tema.ACTUAL.texto_3))
        marca.setAlignment(Qt.AlignCenter)
        columna.addWidget(marca)

        titulo = QLabel("Arrastra aquí tus archivos")
        titulo.setObjectName("zona-titulo")
        titulo.setAlignment(Qt.AlignCenter)
        columna.addWidget(titulo)

        self.cuenta = QLabel("")
        self.cuenta.setObjectName("zona-cuenta")
        self.cuenta.setAlignment(Qt.AlignCenter)
        columna.addWidget(self.cuenta)

        self.lista = QLabel("Preguntando al motor qué formatos admite…")
        self.lista.setObjectName("zona-formatos")
        self.lista.setAlignment(Qt.AlignCenter)
        self.lista.setWordWrap(True)
        columna.addWidget(self.lista)

    def formatos(self, extensiones: Optional[Iterable[str]]) -> None:
        """Escribe lo que el motor admite. `None` mientras no se sabe.

        Se enseñan **todas**, no las primeras dieciocho con un «y 23 más»:
        quien quiere comprobar si su `.pptx` entra no puede hacerlo con una
        lista recortada, y el dato está a mano.
        """
        if extensiones is None:
            self.cuenta.setText("")
            self.lista.setText("Preguntando al motor qué formatos admite…")
            return

        lista = [str(e) for e in extensiones]
        if not lista:
            self.cuenta.setText("")
            self.lista.setText(
                "El motor no declara ningún formato admitido. Revisa la "
                "configuración de parsers antes de subir nada."
            )
            return

        self.cuenta.setText(f"Admite {len(lista)} formatos")
        self.lista.setText(" · ".join(lista))

    def no_se_pudo(self, motivo: str) -> None:
        """Cuando no hubo forma de preguntárselo al motor.

        No es lo mismo que «no admite nada»: decir eso sería acusar a la
        configuración de parsers de un problema que está en la conexión.
        """
        self.cuenta.setText("")
        self.lista.setText(motivo)

    # -- arrastre -----------------------------------------------------------

    def _encender(self, encendida: bool) -> None:
        self.setProperty("encima", "si" if encendida else "")
        # Qt no repinta al cambiar una propiedad: hay que pedírselo.
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, evento: QDragEnterEvent) -> None:  # noqa: N802
        if evento.mimeData().hasUrls():
            evento.acceptProposedAction()
            self._encender(True)

    def dragLeaveEvent(self, evento) -> None:  # noqa: N802
        self._encender(False)
        super().dragLeaveEvent(evento)

    def dropEvent(self, evento: QDropEvent) -> None:  # noqa: N802
        self._encender(False)
        rutas = [
            url.toLocalFile() for url in evento.mimeData().urls() if url.isLocalFile()
        ]
        evento.acceptProposedAction()
        if rutas:
            self.soltados.emit(rutas)

    def mouseReleaseEvent(self, evento) -> None:  # noqa: N802
        if evento.button() == Qt.LeftButton:
            self.pulsada.emit()
        super().mouseReleaseEvent(evento)


class Filtros(QWidget):
    """Los chips de categoría, con su recuento.

    Se vuelven a construir solo cuando cambian de verdad. Rehacerlos en cada
    sondeo —cada segundo y medio— le quitaría el ratón de encima justo a
    quien está a punto de pulsar uno.
    """

    #: La categoría elegida. Cadena vacía = todas.
    elegida = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("fila")
        self._activa = ""
        self._sello: tuple = ()

        # Fluida y no `QHBoxLayout`: con ocho categorías y la ventana
        # estrecha, una fila que no salta de línea recorta los rótulos hasta
        # dejarlos en «Present… 1».
        self.caja = Fluida(separacion=6, salto=6)
        self.setLayout(self.caja)
        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)

    @property
    def activa(self) -> str:
        return self._activa

    def poner(
        self, filas: list[dict[str, Any]], catalogo: list[dict[str, Any]]
    ) -> None:
        """Rehace los chips si el reparto por categorías ha cambiado."""
        cuentas: dict[str, int] = {}
        for fila in filas:
            clave = str(fila.get("category") or "other")
            cuentas[clave] = cuentas.get(clave, 0) + 1

        presentes = [c for c in catalogo if cuentas.get(str(c.get("key")))]
        if cuentas.get("other"):
            presentes.append(OTROS)

        sello = (
            len(filas),
            tuple((str(c["key"]), cuentas[str(c["key"])]) for c in presentes),
        )
        if sello == self._sello:
            return
        self._sello = sello

        # La categoría elegida puede haber desaparecido —se borró el último
        # fichero de ese tipo—: se vuelve a «todas» en vez de dejar la tabla
        # filtrada por algo que ya no existe.
        if self._activa and not cuentas.get(self._activa):
            self._activa = ""

        self._vaciar()
        self._chip("Todos", "", len(filas))
        for categoria in presentes:
            clave = str(categoria["key"])
            self._chip(str(categoria["label"]), clave, cuentas[clave])

    def _vaciar(self) -> None:
        for boton in list(self._grupo.buttons()):
            self._grupo.removeButton(boton)
        while self.caja.count():
            elemento = self.caja.takeAt(0)
            widget = elemento.widget()
            if widget is not None:
                widget.deleteLater()

    def _chip(self, rotulo: str, clave: str, cuantos: int) -> None:
        boton = QPushButton(f"{rotulo}  {cuantos}")
        boton.setObjectName("chip")
        boton.setCheckable(True)
        boton.setChecked(clave == self._activa)
        boton.setCursor(Qt.PointingHandCursor)
        boton.clicked.connect(lambda _marcado=False, c=clave: self._elegir(c))
        self._grupo.addButton(boton)
        self.caja.addWidget(boton)

    def _elegir(self, clave: str) -> None:
        self._activa = clave
        self.elegida.emit(clave)


__all__ = [
    "Filtros",
    "OTROS",
    "ZonaSoltar",
    "categoria_de",
    "icono_categoria",
    "insignia",
]
