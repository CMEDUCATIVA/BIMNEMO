"""Pausar la indexación de una memoria cualquiera, no solo la de por defecto."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from uuid import uuid4

import pytest

# Importar document_routes pasa un argparse sobre sys.argv.
_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
importlib.import_module("lightrag.api.routers.document_routes")
sys.argv = _argv

from lightrag.api.bimnemo import stats  # noqa: E402
from lightrag.api.routers.bimnemo_documents_routes import (  # noqa: E402
    create_bimnemo_documents_routes,
)

pytestmark = pytest.mark.offline


class _Rag:
    def __init__(self, workspace: str) -> None:
        self.workspace = workspace


def _pausar(workspace: str):
    async def resolver(_nemo):
        return _Rag(workspace), Path("."), None

    router = create_bimnemo_documents_routes(None, resolver, None)
    ruta = next(r for r in router.routes if r.path == "/documents/pause")
    return ruta.endpoint(nemo="obra")


async def _tuberia(workspace: str):
    shared = importlib.import_module("lightrag.kg.shared_storage")
    shared.initialize_share_data()
    await shared.initialize_pipeline_status(workspace=workspace)
    return await shared.get_namespace_data("pipeline_status", workspace=workspace)


async def test_pausa_la_memoria_pedida_y_no_la_de_por_defecto():
    workspace = f"pausa-{uuid4().hex[:8]}"
    estado = await _tuberia(workspace)
    estado["busy"] = True

    respuesta = await _pausar(workspace)

    assert respuesta.status == "pausing"
    assert estado["cancellation_requested"] is True


async def test_sin_nada_en_marcha_no_hace_nada():
    workspace = f"pausa-{uuid4().hex[:8]}"
    estado = await _tuberia(workspace)
    estado["busy"] = False

    respuesta = await _pausar(workspace)

    assert respuesta.status == "not_busy"
    assert not estado.get("cancellation_requested")


# --- cómo se enseña lo pausado -----------------------------------------------


@pytest.mark.parametrize(
    "mensaje",
    ["User cancelled", "User cancelled during entity extraction", "user cancelled during merge"],
)
def test_una_cancelacion_pedida_es_una_pausa(mensaje):
    assert stats.pausado(mensaje)
    assert stats._clean_reason(mensaje).startswith("En pausa")


def test_una_cancelacion_por_error_interno_no_es_una_pausa():
    assert not stats.pausado("Cancelled by internal error: disk full during merge")
    assert not stats.pausado(None)
