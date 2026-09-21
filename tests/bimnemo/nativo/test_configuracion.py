"""Configuración IA: el idioma como selector y las tarjetas en dos columnas."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline


@pytest.fixture()
def configuracion(ventana):
    """La pantalla de configuración, **delante**.

    Delante y no solo construida: una página del apilado que no se está
    viendo no recibe los cambios de tamaño hasta que se enseña, así que
    medir su disposición detrás de otra mediría la de hace un rato.
    """
    indice = next(
        i
        for i in range(ventana.contenido.count())
        if type(ventana.contenido.widget(i)).__name__ == "PantallaConfiguracion"
    )
    ventana.contenido.setCurrentIndex(indice)
    return ventana.contenido.widget(indice)


# --- Idioma -----------------------------------------------------------------


def test_el_idioma_es_una_lista_y_no_un_campo_libre(configuracion):
    """El valor va literal al prompt: una errata estropea una indexación."""
    from PySide6.QtWidgets import QComboBox

    assert isinstance(configuracion.idioma, QComboBox)
    rotulos = [
        configuracion.idioma.itemText(i) for i in range(configuracion.idioma.count())
    ]
    assert rotulos == [
        "Español",
        "Inglés",
        "Portugués",
        "Francés",
        "Alemán",
        "Italiano",
        "Chino",
    ]


def test_se_lee_en_castellano_pero_se_guarda_como_lo_entiende_el_motor(configuracion):
    configuracion._poner_idioma("French")
    assert configuracion.idioma.currentText() == "Francés"
    assert configuracion.idioma.currentData() == "French"


def test_un_idioma_fuera_de_la_lista_no_se_pierde(configuracion):
    """Si alguien lo puso a mano en el `.env`, sigue ahí al guardar.

    Elegir el primero de la lista en su lugar cambiaría el idioma en el
    siguiente «Guardar» sin que nadie lo hubiera pedido.
    """
    configuracion._poner_idioma("Catalan")
    assert configuracion.idioma.currentData() == "Catalan"


def test_guardar_manda_el_idioma_elegido(configuracion, ventana):
    enviado = {}
    ventana.motor.post = lambda ruta, cuerpo=None, bien=None, mal=None: enviado.update(
        cuerpo or {}
    )

    configuracion._poner_idioma("German")
    configuracion._guardar()

    assert enviado.get("language") == "German"


# --- Disposición ------------------------------------------------------------


def _posiciones(configuracion):
    """Fila y columna de cada una de las cuatro tarjetas."""
    return configuracion.rejilla.posiciones()


def _con_ancho(ventana, ancho):
    """Redimensiona la ventana de verdad y deja que Qt reparta."""
    from PySide6.QtWidgets import QApplication

    ventana.resize(ancho, 900)
    ventana.show()
    QApplication.processEvents()


def test_en_ventana_ancha_van_de_dos_en_dos(configuracion, ventana):
    """Una tarjeta a todo lo ancho deja cada valor perdido al otro extremo."""
    # Desde estrecha: arrancar ya en dos columnas no probaría el cambio.
    _con_ancho(ventana, 1000)
    _con_ancho(ventana, 1600)
    posiciones = _posiciones(configuracion)
    ventana.hide()

    assert posiciones == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_en_ventana_estrecha_van_de_una_en_una(configuracion, ventana):
    """Dos tarjetas de cuatrocientos píxeles no dejan leer ni el proveedor."""
    _con_ancho(ventana, 1600)
    _con_ancho(ventana, 1000)
    posiciones = _posiciones(configuracion)
    ventana.hide()

    assert posiciones == [(0, 0), (1, 0), (2, 0), (3, 0)]
