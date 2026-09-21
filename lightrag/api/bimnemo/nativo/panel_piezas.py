"""Las piezas del panel: el reparto del disco, las memorias, las categorías
y los tipos de archivo.

Están aquí y no en `pantalla_panel.py` porque ese fichero ya es el más largo
del paquete y lo que hace es **otra cosa**: pedir datos al motor y repartirlos.
Cómo se dibuja una barra apilada o una tarjeta de categoría no tiene que
estorbar a eso.

## De qué memoria habla cada bloque

Es la misma división que la web, y no es un detalle:

**Todo habla de la memoria abierta**: el reparto del disco, el catálogo de
categorías y los tipos de archivo. La web reparte esto de otra manera —suma
todas las memorias en los tres primeros bloques— y aquí se hizo así al
principio; el resultado era un panel que no cambiaba al cambiar de memoria y
del que no se sabía de qué hablaba. Con una memoria abierta a la vez, lo que
se espera del panel es que describa **esa**.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo import formato, iconos, tema
from lightrag.api.bimnemo.nativo.piezas import Fluida

#: Alto de la barra de reparto, y el de las barritas de las tarjetas.
ALTO_MEDIDOR = 8
ALTO_MEDIDOR_FINO = 4

#: Lo que ocupa una tarjeta de categoría con sus cinco líneas.
ALTO_TARJETA_CATEGORIA = 122

#: Lo que necesita de ancho para que quepa el nombre entero —«Hoja de
#: cálculo» es el más largo— sin recortarlo con puntos suspensivos.
ANCHO_TARJETA_CATEGORIA = 180


def porcentaje(parte: Any, total: Any) -> float:
    try:
        p, t = float(parte), float(total)
    except (TypeError, ValueError):
        return 0.0
    if t <= 0:
        return 0.0
    return p / t * 100.0


def porcentaje_texto(parte: Any, total: Any) -> str:
    """El porcentaje en palabras, sin decimales engañosos.

    Por debajo del 1 % se dice «<1%» y no «0%»: no es lo mismo nada que
    poco, y en un reparto de almacenamiento esa diferencia importa.
    """
    valor = porcentaje(parte, total)
    if valor <= 0:
        return "0%"
    if valor < 1:
        return "<1%"
    # `round` de Python parte los empates al par —90.5 da 90— y la web
    # redondea al alza, que es lo que hace `Math.round`. El mismo dato no
    # puede salir como 90 % en una y 91 % en la otra.
    return f"{int(valor + 0.5)}%"


def ocupadas(categorias: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Las categorías con algún fichero, de mayor a menor peso."""
    return sorted(
        (c for c in categorias if (c.get("files") or 0) > 0),
        key=lambda c: -(c.get("size_bytes") or 0),
    )


class Medidor(QWidget):
    """Una barra apilada: cada trozo, una categoría con su color.

    Se pinta a mano en vez de con widgets porque son trozos de ancho
    proporcional: con cajas habría que recalcular tamaños a cada cambio de
    ventana, y un redondeo de más deja una raya de fondo entre dos trozos.
    """

    def __init__(self, alto: int = ALTO_MEDIDOR, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._trozos: list[tuple[str, float]] = []
        # Alto fijo y ancho elástico: la barra se estira con la tarjeta.
        self.setFixedHeight(alto)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def poner(self, categorias: list[dict[str, Any]], total: Any) -> None:
        self._trozos = [
            (
                str(c.get("color") or "slate"),
                porcentaje(c.get("size_bytes"), total),
            )
            for c in ocupadas(categorias)
        ]
        self.update()

    def poner_uno(self, color: str, parte: Any, total: Any) -> None:
        """Un solo trozo: lo usan las barritas de cada tarjeta."""
        self._trozos = [(color, porcentaje(parte, total))]
        self.update()

    def paintEvent(self, _evento) -> None:  # noqa: N802 (nombre de Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)
        pintor.setPen(Qt.NoPen)

        radio = self.height() / 2
        canal = QPainterPath()
        canal.addRoundedRect(0, 0, self.width(), self.height(), radio, radio)
        pintor.fillPath(canal, QColor(tema.ACTUAL.secundaria))

        # Nada que pintar: se deja el canal vacío. Una barra completa de
        # color neutro se lee como «lleno», que es lo contrario.
        if not self._trozos:
            pintor.end()
            return

        pintor.setClipPath(canal)
        x = 0.0
        for color, parte in self._trozos:
            ancho = self.width() * parte / 100.0
            pintor.fillRect(
                int(x),
                0,
                max(1, int(ancho + 0.5)),
                self.height(),
                QColor(tema.color_categoria(color)[0]),
            )
            x += ancho
        pintor.end()


class Leyenda(QWidget):
    """Los nombres de las categorías con su color y su porcentaje."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("fila")
        self.caja = Fluida(separacion=14, salto=4)
        self.setLayout(self.caja)

    def poner(self, categorias: list[dict[str, Any]], total: Any) -> None:
        while self.caja.count():
            elemento = self.caja.takeAt(0)
            widget = elemento.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        trozos = ocupadas(categorias)
        if not trozos:
            self.caja.addWidget(_texto("Todavía no hay nada almacenado.", "pista"))
            return

        for categoria in trozos:
            self.caja.addWidget(
                _punto_y_texto(
                    str(categoria.get("color") or "slate"),
                    str(categoria.get("label") or ""),
                    porcentaje_texto(categoria.get("size_bytes"), total),
                )
            )


class RejillaCategorias(QWidget):
    """Las ocho categorías del catálogo, con lo que ocupa cada una."""

    elegida = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("fila")
        self._sello: tuple = ()
        self._columnas = 0

        self.rejilla = QGridLayout(self)
        self.rejilla.setContentsMargins(0, 0, 0, 0)
        self.rejilla.setHorizontalSpacing(10)
        self.rejilla.setVerticalSpacing(10)
        self._tarjetas: dict[str, TarjetaCategoria] = {}

    def resizeEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        """Tantas columnas como quepan sin recortar los nombres."""
        super().resizeEvent(evento)
        self._colocar(max(1, min(4, self.width() // ANCHO_TARJETA_CATEGORIA)))

    def poner(self, categorias: list[dict[str, Any]], total: Any):
        sello = tuple(str(c.get("key", "")) for c in categorias)
        if sello != self._sello:
            self._sello = sello
            self._rehacer(categorias)
        for categoria in categorias:
            tarjeta = self._tarjetas.get(str(categoria.get("key", "")))
            if tarjeta is not None:
                tarjeta.poner(categoria, total)

    def _rehacer(self, categorias: list[dict[str, Any]]) -> None:
        for tarjeta in self._tarjetas.values():
            self.rejilla.removeWidget(tarjeta)
            tarjeta.setParent(None)
            tarjeta.deleteLater()
        self._tarjetas.clear()

        for categoria in categorias:
            clave = str(categoria.get("key", ""))
            tarjeta = TarjetaCategoria(categoria)
            tarjeta.clicked.connect(lambda _m=False, c=clave: self.elegida.emit(c))
            self._tarjetas[clave] = tarjeta

        self._columnas = 0
        self._colocar(max(1, min(4, (self.width() or 720) // ANCHO_TARJETA_CATEGORIA)))

    def _colocar(self, columnas: int) -> None:
        """Reparte las tarjetas que ya existen en el número de columnas dado."""
        if columnas == self._columnas or not self._tarjetas:
            return
        self._columnas = columnas

        for puesto, tarjeta in enumerate(self._tarjetas.values()):
            self.rejilla.addWidget(tarjeta, puesto // columnas, puesto % columnas)
            tarjeta.show()
        for columna in range(4):
            self.rejilla.setColumnStretch(columna, 1 if columna < columnas else 0)


class TarjetaCategoria(QPushButton):
    """Una categoría: icono, nombre, cuántos, cuánto pesan y su parte."""

    def __init__(self, categoria: dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("tarjeta-categoria")
        self.setCursor(Qt.PointingHandCursor)
        # Un botón mide por su texto y su icono, NO por lo que lleve dentro:
        # sin esto la tarjeta se queda en el alto de un botón vacío y aplasta
        # sus cinco líneas hasta hacerlas invisibles.
        self.setMinimumHeight(ALTO_TARJETA_CATEGORIA)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip(f"Ver los archivos de {categoria.get('label')}")

        color = str(categoria.get("color") or "slate")
        self.color = color

        columna = QVBoxLayout(self)
        columna.setContentsMargins(12, 10, 12, 10)
        columna.setSpacing(4)

        cabecera = QWidget()
        cabecera.setObjectName("fila")
        fila = QHBoxLayout(cabecera)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(8)

        marca = QLabel()
        marca.setFixedSize(22, 22)
        marca.setAlignment(Qt.AlignCenter)
        fuerte, suave = tema.color_categoria(color)
        marca.setStyleSheet(f"background: {suave}; border-radius: 6px;")
        marca.setPixmap(iconos.pixmap(str(categoria.get("icon") or ""), 13, fuerte))
        fila.addWidget(marca)

        self.nombre = _texto(str(categoria.get("label") or ""), "nombre-categoria")
        fila.addWidget(self.nombre, 1)
        columna.addWidget(cabecera)

        cuenta = QWidget()
        cuenta.setObjectName("fila")
        caja = QHBoxLayout(cuenta)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(5)
        self.cuantos = _texto("0", "cifra-categoria")
        caja.addWidget(self.cuantos)
        self.unidad = _texto("archivos", "pista")
        caja.addWidget(self.unidad)
        caja.addStretch(1)
        columna.addWidget(cuenta)

        self.tamano = _texto("0 B", "dato-valor")
        columna.addWidget(self.tamano)

        self.barra = Medidor(ALTO_MEDIDOR_FINO)
        columna.addWidget(self.barra)

        self.parte = _texto("0%", "pista")
        columna.addWidget(self.parte)

        for hijo in (
            self.nombre,
            self.cuantos,
            self.unidad,
            self.tamano,
            self.parte,
            self.barra,
            marca,
            cabecera,
            cuenta,
        ):
            hijo.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def poner(self, categoria: dict[str, Any], total: Any) -> None:
        cuantos = int(categoria.get("files") or 0)
        self.cuantos.setText(formato.numero(cuantos))
        self.unidad.setText("archivo" if cuantos == 1 else "archivos")
        self.tamano.setText(formato.tamano(categoria.get("size_bytes")))
        self.barra.poner_uno(self.color, categoria.get("size_bytes"), total)
        self.parte.setText(porcentaje_texto(categoria.get("size_bytes"), total))
        # Una categoría vacía se apaga en vez de desaparecer: el catálogo
        # completo dice lo que BIMNEMO sabe clasificar, y eso también informa.
        self.setProperty("vacia", "si" if cuantos == 0 else "")
        self.style().unpolish(self)
        self.style().polish(self)


class ResumenCarril(QWidget):
    """Lo que ocupa esta memoria, al pie del carril.

    Es el mismo dato que el panel, en pequeño y siempre a la vista: cuánto
    hay guardado en la memoria abierta, cuántos archivos son y en qué
    categorías caen. Pulsar una categoría lleva a Archivos con ese filtro.

    Se alimenta de la lectura que ya hace el panel —nadie pide nada dos
    veces— y **se esconde con el carril estrecho**: en sesenta píxeles no
    cabe ni la cifra ni un solo chip.
    """

    elegida = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("resumen-carril")

        columna = QVBoxLayout(self)
        columna.setContentsMargins(16, 12, 16, 8)
        columna.setSpacing(6)

        columna.addWidget(self._rotulo("disco", "Almacenado"))

        self.tamano = _texto("—", "cifra-carril")
        columna.addWidget(self.tamano)

        self.cuantos = _texto("—", "pista")
        columna.addWidget(self.cuantos)

        self.medidor = Medidor(ALTO_MEDIDOR_FINO)
        columna.addWidget(self.medidor)

        columna.addSpacing(8)
        columna.addWidget(self._rotulo("categorias", "Categorías"))

        self.chips = QWidget()
        self.chips.setObjectName("fila")
        self.caja_chips = Fluida(separacion=6, salto=6)
        self.chips.setLayout(self.caja_chips)
        columna.addWidget(self.chips)

    @staticmethod
    def _rotulo(icono: str, texto: str) -> QWidget:
        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(6)

        marca = QLabel()
        iconos.poner(marca, icono, 11, "texto_3")
        caja.addWidget(marca)
        caja.addWidget(_texto(texto.upper(), "rotulo-carril"))
        caja.addStretch(1)
        return fila

    def poner(self, almacen: dict[str, Any]) -> None:
        octetos = almacen.get("total_bytes")
        cuantos = int(almacen.get("total_files") or 0)
        categorias = almacen.get("categories") or []

        self.tamano.setText(formato.tamano(octetos))
        self.cuantos.setText(
            f"{formato.numero(cuantos)} archivo" + ("" if cuantos == 1 else "s")
        )
        self.medidor.poner(categorias, octetos)

        while self.caja_chips.count():
            elemento = self.caja_chips.takeAt(0)
            widget = elemento.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        usadas = ocupadas(categorias)
        if not usadas:
            self.caja_chips.addWidget(_texto("Sin archivos todavía.", "pista"))
            return

        for categoria in usadas:
            self.caja_chips.addWidget(self._chip(categoria))

    def _chip(self, categoria: dict[str, Any]) -> QPushButton:
        clave = str(categoria.get("key", ""))
        boton = QPushButton(
            f"{categoria.get('label', '')}  {categoria.get('files', 0)}"
        )
        boton.setObjectName("chip")
        boton.setCursor(Qt.PointingHandCursor)
        boton.setToolTip(
            f"{categoria.get('label', '')}: {formato.tamano(categoria.get('size_bytes'))}"
        )
        iconos.poner(boton, str(categoria.get("icon") or ""), 12, "texto_2")
        boton.clicked.connect(lambda _m=False, c=clave: self.elegida.emit(c))
        return boton


class ListaTipos(QWidget):
    """Los tipos de archivo de la memoria abierta, por peso."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("fila")
        self.columna = QVBoxLayout(self)
        self.columna.setContentsMargins(0, 0, 0, 0)
        self.columna.setSpacing(8)

    def poner(self, tipos: list[dict[str, Any]], total: Any) -> None:
        while self.columna.count():
            elemento = self.columna.takeAt(0)
            widget = elemento.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        if not tipos:
            self.columna.addWidget(
                _texto("Todavía no hay archivos que clasificar.", "pista")
            )
            return

        for tipo in tipos:
            self.columna.addWidget(_fila_tipo(tipo, total))


# --- Piezas pequeñas --------------------------------------------------------


def _fila_tipo(tipo: dict[str, Any], total: Any) -> QWidget:
    fila = QWidget()
    fila.setObjectName("fila")
    caja = QHBoxLayout(fila)
    caja.setContentsMargins(0, 0, 0, 0)
    caja.setSpacing(10)

    extension = _texto(str(tipo.get("type") or ""), "extension")
    extension.setFixedWidth(52)
    extension.setAlignment(Qt.AlignCenter)
    caja.addWidget(extension)

    barra = Medidor(ALTO_MEDIDOR_FINO)
    barra.poner_uno("slate", tipo.get("size_bytes"), total)
    caja.addWidget(barra, 1)

    cuantos = formato.numero(tipo.get("files"))
    caja.addWidget(
        _texto(f"{cuantos} · {formato.tamano(tipo.get('size_bytes'))}", "pista")
    )
    return fila


def _punto_y_texto(color: str, rotulo: str, parte: str) -> QWidget:
    fila = QWidget()
    fila.setObjectName("fila")
    caja = QHBoxLayout(fila)
    caja.setContentsMargins(0, 0, 0, 0)
    caja.setSpacing(6)

    punto = _texto("●", "punto-leyenda")
    punto.setStyleSheet(f"color: {tema.color_categoria(color)[0]}; font-size: 9px;")
    caja.addWidget(punto)
    caja.addWidget(_texto(rotulo, "dato-valor"))
    caja.addWidget(_texto(parte, "pista"))
    return fila


def _texto(texto: str, objeto: str) -> QLabel:
    etiqueta = QLabel(texto)
    etiqueta.setObjectName(objeto)
    return etiqueta


def _numero(ancho: int) -> QLabel:
    etiqueta = _texto("—", "dato-valor")
    etiqueta.setFixedWidth(ancho)
    etiqueta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return etiqueta


__all__ = [
    "ALTO_MEDIDOR",
    "ALTO_MEDIDOR_FINO",
    "Leyenda",
    "ListaTipos",
    "Medidor",
    "RejillaCategorias",
    "ResumenCarril",
    "TarjetaCategoria",
    "ocupadas",
    "porcentaje",
    "porcentaje_texto",
]
