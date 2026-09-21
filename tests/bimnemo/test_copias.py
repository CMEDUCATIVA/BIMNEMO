"""Una copia repetida se explica en castellano, y no cuenta como fallo."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace as Doc

import pytest

pytestmark = pytest.mark.offline

RECHAZO = (
    "Identical content already exists under another filename. "
    "Original doc_id: doc-38d3aa45b0c10efdb7e75cbef601fe95, "
    "Status: DocStatus.PROCESSING"
)


def _docs():
    from lightrag.base import DocStatus

    return {
        "doc-38d3aa45b0c10efdb7e75cbef601fe95": Doc(
            file_path="OIR FB.txt", status=DocStatus.PROCESSED, error_msg=None,
            chunks_count=1, content_length=1304,
        ),
        "doc-94534dd2dc6d3c900dbcf116885ad93e": Doc(
            file_path="Error OIR.txt", status=DocStatus.FAILED, error_msg=RECHAZO,
            chunks_count=0, content_length=1304,
        ),
    }


def test_reconoce_la_copia_y_dice_de_que_archivo_es():
    from lightrag.api.bimnemo.stats import explicar_copia, original_de_copia

    original = original_de_copia(RECHAZO, _docs())
    assert original == "OIR FB.txt"

    texto = explicar_copia("Error OIR.txt", original)
    assert "«OIR FB.txt»" in texto and "«Error OIR.txt»" in texto
    assert "No falta nada" in texto and "borrar" in texto
    assert "doc-" not in texto, "el identificador interno no le dice nada a nadie"


def test_un_fallo_de_verdad_no_se_toma_por_copia():
    from lightrag.api.bimnemo.stats import original_de_copia

    assert original_de_copia("Error code: 401 - invalid api key", _docs()) is None


def test_si_el_original_ya_no_esta_sigue_siendo_una_copia():
    from lightrag.api.bimnemo.stats import explicar_copia, original_de_copia

    original = original_de_copia(RECHAZO, {})
    assert original == ""
    assert "otro archivo" in explicar_copia("Error OIR.txt", original)


class _Rag:
    def __init__(self, docs):
        self.doc_status = self
        self._docs = docs

    async def get_docs_by_statuses(self, statuses, strict=False):
        return self._docs


def test_en_el_panel_la_copia_es_un_aviso_y_no_un_error():
    from lightrag.api.bimnemo.stats import summarize_memory

    memoria = asyncio.run(summarize_memory(_Rag(_docs())))
    assert memoria["failed_kind"] == "duplicate"
    assert "«OIR FB.txt»" in memoria["failed_reason"]


def test_un_fallo_de_verdad_gana_a_la_copia():
    """Si además hay un fallo real, es lo que hay que ver primero."""
    from lightrag.base import DocStatus
    from lightrag.api.bimnemo.stats import summarize_memory

    docs = _docs()
    docs["doc-roto"] = Doc(
        file_path="roto.pdf", status=DocStatus.FAILED,
        error_msg="Error code: 401 - {'error': {'message': 'Incorrect API key'}}",
        chunks_count=0, content_length=0,
    )
    memoria = asyncio.run(summarize_memory(_Rag(docs)))
    assert memoria["failed_kind"] == "error"
    assert "clave de API" in memoria["failed_reason"]
