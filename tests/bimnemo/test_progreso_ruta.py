"""`GET /bimnemo/progress` cuenta lo de **esta** memoria, documento a documento.

El endpoint es fino a propósito —los cálculos están en ``bimnemo/avance.py``
y se prueban aparte—, pero el cableado no: qué documentos cuentan como «en
marcha», que el avance de cada uno llegue a su fila y que un `doc_status`
ilegible informe en vez de tumbar el panel.
"""

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

from lightrag import doc_progress  # noqa: E402
from lightrag.api.routers.bimnemo_progreso_routes import (  # noqa: E402
    create_bimnemo_progreso_routes,
)
from lightrag.base import DocStatus  # noqa: E402

pytestmark = pytest.mark.offline


class _Registro:
    def __init__(self, estado: DocStatus) -> None:
        self.status = estado


class _DocStatus:
    def __init__(self, documentos: dict[str, DocStatus]) -> None:
        self._documentos = documentos

    async def get_docs_by_statuses(self, _estados, strict: bool = True):
        return {k: _Registro(v) for k, v in self._documentos.items()}


class _DocStatusRoto(_DocStatus):
    async def get_docs_by_statuses(self, _estados, strict: bool = True):
        raise RuntimeError("el almacén no contesta")


class _Rag:
    def __init__(self, workspace: str, doc_status) -> None:
        self.workspace = workspace
        self.doc_status = doc_status


async def _tuberia(workspace: str):
    shared = importlib.import_module("lightrag.kg.shared_storage")
    shared.initialize_share_data()
    await shared.initialize_pipeline_status(workspace=workspace)
    return await shared.get_namespace_data("pipeline_status", workspace=workspace)


def _preguntar(workspace: str, doc_status, entrada: Path):
    async def resolver(_nemo):
        return _Rag(workspace, doc_status), entrada, None

    router = create_bimnemo_progreso_routes(resolver, None)
    ruta = next(r for r in router.routes if r.path == "/progress")
    return ruta.endpoint(nemo="obra")


async def test_cada_documento_en_marcha_trae_su_avance(tmp_path):
    workspace = f"avance-{uuid4().hex[:8]}"
    estado = await _tuberia(workspace)
    estado["busy"] = True
    doc_progress.publish(estado, "doc-1", doc_progress.EXTRACT, 3, 7)
    doc_progress.publish(estado, "doc-2", doc_progress.ANALYZE, 2, 8)

    respuesta = await _preguntar(
        workspace,
        _DocStatus(
            {
                "doc-1": DocStatus.PROCESSING,
                "doc-2": DocStatus.ANALYZING,
                "doc-3": DocStatus.PROCESSED,
            }
        ),
        tmp_path,
    )

    porciento = {f["doc_id"]: f["percent"] for f in respuesta.docs}
    assert set(porciento) == {"doc-1", "doc-2"}, "el terminado no lleva barra"
    assert porciento["doc-1"] != porciento["doc-2"], "cada uno el suyo"
    assert respuesta.working == 2 and respuesta.done == 1


async def test_el_borrado_tambien_se_ve(tmp_path):
    """Purgar tarda segundos y el documento ya no consta como «en marcha»."""
    workspace = f"avance-{uuid4().hex[:8]}"
    estado = await _tuberia(workspace)
    doc_progress.publish(estado, "doc-1", doc_progress.DELETE, 30, 120)

    respuesta = await _preguntar(
        workspace, _DocStatus({"doc-1": DocStatus.PROCESSED}), tmp_path
    )

    assert [(f["doc_id"], f["percent"]) for f in respuesta.docs] == [("doc-1", 25)]


async def test_un_almacen_ilegible_informa_en_vez_de_tumbar_el_panel(tmp_path):
    workspace = f"avance-{uuid4().hex[:8]}"
    await _tuberia(workspace)

    respuesta = await _preguntar(workspace, _DocStatusRoto({}), tmp_path)

    assert respuesta.total == 0 and respuesta.percent == 0


async def test_el_sello_cambia_cuando_cambia_lo_que_se_enseña(tmp_path):
    """La vista lo compara para saber si volver a pedir la lista entera."""
    workspace = f"avance-{uuid4().hex[:8]}"
    await _tuberia(workspace)
    docs = _DocStatus({"doc-1": DocStatus.PROCESSED})

    antes = (await _preguntar(workspace, docs, tmp_path)).revision
    (tmp_path / "nuevo.docx").write_bytes(b"x")
    despues = (await _preguntar(workspace, docs, tmp_path)).revision

    assert antes != despues
