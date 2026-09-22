"""Las dos barras de razonamiento de «Modelo de lenguaje».

Qué nivel admite cada modelo lo decide el motor (``bimnemo/razonamiento.py``)
y llega en el catálogo: aquí no se sabe nada de proveedores. Esta pieza pinta
los niveles que le den y devuelve el que se eligió.

- **Al extraer**: indexar documentos y sacar las palabras clave de cada
  pregunta. Casi todo el gasto.
- **Al responder**: la respuesta del chat.

La primera posición es siempre «Lo que decida el modelo», que no escribe
nada. Un modelo sin control no enseña barras: lo dice.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

#: Igual que ``razonamiento.MANUAL``: hay algo puesto a mano en el ``.env``
#: que ninguna posición de la barra representa.
MANUAL = "manual"

#: Rótulos cortos a propósito: van en la misma columna que «Proveedor» o
#: «Modelo», y uno más largo empujaría su barra fuera de la línea de los
#: desplegables. El «Razonamiento» lo pone el título de encima.
BARRAS = (
    (
        "indexar",
        "Al extraer",
        "Indexar documentos y sacar las palabras clave de cada pregunta. Es "
        "casi todo el gasto: apagarlo suele abaratar mucho.",
    ),
    (
        "responder",
        "Al responder",
        "La respuesta del chat. Son pocos tokens; aquí razonar sí se nota.",
    ),
)


class Barra(QWidget):
    """Una fila: nombre, deslizador y el nivel elegido escrito."""

    def __init__(self, nombre: str, ayuda: str) -> None:
        super().__init__()
        self.setObjectName("fila")
        self._niveles: list[dict[str, Any]] = []
        self._manual = False

        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(2)

        fila = QHBoxLayout()
        fila.setSpacing(12)
        etiqueta = QLabel(nombre)
        etiqueta.setObjectName("dato-nombre")
        etiqueta.setMinimumWidth(130)
        etiqueta.setToolTip(ayuda)
        fila.addWidget(etiqueta)

        self.deslizador = QSlider(Qt.Horizontal)
        self.deslizador.setTickPosition(QSlider.TicksBelow)
        self.deslizador.setTickInterval(1)
        self.deslizador.setPageStep(1)
        self.deslizador.setToolTip(ayuda)
        self.deslizador.valueChanged.connect(self._movido)
        fila.addWidget(self.deslizador, 1)

        self.valor = QLabel("")
        self.valor.setObjectName("dato-valor")
        self.valor.setMinimumWidth(170)
        fila.addWidget(self.valor)
        columna.addLayout(fila)

    def poner_niveles(self, niveles: list[dict[str, Any]]) -> None:
        self._niveles = list(niveles)
        self.deslizador.blockSignals(True)
        self.deslizador.setRange(0, max(len(self._niveles) - 1, 0))
        self.deslizador.setValue(0)
        self.deslizador.blockSignals(False)
        self._manual = False
        self._rotular()

    def elegir(self, nivel: str) -> None:
        """Coloca la barra en ``nivel``; uno que no existe vuelve al principio."""
        self._manual = nivel == MANUAL
        indice = next(
            (i for i, n in enumerate(self._niveles) if n.get("id") == nivel), 0
        )
        self.deslizador.blockSignals(True)
        self.deslizador.setValue(indice)
        self.deslizador.blockSignals(False)
        self._rotular()

    def elegido(self) -> str:
        if self._manual:
            return MANUAL
        indice = self.deslizador.value()
        if 0 <= indice < len(self._niveles):
            return str(self._niveles[indice].get("id") or "")
        return ""

    def _movido(self, _valor: int) -> None:
        # Moverla es decidir: el ajuste a mano deja de conservarse.
        self._manual = False
        self._rotular()

    def _rotular(self) -> None:
        if self._manual:
            self.valor.setText("Ajuste a mano (se conserva)")
            return
        indice = self.deslizador.value()
        if 0 <= indice < len(self._niveles):
            self.valor.setText(str(self._niveles[indice].get("label") or ""))


class ControlRazonamiento(QWidget):
    """Las dos barras, o la explicación de por qué no hay."""

    def __init__(self) -> None:
        super().__init__()
        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 4, 0, 0)
        columna.setSpacing(8)

        self.titulo = QLabel("Razonamiento")
        self.titulo.setObjectName("dato-nombre")
        self.titulo.setToolTip(
            "Cuánto «piensa» el modelo antes de contestar. Pensar se cobra "
            "como tokens de salida."
        )
        columna.addWidget(self.titulo)

        self.barras: dict[str, Barra] = {}
        for clave, nombre, ayuda in BARRAS:
            barra = Barra(nombre, ayuda)
            self.barras[clave] = barra
            columna.addWidget(barra)

        self.nota = QLabel("")
        self.nota.setObjectName("pista")
        self.nota.setWordWrap(True)
        columna.addWidget(self.nota)

        self.poner_niveles(None)

    def poner_niveles(self, info: Optional[dict[str, Any]]) -> None:
        """Los niveles del modelo elegido; ``None`` si no tiene control."""
        niveles = list((info or {}).get("levels") or [])
        hay = len(niveles) > 1
        for barra in self.barras.values():
            barra.poner_niveles(niveles)
            barra.setVisible(hay)
        self.titulo.setVisible(hay)
        if hay:
            self.nota.setText((info or {}).get("note") or "")
        else:
            self.nota.setText(
                "Razonamiento: este modelo no razona, o su proveedor no deja "
                "controlarlo desde aquí. Se usa lo que decida el modelo."
            )

    def poner_elegidos(self, elegidos: dict[str, str]) -> None:
        for clave, barra in self.barras.items():
            barra.elegir(str((elegidos or {}).get(clave) or ""))

    def elegidos(self) -> dict[str, str]:
        return {clave: barra.elegido() for clave, barra in self.barras.items()}


__all__ = ["Barra", "ControlRazonamiento", "MANUAL"]
