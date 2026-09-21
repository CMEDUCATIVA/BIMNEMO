"""La pantalla Motor: sus siete tarjetas, de dos en dos."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline


@pytest.fixture()
def pantalla(ventana):
    """La pantalla del Motor, delante: detrás no recibiría los cambios de tamaño."""
    indice = next(
        i
        for i in range(ventana.contenido.count())
        if type(ventana.contenido.widget(i)).__name__ == "PantallaMotor"
    )
    ventana.contenido.setCurrentIndex(indice)
    return ventana.contenido.widget(indice)


def _con_ancho(ventana, ancho):
    from PySide6.QtWidgets import QApplication

    ventana.resize(ancho, 900)
    ventana.show()
    QApplication.processEvents()


def test_las_siete_tarjetas_van_de_dos_en_dos(pantalla, ventana):
    """A todo lo ancho, cada dato quedaba a mil píxeles de su nombre."""
    _con_ancho(ventana, 1000)
    _con_ancho(ventana, 1600)
    posiciones = pantalla.rejilla.posiciones()
    ventana.hide()

    assert posiciones == [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1), (3, 0)]


def test_en_ventana_estrecha_van_de_una_en_una(pantalla, ventana):
    _con_ancho(ventana, 1600)
    _con_ancho(ventana, 1000)
    posiciones = pantalla.rejilla.posiciones()
    ventana.hide()

    assert posiciones == [(fila, 0) for fila in range(7)]


def test_el_reinicio_queda_fuera_de_la_rejilla(pantalla):
    """Es del motor entero, no de una tarjeta: va debajo y a todo lo ancho."""
    assert len(pantalla.rejilla.tarjetas) == 7
