"""Lo que hace falta para probar widgets de Qt sin pantalla.

Qt no viaja en la instalación mínima —son 60 MB de bibliotecas nativas—, así
que estas pruebas **se saltan** donde no está en vez de romper la suite.
"""

from __future__ import annotations

import os

import pytest

# Antes de que nadie importe PySide6: sin esto Qt intenta abrir una ventana
# de verdad y en un servidor de integración continua no hay ninguna.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="La ventana nativa necesita Qt (PySide6).")


@pytest.fixture(scope="session")
def aplicacion():
    """La `QApplication`, una sola por proceso.

    Qt no admite dos, y crear una por prueba deja la segunda muerta al
    instante: los widgets se construyen sin quejarse y luego no miden nada.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
