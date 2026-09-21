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


# -- el selector de modelo --------------------------------------------------

CATALOGO_LLM = [
    {"key": "openai", "label": "OpenAI", "binding": "openai",
     "host": "https://api.openai.com/v1", "models": ["gpt-5.4-mini", "gpt-5.4"]},
    {"key": "gemini", "label": "Gemini", "binding": "gemini",
     "host": "https://generativelanguage.googleapis.com", "models": ["gemini-2.5-flash"]},
    {"key": "localai", "label": "LocalAI", "binding": "openai",
     "host": "http://localhost:8080/v1", "models": []},
]


def _seccion():
    from lightrag.api.bimnemo.nativo.pantalla_configuracion import Seccion

    seccion = Seccion("llm", "Modelo de lenguaje", "")
    seccion.poner_catalogo(CATALOGO_LLM)
    return seccion


def test_el_modelo_es_un_selector_y_no_se_escribe(aplicacion):
    seccion = _seccion()
    seccion.poner_valores({"provider": "openai", "model": "gpt-5.4"})

    assert seccion.modelo.isEditable() is False
    assert seccion.modelo_actual() == "gpt-5.4"
    textos = [seccion.modelo.itemText(i) for i in range(seccion.modelo.count())]
    assert textos[-1] == "Otro modelo…"


def test_un_modelo_guardado_que_no_esta_en_la_lista_no_se_pierde(aplicacion):
    """Cambiarlo por otro lo cambiaría en el siguiente «Guardar»."""
    seccion = _seccion()
    seccion.poner_valores({"provider": "openai", "model": "gpt-5.6-luna"})

    assert seccion.modelo_actual() == "gpt-5.6-luna"
    assert seccion.a_peticion()["model"] == "gpt-5.6-luna"


def test_otro_modelo_pregunta_el_nombre_y_lo_deja_elegido(aplicacion, monkeypatch):
    from lightrag.api.bimnemo.nativo import pantalla_configuracion as modulo

    seccion = _seccion()
    seccion.poner_valores({"provider": "localai", "model": ""})
    monkeypatch.setattr(
        modulo.QInputDialog, "getText", lambda *a, **k: ("mi-modelo:7b", True)
    )
    seccion._modelo_elegido(seccion.modelo.findData(modulo.OTRO_MODELO))

    assert seccion.modelo_actual() == "mi-modelo:7b"


def test_cancelar_otro_modelo_deja_el_que_habia(aplicacion, monkeypatch):
    from lightrag.api.bimnemo.nativo import pantalla_configuracion as modulo

    seccion = _seccion()
    seccion.poner_valores({"provider": "openai", "model": "gpt-5.4"})
    monkeypatch.setattr(modulo.QInputDialog, "getText", lambda *a, **k: ("", False))
    seccion._modelo_elegido(seccion.modelo.findData(modulo.OTRO_MODELO))

    assert seccion.modelo_actual() == "gpt-5.4"


def test_sin_modelo_se_queda_en_blanco_y_no_elige_el_primero(aplicacion):
    """El reordenado se puede dejar en blanco: no se rellena por su cuenta."""
    seccion = _seccion()
    seccion.poner_valores({"provider": "openai", "model": ""})

    assert seccion.modelo_actual() == ""
    assert seccion.a_peticion()["model"] == ""


def test_al_cambiar_de_proveedor_no_arrastra_el_modelo_anterior(aplicacion):
    seccion = _seccion()
    seccion.poner_valores({"provider": "openai", "model": "gpt-5.4"})
    seccion.proveedor.setCurrentIndex(seccion.proveedor.findData("gemini"))

    textos = [seccion.modelo.itemText(i) for i in range(seccion.modelo.count())]
    assert seccion.modelo_actual() == "gemini-2.5-flash"
    assert "gpt-5.4" not in textos


def test_el_idioma_de_una_instalacion_nueva_es_el_espanol():
    """El `.env` de una instalación nueva sale de `env.example`."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[3]
    lineas = (raiz / "env.example").read_text(encoding="utf-8").splitlines()
    assert "SUMMARY_LANGUAGE=Spanish" in lineas
