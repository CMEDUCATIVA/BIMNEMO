"""`GET /bimnemo/usage` cuenta el gasto de la memoria abierta.

La tabla de «Uso y coste de la IA» enseñaba el gasto de todas las NEMO
juntas. Con varias memorias, la pregunta que se hace quien mira es «cuánto me
cuesta **esta**», y un total de todas no la contesta. «Todas» sigue estando,
porque esa es la cifra que cuadra con la factura del proveedor.
"""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest

# Importar el paquete de routers pasa un argparse sobre sys.argv.
_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
importlib.import_module("lightrag.api.routers.document_routes")
sys.argv = _argv

from lightrag.api.bimnemo import consumo  # noqa: E402
from lightrag.api.routers.bimnemo_usage_routes import (  # noqa: E402
    create_bimnemo_usage_routes,
)

pytestmark = pytest.mark.offline


class _Registro:
    """Un índice de NEMOs con lo justo: resolver, listar y nombrar."""

    def __init__(self) -> None:
        self._nemos = [
            SimpleNamespace(id="", name="General"),
            SimpleNamespace(id="obra-sur", name="Obra Sur"),
        ]

    def resolve(self, pedida):
        for nemo in self._nemos:
            if nemo.id == (pedida or ""):
                return nemo.id
        raise ValueError(f"No existe la NEMO «{pedida}».")

    def list(self):
        return list(self._nemos)

    def get(self, nemo_id):
        return next((n for n in self._nemos if n.id == nemo_id), None)


@pytest.fixture
def gastado(tmp_path, monkeypatch):
    """Gasto en dos memorias y una fila de antes de medirlas."""
    nuevo = consumo._Registro()
    nuevo.iniciar(tmp_path)
    monkeypatch.setattr(consumo, "REGISTRO", nuevo)
    nuevo.anotar("llm", "Indexar", "gpt-5-nano", "", 1000, 500, nemo="obra-sur")
    nuevo.anotar("llm", "Indexar", "gpt-5.6-luna", "", 2000, 900, nemo="")
    nuevo.anotar("llm", "Responder", "gpt-5-mini", "", 10, 5)  # sin memoria
    return nuevo


def _preguntar(**kwargs):
    router = create_bimnemo_usage_routes(None, _Registro())
    ruta = next(r for r in router.routes if r.path == "/usage")
    return ruta.endpoint(**kwargs)


async def test_por_defecto_solo_cuenta_la_memoria_abierta(gastado):
    respuesta = await _preguntar(days=30, nemo="obra-sur", scope="nemo")

    assert [f["modelo"] for f in respuesta.rows] == ["gpt-5-nano"]
    assert respuesta.nemo == "obra-sur" and respuesta.nemo_name == "Obra Sur"
    # Se dice cuánto se está dejando fuera: si no, la tabla parece incompleta
    # sin que nada explique por qué.
    assert respuesta.other_rows == 2


async def test_sin_nemo_cuenta_la_heredada_y_no_todas(gastado):
    """El cliente no manda `nemo` cuando la abierta es la de por defecto."""
    respuesta = await _preguntar(days=30, nemo=None, scope="nemo")

    assert [f["modelo"] for f in respuesta.rows] == ["gpt-5.6-luna"]
    assert respuesta.nemo == "" and respuesta.nemo_name == "General"


async def test_todas_da_la_cuenta_entera(gastado):
    """Es la que cuadra con la factura, y donde sale lo de antes de medir."""
    respuesta = await _preguntar(days=30, nemo="obra-sur", scope="all")

    assert len(respuesta.rows) == 3 and respuesta.other_rows == 0
    assert respuesta.totals["today"]["llamadas"] == 3


async def test_cada_fila_dice_de_que_memoria_es(gastado):
    respuesta = await _preguntar(days=30, nemo="", scope="all")

    por_modelo = {f["modelo"]: f.get("nemo_name") for f in respuesta.rows}
    assert por_modelo["gpt-5-nano"] == "Obra Sur"
    assert por_modelo["gpt-5.6-luna"] == "General"
    # La de antes de medir no es de ninguna: no se le pone nombre.
    assert por_modelo["gpt-5-mini"] == ""


async def test_los_totales_cuadran_con_las_filas_que_se_ven(gastado):
    """Un total de todas junto a las filas de una es lo que no se entiende."""
    respuesta = await _preguntar(days=30, nemo="obra-sur", scope="nemo")

    assert respuesta.totals["today"]["entrada"] == 1000
    assert respuesta.totals["today"]["salida"] == 500


async def test_una_memoria_que_no_existe_se_dice(gastado):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as fallo:
        await _preguntar(days=30, nemo="inventada", scope="nemo")
    assert fallo.value.status_code == 404
