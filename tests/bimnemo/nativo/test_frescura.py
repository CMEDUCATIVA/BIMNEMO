"""El Panel se entera solo de lo que se sube en Archivos."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline


class Motor:
    def __init__(self) -> None:
        self.progreso = {"revision": "r1", "busy": False}
        self.pedidos: list[str] = []

    def get(self, ruta, bien=None, mal=None):
        self.pedidos.append(ruta)
        if ruta == "/bimnemo/progress" and bien:
            bien(dict(self.progreso))


_abiertas: list = []


@pytest.fixture(autouse=True)
def cerrar_lo_abierto():
    """Cada prueba cierra lo que abre.

    Sin esto, la pantalla de prueba seguía viva en Qt con su filtro puesto
    después de que Python la soltara, y le saltaba a la prueba siguiente.
    """
    yield
    from PySide6.QtWidgets import QApplication

    while _abiertas:
        pantalla, frescura = _abiertas.pop()
        pantalla.removeEventFilter(frescura)
        pantalla.close()
        pantalla.deleteLater()
    QApplication.processEvents()


def _vigilada(aplicacion):
    from PySide6.QtWidgets import QWidget

    from lightrag.api.bimnemo.nativo.frescura import Frescura

    pantalla = QWidget()
    motor = Motor()
    frescura = Frescura(motor, pantalla)
    _abiertas.append((pantalla, frescura))
    avisos: list[bool] = []
    frescura.cambiaron.connect(avisos.append)
    frescura.mirar()  # la primera lectura es la base
    return pantalla, motor, frescura, avisos


def test_sin_cambios_no_avisa(aplicacion):
    _p, _m, frescura, avisos = _vigilada(aplicacion)
    frescura.mirar()
    assert avisos == []


def test_indexando_con_la_pantalla_a_la_vista_solo_las_cifras(aplicacion):
    """El grafo no se redibuja con cada documento mientras se mira."""
    _p, motor, frescura, avisos = _vigilada(aplicacion)
    motor.progreso = {"revision": "r2", "busy": True}
    frescura.mirar()
    assert avisos == [False]


def test_cuando_el_motor_termina_se_recarga_el_grafo(aplicacion):
    """Aunque el sello ya no cambie: el último cambio llegó con el motor ocupado."""
    _p, motor, frescura, avisos = _vigilada(aplicacion)
    motor.progreso = {"revision": "r2", "busy": True}
    frescura.mirar()
    motor.progreso = {"revision": "r2", "busy": False}
    frescura.mirar()
    assert avisos == [False, True]


def test_al_volver_a_la_pantalla_se_recarga_todo(aplicacion):
    """El caso de siempre: subir en Archivos y volver al Panel."""
    pantalla, motor, _f, avisos = _vigilada(aplicacion)
    motor.progreso = {"revision": "r2", "busy": True}  # aún indexando
    pantalla.show()
    assert avisos == [True]


def test_una_pantalla_que_nadie_mira_no_pregunta(aplicacion):
    pantalla, motor, frescura, _a = _vigilada(aplicacion)
    pantalla.hide()
    motor.pedidos.clear()
    frescura._sondear()
    assert motor.pedidos == []


def test_el_panel_recarga_el_grafo_o_solo_las_cifras(ventana):
    panel = ventana.contenido.widget(0)
    ventana.motor.pedidos.clear()
    panel._datos_nuevos(False)
    assert not any(r.startswith("/bimnemo/graph") for r in ventana.motor.pedidos)
    assert "/bimnemo/stats" in ventana.motor.pedidos

    ventana.motor.pedidos.clear()
    panel._datos_nuevos(True)
    assert any(r.startswith("/bimnemo/graph") for r in ventana.motor.pedidos)
