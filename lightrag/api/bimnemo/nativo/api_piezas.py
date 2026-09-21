"""Las piezas de la pantalla «API»: pestañas, paneles, filas y el interruptor.

Están fuera de `pantalla_api.py` para que esa pantalla se quede con lo que
hace —resolver las rutas de la memoria abierta y montar los paneles— y no con
cuatrocientas líneas de construir widgets.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo import iconos

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
    """

    def __init__(self, titulo: str, icono: str = "", nota: str = "") -> None:
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
            marca.setPixmap(iconos.pixmap(icono, 15, "azul"))
            fila.addWidget(marca)

        etiqueta = QLabel(titulo)
        etiqueta.setObjectName("subtitulo")
        fila.addWidget(etiqueta)
        fila.addStretch(1)

        self.nota = QLabel(nota)
        self.nota.setObjectName("descripcion")
        fila.addWidget(self.nota)

        self.columna.addWidget(cabecera)

    def anadir(self, widget: QWidget) -> None:
        self.columna.addWidget(widget)


class Fila(QFrame):
    """Un endpoint: verbo, ruta, para qué sirve y copiar."""

    def __init__(self, endpoint: dict[str, Any], base: str) -> None:
        super().__init__()
        self.setObjectName("endpoint")
        self.endpoint = endpoint
        self.base = base

        columna = QVBoxLayout(self)
        columna.setContentsMargins(12, 9, 12, 9)
        columna.setSpacing(4)

        arriba = QWidget()
        arriba.setObjectName("fila")
        fila = QHBoxLayout(arriba)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)

        metodo = str(endpoint.get("method") or "")
        verbo = QLabel(metodo)
        verbo.setObjectName("verbo")
        verbo.setFixedWidth(62)
        verbo.setAlignment(Qt.AlignCenter)
        color = COLOR_VERBO.get(metodo, "#94a3b8")
        verbo.setStyleSheet(
            f"color: {color}; border: 1px solid {color}; border-radius: 5px;"
            " padding: 2px 0; font-weight: 700; font-size: 10px;"
        )
        fila.addWidget(verbo)

        ruta = QLabel(str(endpoint.get("ruta") or endpoint.get("path") or ""))
        ruta.setObjectName("ruta")
        ruta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fila.addWidget(ruta)

        proposito = QLabel(str(endpoint.get("purpose") or ""))
        proposito.setObjectName("descripcion")
        proposito.setWordWrap(True)
        fila.addWidget(proposito, 1)

        copiar = QPushButton("Copiar")
        copiar.setObjectName("copiar-linea")
        copiar.setCursor(Qt.PointingHandCursor)
        copiar.clicked.connect(self._copiar)
        fila.addWidget(copiar)

        columna.addWidget(arriba)

        cuerpo = endpoint.get("body")
        if cuerpo:
            ejemplo = QLabel(json.dumps(cuerpo, ensure_ascii=False))
            ejemplo.setObjectName("codigo")
            ejemplo.setWordWrap(True)
            ejemplo.setTextInteractionFlags(Qt.TextSelectableByMouse)
            columna.addWidget(ejemplo)

    def _copiar(self) -> None:
        """Se copia lo que hace falta para llamarlo, no la ruta sola."""
        ruta = self.endpoint.get("ruta") or self.endpoint.get("path")
        partes = [f"{self.endpoint.get('method')} {self.base}{ruta}"]
        cuerpo = self.endpoint.get("body")
        if cuerpo:
            partes.append(json.dumps(cuerpo, ensure_ascii=False, indent=2))
        al_portapapeles("\n".join(partes))


class Interruptor(QPushButton):
    """Un interruptor de sí/no con aspecto de interruptor.

    Qt trae `QCheckBox`, que es una casilla: sirve para «acepto las
    condiciones», no para encender algo. Esto es un botón que se queda
    pulsado y se pinta como una palanca, que es lo que la gente reconoce
    como «activado / desactivado».
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("interruptor")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 24)


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
