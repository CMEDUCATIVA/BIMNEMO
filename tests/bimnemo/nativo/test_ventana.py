"""El armazón de la ventana: navegación, contadores y pantallas montadas."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline


@pytest.fixture()
def ventana(aplicacion):
    """Una ventana entera, con un motor que no toca la red.

    Se construye de verdad —las seis pantallas— porque lo que se prueba aquí
    es precisamente el cableado entre ellas y el carril.
    """
    from PySide6.QtCore import QObject, Signal

    class MotorFalso(QObject):
        caido = Signal(str)

        def __init__(self) -> None:
            super().__init__()
            self.base = "http://127.0.0.1:0"

        def get(self, ruta, bien=None, mal=None) -> None:
            pass

        def post(self, ruta, cuerpo=None, bien=None, mal=None) -> None:
            pass

        def borrar(self, ruta, cuerpo=None, bien=None, mal=None) -> None:
            pass

        def subir(self, ruta, fichero, bien=None, mal=None, avance=None) -> None:
            pass

    from lightrag.api.bimnemo.nativo.ventana import Ventana

    return Ventana(MotorFalso(), "1.4.0")


def test_las_seis_pantallas_estan_montadas(ventana):
    """Ningún `Hueco`: si queda uno, alguien rompió el registro."""
    from lightrag.api.bimnemo.nativo.ventana import PANTALLAS

    montadas = [
        type(ventana.contenido.widget(i)).__name__ for i in range(len(PANTALLAS))
    ]
    assert montadas == [
        "PantallaPanel",
        "PantallaArchivos",
        "PantallaChat",
        "PantallaConfiguracion",
        "PantallaMotor",
        "PantallaApi",
    ]


def test_archivos_empieza_con_una_raya_y_no_con_un_cero(ventana):
    """Un cero mientras carga se lee como «esta memoria está vacía»."""
    assert ventana._cuentas["Archivos"].text() == "—"


def test_el_carril_cuenta_los_archivos_de_la_memoria(ventana):
    """Es el contador que la web enseña junto a «Archivos»."""
    archivos = ventana.contenido.widget(1)
    archivos._recibir({"files": [{"name": f"{i}.pdf"} for i in range(1234)]})
    assert ventana._cuentas["Archivos"].text() == "1.234"


def test_las_demas_entradas_no_llevan_contador(ventana):
    """Un número junto a «Motor» no significaría nada."""
    con_numero = [n for n, e in ventana._cuentas.items() if e.text()]
    assert con_numero == ["Archivos"]


def test_el_contador_no_se_come_el_clic(ventana):
    """La etiqueta va DENTRO del botón, y el ratón la atraviesa.

    Sin `WA_TransparentForMouseEvents`, la etiqueta es quien está debajo del
    puntero en esa esquina y el botón deja de encenderse y de responder ahí.
    `childAt` contesta a esa misma pregunta: qué hijo intercepta el punto.
    """
    from PySide6.QtCore import QPoint

    boton = ventana._botones[1]
    boton.resize(200, 34)
    donde = QPoint(boton.width() - 20, boton.height() // 2)
    assert boton.childAt(donde) is None


def test_pulsar_sobre_el_contador_sigue_cambiando_de_pantalla(ventana):
    """Y el clic en esa esquina lleva a Archivos, que es lo que se espera."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    ventana.contenido.setCurrentIndex(0)
    boton = ventana._botones[1]
    # Donde está el contador: pegado al borde derecho del botón.
    donde = QPointF(boton.width() - 20, boton.height() / 2)
    for tipo in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        QApplication.sendEvent(
            boton,
            QMouseEvent(
                tipo,
                donde,
                boton.mapToGlobal(donde),
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier,
            ),
        )

    assert ventana.contenido.currentIndex() == 1
