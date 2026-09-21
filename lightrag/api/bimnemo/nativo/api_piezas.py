"""Las piezas de la pantalla «API»: pestañas, paneles, la tabla y el interruptor.

Están fuera de `pantalla_api.py` para que esa pantalla se quede con lo que
hace —resolver las rutas de la memoria abierta y montar los paneles— y no con
cuatrocientas líneas de construir widgets.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo import iconos, tema

#: El color de cada verbo. El rojo del borrado no es decorativo: avisa antes
#: de que a nadie le dé tiempo a leer la línea.
COLOR_VERBO = {
    "GET": "#0ea5e9",
    "POST": "#10b981",
    "PATCH": "#f59e0b",
    "PUT": "#f59e0b",
    "DELETE": "#ef4444",
}


def al_portapapeles(texto: str) -> None:
    QGuiApplication.clipboard().setText(texto)


class Linea(QWidget):
    """Una raya de un píxel que sigue al tema.

    Se pinta en vez de darle un color en la hoja de estilo porque una hoja
    se genera una vez y el tema se cambia en caliente: la raya se quedaría
    del color del tema anterior.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _evento) -> None:  # noqa: N802 (nombre de Qt)
        QPainter(self).fillRect(self.rect(), QColor(tema.ACTUAL.borde))


class Pestanas(QFrame):
    """Guía · Swagger · ReDoc, como en la web."""

    elegida = Signal(str)

    def __init__(self, nombres: tuple[str, ...]) -> None:
        super().__init__()
        self.setObjectName("pestanas")

        fila = QHBoxLayout(self)
        fila.setContentsMargins(3, 3, 3, 3)
        fila.setSpacing(2)

        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)

        for indice, nombre in enumerate(nombres):
            boton = QPushButton(nombre)
            boton.setObjectName("pestana")
            boton.setCheckable(True)
            boton.setCursor(Qt.PointingHandCursor)
            boton.clicked.connect(lambda _m=False, n=nombre: self.elegida.emit(n))
            self._grupo.addButton(boton, indice)
            fila.addWidget(boton)

        self._grupo.buttons()[0].setChecked(True)


class Panel(QFrame):
    """Una caja con título, una nota a la derecha y lo que se le meta.

    La nota de la derecha es lo que en la web dice «General» o «Sin
    autenticación en esta instancia»: el dato que cambia el significado de
    todo lo que hay debajo, y que sin él se lee mal.

    `boton` pone una acción **en la propia cabecera**, que es donde la busca
    quien ya ha leído el título y quiere llevárselo.
    """

    def __init__(
        self,
        titulo: str,
        icono: str = "",
        nota: str = "",
        boton: str = "",
    ) -> None:
        super().__init__()
        self.setObjectName("tarjeta")

        self.columna = QVBoxLayout(self)
        self.columna.setContentsMargins(16, 14, 16, 16)
        self.columna.setSpacing(10)

        cabecera = QWidget()
        cabecera.setObjectName("fila")
        fila = QHBoxLayout(cabecera)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(8)

        if icono:
            marca = QLabel()
            iconos.poner(marca, icono, 15, "azul")
            fila.addWidget(marca)

        etiqueta = QLabel(titulo)
        etiqueta.setObjectName("subtitulo")
        fila.addWidget(etiqueta)
        fila.addStretch(1)

        self.nota = QLabel(nota)
        self.nota.setObjectName("descripcion")
        fila.addWidget(self.nota)

        self.boton: Optional[QPushButton] = None
        if boton:
            self.boton = QPushButton(f"  {boton}")
            iconos.poner(self.boton, "copiar", 12, "texto_2")
            self.boton.setCursor(Qt.PointingHandCursor)
            fila.addWidget(self.boton)

        self.columna.addWidget(cabecera)

    def anadir(self, widget: QWidget) -> None:
        self.columna.addWidget(widget)


class Tabla(QWidget):
    """Los endpoints de un ámbito, en cuatro columnas.

    ## Por qué una rejilla y no una fila por endpoint

    Con una fila independiente por endpoint, cada una repartía su ancho a su
    manera: las rutas empezaban en un sitio distinto en cada línea y la
    columna de «para qué sirve» bailaba. Doce endpoints así no son una tabla,
    son doce frases sueltas, y para encontrar el que se busca hay que leerlas
    todas.

    En una rejilla las cuatro columnas mandan sobre todas las filas, así que
    la vista se recorre por columnas: se baja por los verbos hasta el POST
    que se quiere, y la ruta está justo al lado.

    ## El cuerpo no se pinta

    Cada endpoint lleva en el manifiesto el cuerpo mínimo que hay que
    mandarle. Debajo de cada ruta eran doce trozos de JSON amontonados que
    tapaban lo que se venía a buscar. Sigue estando —es lo que hace falta
    para llamar de verdad—, pero donde se necesita: en lo que copia el botón,
    y en su globo de ayuda antes de pulsarlo.
    """

    #: Los títulos, y a cuánto estira cada columna.
    COLUMNAS = (("Acción", 0), ("Ruta", 0), ("Para qué sirve", 1), ("", 0))

    def __init__(self, filas: list[dict[str, Any]], base: str) -> None:
        super().__init__()
        self.setObjectName("fila")
        self.base = base

        rejilla = QGridLayout(self)
        rejilla.setContentsMargins(0, 0, 0, 0)
        rejilla.setHorizontalSpacing(14)
        rejilla.setVerticalSpacing(7)

        for columna, (titulo, estira) in enumerate(self.COLUMNAS):
            rejilla.setColumnStretch(columna, estira)
            rotulo = QLabel(titulo.upper())
            rotulo.setObjectName("columna")
            rejilla.addWidget(rotulo, 0, columna)

        rejilla.addWidget(Linea(), 1, 0, 1, 4)

        for numero, endpoint in enumerate(filas):
            fila = 2 + numero * 2
            rejilla.addWidget(self._verbo(endpoint), fila, 0)
            rejilla.addWidget(self._ruta(endpoint), fila, 1)
            rejilla.addWidget(self._proposito(endpoint), fila, 2)
            rejilla.addWidget(self._copiar(endpoint), fila, 3)
            if numero < len(filas) - 1:
                rejilla.addWidget(Linea(), fila + 1, 0, 1, 4)

    # -- las cuatro columnas ------------------------------------------------

    @staticmethod
    def _verbo(endpoint: dict[str, Any]) -> QLabel:
        metodo = str(endpoint.get("method") or "")
        etiqueta = QLabel(metodo)
        etiqueta.setObjectName("verbo")
        etiqueta.setFixedWidth(62)
        etiqueta.setAlignment(Qt.AlignCenter)
        color = COLOR_VERBO.get(metodo, "#94a3b8")
        etiqueta.setStyleSheet(
            f"color: {color}; border: 1px solid {color}; border-radius: 5px;"
            " padding: 2px 0; font-weight: 700; font-size: 10px;"
        )
        return etiqueta

    @staticmethod
    def _ruta(endpoint: dict[str, Any]) -> QLabel:
        etiqueta = QLabel(str(endpoint.get("ruta") or endpoint.get("path") or ""))
        etiqueta.setObjectName("ruta")
        etiqueta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return etiqueta

    @staticmethod
    def _proposito(endpoint: dict[str, Any]) -> QLabel:
        etiqueta = QLabel(str(endpoint.get("purpose") or ""))
        etiqueta.setObjectName("descripcion")
        etiqueta.setWordWrap(True)
        # Sin esto la columna crece con el texto más largo y se come a las
        # demás: es la única que puede partir en varias líneas.
        etiqueta.setMinimumWidth(180)
        return etiqueta

    def _copiar(self, endpoint: dict[str, Any]) -> QPushButton:
        boton = QPushButton()
        boton.setObjectName("copiar-linea")
        iconos.poner(boton, "copiar", 13, "texto_3")
        boton.setFixedSize(28, 24)
        boton.setCursor(Qt.PointingHandCursor)
        texto = self.llamada(endpoint, self.base)
        boton.setToolTip(f"Copiar la llamada:\n{texto}")
        boton.clicked.connect(lambda _m=False, t=texto: al_portapapeles(t))
        return boton

    @staticmethod
    def llamada(endpoint: dict[str, Any], base: str) -> str:
        """Lo que hace falta para llamarlo: verbo, dirección y cuerpo.

        La ruta sola no basta. Quien copia `/bimnemo/memory/remember` todavía
        no sabe que hay que mandarle `text` y `source`, y tiene que ir a
        buscarlo a Swagger — que es justo el viaje que esta pantalla existe
        para ahorrar.
        """
        ruta = endpoint.get("ruta") or endpoint.get("path")
        partes = [f"{endpoint.get('method')} {base}{ruta}"]
        cuerpo = endpoint.get("body")
        if cuerpo:
            partes.append(json.dumps(cuerpo, ensure_ascii=False, indent=2))
        return "\n".join(partes)


class Interruptor(QPushButton):
    """Un interruptor de sí/no con aspecto de interruptor.

    Qt trae `QCheckBox`, que es una casilla: sirve para «acepto las
    condiciones», no para encender algo.

    Se pinta a mano porque la hoja de estilo no puede dibujar la bola: en QSS
    un botón es una caja, y lo único que se movía al pulsarlo era el color
    del fondo. Un rectángulo que cambia de color no se lee como encendido o
    apagado; una palanca que se desplaza, sí.
    """

    #: Diámetro de la bola y aire a su alrededor.
    BOLA = 18
    AIRE = 3

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("interruptor")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.BOLA * 2 + self.AIRE * 3, self.BOLA + self.AIRE * 2)

    def paintEvent(self, _evento) -> None:  # noqa: N802 (nombre de Qt)
        p = tema.ACTUAL
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)

        alto = self.height()
        pintor.setPen(Qt.NoPen)
        pintor.setBrush(QColor(p.azul if self.isChecked() else p.terciaria))
        pintor.drawRoundedRect(self.rect(), alto / 2, alto / 2)

        x = self.width() - self.BOLA - self.AIRE if self.isChecked() else self.AIRE
        pintor.setBrush(QColor(p.sobre_azul if self.isChecked() else p.texto_3))
        pintor.drawEllipse(x, self.AIRE, self.BOLA, self.BOLA)


def fila_con_boton(
    texto: str, rotulo: str, al_pulsar: Callable[[], None], codigo: bool = True
) -> QWidget:
    """Un texto con su botón al lado. Se usa para direcciones y claves."""
    caja = QWidget()
    caja.setObjectName("fila")
    fila = QHBoxLayout(caja)
    fila.setContentsMargins(0, 0, 0, 0)
    fila.setSpacing(10)

    etiqueta = QLabel(texto)
    etiqueta.setObjectName("codigo" if codigo else "descripcion")
    etiqueta.setTextInteractionFlags(Qt.TextSelectableByMouse)
    fila.addWidget(etiqueta, 1)

    boton = QPushButton(rotulo)
    boton.setCursor(Qt.PointingHandCursor)
    boton.clicked.connect(al_pulsar)
    fila.addWidget(boton)

    caja.etiqueta = etiqueta  # type: ignore[attr-defined]
    caja.boton = boton  # type: ignore[attr-defined]
    return caja
