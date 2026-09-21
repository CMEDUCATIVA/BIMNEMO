"""Lo que hace falta para probar widgets de Qt sin pantalla.

Qt no viaja en la instalación mínima —son 60 MB de bibliotecas nativas—, así
que estas pruebas **se saltan** donde no está en vez de romper la suite.
"""

from __future__ import annotations

import os
from typing import Any

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


LISTA: dict[str, Any] = {
    "nemos": [
        {"id": "", "name": "General", "protected": True, "live": True},
        {"id": "obra-sur", "name": "Obra Sur", "protected": False},
    ],
    "default": "",
}


@pytest.fixture()
def ventana(aplicacion, tmp_path, monkeypatch):
    """Una ventana entera, con un motor que no toca la red.

    Se construye de verdad —las seis pantallas— porque lo que se prueba aquí
    es precisamente el cableado entre ellas, la barra y el carril. Los
    ajustes van a un fichero de usar y tirar: sin eso, la prueba le cambiaría
    el tema y la memoria abierta al BIMNEMO de quien la ejecuta.
    """
    from PySide6.QtCore import QObject, QSettings, Signal

    class MotorFalso(QObject):
        caido = Signal(str)

        def __init__(self) -> None:
            super().__init__()
            self.base = "http://127.0.0.1:0"
            self.memoria = ""
            # La clave de acceso al motor, como el de verdad: la pantalla de
            # API la lee para decir si está puesta.
            self.clave = ""
            self.pedidos: list[str] = []
            self.respuestas: dict[str, Any] = {"/bimnemo/nemos": LISTA}

        def usar_memoria(self, nemo: str) -> None:
            self.memoria = nemo

        def usar_clave(self, clave: str) -> None:
            self.clave = clave

        def _contestar(self, ruta, bien):
            self.pedidos.append(ruta)
            if bien is None or ruta not in self.respuestas:
                return
            respuesta = self.respuestas[ruta]
            # Una respuesta puede ser una función: así depende de la memoria
            # abierta en ese instante, como la del motor de verdad.
            bien(respuesta() if callable(respuesta) else respuesta)

        def get(self, ruta, bien=None, mal=None):
            self._contestar(ruta, bien)

        def post(self, ruta, cuerpo=None, bien=None, mal=None):
            self._contestar(ruta, bien)

        def parchear(self, ruta, cuerpo=None, bien=None, mal=None):
            self._contestar(ruta, bien)

        def borrar(self, ruta, cuerpo=None, bien=None, mal=None):
            self._contestar(ruta, bien)

        def subir(self, ruta, fichero, bien=None, mal=None, avance=None):
            self._contestar(ruta, bien)

    from lightrag.api.bimnemo.nativo import memorias as modulo_memorias
    from lightrag.api.bimnemo.nativo import ventana as modulo_ventana

    guardados = QSettings(str(tmp_path / "bimnemo.ini"), QSettings.IniFormat)
    monkeypatch.setattr(modulo_memorias, "ajustes", lambda: guardados)
    monkeypatch.setattr(modulo_ventana, "ajustes", lambda: guardados)

    return modulo_ventana.Ventana(MotorFalso(), "1.4.0")
