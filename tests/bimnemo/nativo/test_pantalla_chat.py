"""El chat pregunta a la memoria que tienes abierta, no a todas.

El selector «Buscar en» nace con «Todas las memorias» —es lo primero de la
lista— y nadie le decía cuál estaba abierta arriba. Con tres memorias, el
usuario preguntaba con «Normativas_BIM» seleccionada y recibía una respuesta
que mezclaba las tres, **y tardaba el triple**: preguntar a todas son tres
recuperaciones con su extracción de palabras clave, y las llamadas a Claude
Code van de una en una.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.offline

NEMOS: dict[str, Any] = {
    "nemos": [
        {"id": "", "name": "General", "protected": True},
        {"id": "Normativas_BIM", "name": "Normativas_BIM"},
        {"id": "Desarrollo_CDE", "name": "Desarrollo CDE"},
    ],
    "default": "",
}


class MotorFalso:
    def __init__(self, memoria: str = "") -> None:
        self.base = "http://127.0.0.1:0"
        self.memoria = memoria
        self.pedidos: list[tuple[str, str]] = []

    def get(self, ruta, bien=None, mal=None):
        self.pedidos.append(("GET", ruta))
        if "/bimnemo/nemos" in ruta and bien:
            bien(dict(NEMOS))

    def post(self, ruta, cuerpo=None, bien=None, mal=None, espera_ms=None):
        self.pedidos.append(("POST", ruta))

    def borrar(self, ruta, cuerpo=None, bien=None, mal=None):
        self.pedidos.append(("DELETE", ruta))


def _chat(aplicacion, memoria: str = "Normativas_BIM"):
    from lightrag.api.bimnemo.nativo.pantalla_chat import PantallaChat

    return PantallaChat(MotorFalso(memoria))


# --- a qué memoria se pregunta ---------------------------------------------


def test_al_abrir_se_pregunta_a_la_memoria_abierta(aplicacion):
    """Lo que contesta a «¿en qué estoy trabajando?»."""
    chat = _chat(aplicacion, "Normativas_BIM")

    assert chat.barra.nemo == "Normativas_BIM"
    assert not chat.barra.en_todas


def test_la_memoria_heredada_tambien_se_elige_sola(aplicacion):
    """Su identificador es la cadena vacía y no puede confundirse con «todas»."""
    chat = _chat(aplicacion, "")

    assert not chat.barra.en_todas
    assert chat.barra.nemo == ""


def test_cambiar_de_memoria_arriba_lo_sigue_el_chat(aplicacion):
    chat = _chat(aplicacion, "Normativas_BIM")

    chat.motor.memoria = "Desarrollo_CDE"
    chat.poner_memoria("Desarrollo CDE")

    assert chat.barra.nemo == "Desarrollo_CDE"


def test_preguntar_a_una_memoria_va_por_su_ruta_y_no_por_la_de_todas(aplicacion):
    chat = _chat(aplicacion, "Normativas_BIM")
    chat.compositor.entrada.setPlainText("¿qué dice la norma?")
    chat.preguntar()

    rutas = [r for v, r in chat.motor.pedidos if v == "POST"]
    assert rutas == ["/nemo/Normativas_BIM/query"]
    assert not any("ask-all" in r for r in rutas), "eso costaba el triple"


# --- «Todas» sigue estando, pero se elige a propósito -----------------------


def test_elegir_todas_a_mano_se_respeta(aplicacion):
    from lightrag.api.bimnemo.nativo.chat_piezas import TODAS

    chat = _chat(aplicacion, "Normativas_BIM")
    chat.barra.memoria.setCurrentIndex(chat.barra.memoria.findData(TODAS))
    chat.compositor.entrada.setPlainText("¿y esto?")
    chat.preguntar()

    assert ("POST", "/bimnemo/memory/ask-all") in chat.motor.pedidos


def test_recargar_la_lista_no_pisa_lo_que_se_eligio(aplicacion):
    """Solo la primera carga propone; después manda la persona."""
    from lightrag.api.bimnemo.nativo.chat_piezas import TODAS

    chat = _chat(aplicacion, "Normativas_BIM")
    chat.barra.memoria.setCurrentIndex(chat.barra.memoria.findData(TODAS))

    chat._poner_memorias(dict(NEMOS))

    assert chat.barra.en_todas
