"""El aviso de «nombre demasiado largo», con el nombre para editar.

Sale **antes** de subir, y solo con los archivos que no caben: si se sueltan
veinte y tres tienen el nombre largo, una ventana con esos tres. También lo
abre «Renombrar» en la fila de un archivo que ya falló por eso.

Cada archivo trae:

- el nombre ya acortado por ``nombres.sugerir`` —una propuesta, se edita—;
- la extensión fija al lado: cambiarla cambiaría cómo se lee el documento;
- un contador que se mueve al escribir, en verde si cabe y en rojo si no;
- debajo, qué falla: largo, caracteres que Windows no admite, repetido.

El botón de seguir no se activa hasta que todos sirven. Qué cabe lo dice
``bimnemo/nombres.py`` con la ruta real de la memoria, que da el motor.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo import nombres

VERDE = "#10b981"
ROJO = "#ef4444"


class FilaNombre(QWidget):
    """Un archivo: de dónde viene, el nombre nuevo y si sirve."""

    def __init__(self, original: str, limite: int, sugerido: str) -> None:
        super().__init__()
        self.original = original
        self.limite = limite
        self.extension = nombres.extension(original)

        rejilla = QGridLayout(self)
        rejilla.setContentsMargins(0, 6, 0, 6)
        rejilla.setHorizontalSpacing(8)
        rejilla.setVerticalSpacing(3)

        antes = QLabel(f"Ahora: {original}")
        antes.setObjectName("pista")
        antes.setToolTip(original)
        antes.setWordWrap(True)
        rejilla.addWidget(antes, 0, 0, 1, 3)

        base = sugerido[: -len(self.extension)] if self.extension else sugerido
        self.campo = QLineEdit(base)
        self.campo.setToolTip(
            "El nombre con el que se guardará en la memoria. El archivo de tu "
            "PC no cambia."
        )
        rejilla.addWidget(self.campo, 1, 0)

        rejilla.addWidget(QLabel(self.extension), 1, 1)

        self.contador = QLabel("")
        self.contador.setMinimumWidth(70)
        self.contador.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        rejilla.addWidget(self.contador, 1, 2)

        self.fallos = QLabel("")
        self.fallos.setWordWrap(True)
        self.fallos.setStyleSheet(f"color: {ROJO};")
        rejilla.addWidget(self.fallos, 2, 0, 1, 3)
        rejilla.setColumnStretch(0, 1)

    def nombre(self) -> str:
        return self.campo.text().strip() + self.extension

    def pintar(self, problemas: list[str]) -> bool:
        """El contador y los fallos. Devuelve si el nombre sirve."""
        largo = len(self.nombre())
        cabe = largo <= self.limite
        self.contador.setText(f"{largo} / {self.limite}")
        self.contador.setStyleSheet(
            f"color: {VERDE if cabe else ROJO}; font-weight: 600;"
        )
        self.fallos.setText("  ".join(problemas))
        self.fallos.setVisible(bool(problemas))
        return not problemas


class DialogoNombres(QDialog):
    """Varios archivos a la vez; devuelve ``{original: nombre nuevo}``."""

    def __init__(
        self,
        padre: QWidget,
        originales: list[str],
        limite_de: Callable[[str], int],
        existentes: frozenset[str],
        *,
        titulo: str = "Nombres demasiado largos",
        explicacion: str = "",
        seguir: str = "Subir con estos nombres",
    ) -> None:
        super().__init__(padre)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(620)
        self._existentes = frozenset(existentes) - frozenset(originales)

        columna = QVBoxLayout(self)
        columna.setContentsMargins(20, 18, 20, 16)
        columna.setSpacing(10)

        texto = QLabel(
            explicacion
            or (
                "Windows no admite rutas de más de 260 caracteres, y al leer "
                "un documento BIMNEMO usa su nombre dos veces dentro de la "
                "ruta. En esta memoria caben los que marca el contador. Te "
                "proponemos un nombre más corto: cámbialo si quieres."
            )
        )
        texto.setObjectName("descripcion")
        texto.setWordWrap(True)
        columna.addWidget(texto)

        caja = QWidget()
        lista = QVBoxLayout(caja)
        lista.setContentsMargins(0, 0, 0, 0)
        self.filas: list[FilaNombre] = []
        usados = set(self._existentes)
        for original in originales:
            limite = limite_de(original)
            sugerido = nombres.sugerir(original, limite, frozenset(usados))
            usados.add(sugerido)
            fila = FilaNombre(original, limite, sugerido)
            fila.campo.textChanged.connect(self._revisar)
            self.filas.append(fila)
            lista.addWidget(fila)
        lista.addStretch(1)

        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QScrollArea.NoFrame)
        desplazable.setWidget(caja)
        desplazable.setMaximumHeight(420)
        columna.addWidget(desplazable)

        botones = QHBoxLayout()
        botones.addStretch(1)
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        botones.addWidget(cancelar)
        self.boton_seguir = QPushButton(seguir)
        self.boton_seguir.setObjectName("principal")
        self.boton_seguir.setDefault(True)
        self.boton_seguir.clicked.connect(self.accept)
        botones.addWidget(self.boton_seguir)
        columna.addLayout(botones)

        self._revisar()

    def _revisar(self) -> None:
        """Cada vez que se escribe: qué falla en cada uno, y si se puede seguir."""
        todos_bien = True
        for fila in self.filas:
            # Tampoco pueden repetirse entre ellos.
            otros = {f.nombre() for f in self.filas if f is not fila}
            fallos = nombres.problemas(
                fila.nombre(), fila.limite, self._existentes | frozenset(otros)
            )
            todos_bien = fila.pintar(fallos) and todos_bien
        self.boton_seguir.setEnabled(todos_bien)

    def resultado(self) -> dict[str, str]:
        return {fila.original: fila.nombre() for fila in self.filas}


__all__ = ["DialogoNombres", "FilaNombre"]
