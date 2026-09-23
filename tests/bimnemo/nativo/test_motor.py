"""El cliente del motor apunta a la memoria abierta.

Es lo que hace que cambiar de memoria en la barra cambie los datos de las
seis pantallas sin tocar ninguna: el enrutado vive en un solo sitio.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.offline


@pytest.fixture()
def motor(aplicacion):
    from lightrag.api.bimnemo.nativo.motor import Motor

    return Motor("http://127.0.0.1:9621")


def test_sin_memoria_la_ruta_no_se_toca(motor):
    """Vacío significa «la de por defecto», y esa es la ruta de siempre."""
    assert motor._resolver("/bimnemo/files") == "/bimnemo/files"


def test_con_memoria_se_apunta_con_nemo(motor):
    motor.usar_memoria("obra-sur")
    assert motor._resolver("/bimnemo/files") == "/bimnemo/files?nemo=obra-sur"


def test_una_ruta_que_ya_lleva_parametros_los_conserva(motor):
    """Perder `max_nodes` al añadir la memoria daría otro grafo."""
    motor.usar_memoria("obra-sur")
    resuelta = motor._resolver("/bimnemo/graph?label=*&max_nodes=250")
    assert resuelta == "/bimnemo/graph?label=*&max_nodes=250&nemo=obra-sur"


@pytest.mark.parametrize(
    "ruta, esperada",
    [
        ("/query", "/nemo/obra-sur/query"),
        ("/documents/upload", "/nemo/obra-sur/documents/upload"),
        ("/bimnemo/memory/search", "/nemo/obra-sur/memory/search"),
    ],
)
def test_los_endpoints_con_espejo_usan_su_camino(motor, ruta, esperada):
    """`?nemo=` en estos no da error: lo ignoran y contestan de la otra.

    Ese es justo el fallo que no avisa — la pantalla diría que estás en una
    memoria mientras el motor responde desde la de por defecto.
    """
    motor.usar_memoria("obra-sur")
    assert motor._resolver(ruta) == esperada


def test_el_registro_de_memorias_no_se_apunta_a_ninguna(motor):
    """Listar, crear o borrar memorias se hace desde fuera de todas."""
    motor.usar_memoria("obra-sur")
    assert motor._resolver("/bimnemo/nemos") == "/bimnemo/nemos"


def test_una_ruta_que_ya_nombra_su_memoria_se_respeta(motor):
    """La ha construido quien sabía a cuál apuntaba: renombrar, por ejemplo."""
    motor.usar_memoria("obra-sur")
    assert (
        motor._resolver("/bimnemo/nemos?nemo=proyecto-norte")
        == "/bimnemo/nemos?nemo=proyecto-norte"
    )


def test_un_identificador_raro_va_escapado(motor):
    """Un nombre con espacios partiría la URL en dos."""
    motor.usar_memoria("obra sur/2")
    assert motor._resolver("/bimnemo/files") == "/bimnemo/files?nemo=obra%20sur%2F2"


# -- plazos por petición -------------------------------------------------------


def test_lo_corriente_lleva_el_plazo_corto(aplicacion):
    from lightrag.api.bimnemo.nativo.motor import ESPERA_MS, Motor

    motor = Motor("http://127.0.0.1:0")
    peticion = motor._peticion("/bimnemo/pulso")
    assert peticion.transferTimeout() == ESPERA_MS


def test_se_puede_pedir_un_plazo_largo(aplicacion):
    """Para lo que se sabe que tarda: una respuesta del chat, un login."""
    from lightrag.api.bimnemo.nativo.motor import ESPERA_LARGA_MS, Motor

    motor = Motor("http://127.0.0.1:0")
    peticion = motor._peticion("/query", ESPERA_LARGA_MS)
    assert peticion.transferTimeout() == ESPERA_LARGA_MS
    assert ESPERA_LARGA_MS > 300_000, "el motor le da 300 s a un modelo lento"


def test_el_chat_pide_el_plazo_largo(aplicacion):
    """Con el corto, la ventana se rendía mientras la respuesta venía."""
    from lightrag.api.bimnemo.nativo import pantalla_chat

    fuente = Path(pantalla_chat.__file__).read_text(encoding="utf-8")
    assert "espera_ms=ESPERA_LARGA_MS" in fuente
