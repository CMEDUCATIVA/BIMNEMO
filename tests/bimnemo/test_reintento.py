"""Reintentar un documento toca ese documento y ningún otro."""

from __future__ import annotations

import asyncio
import importlib
import sys
from types import SimpleNamespace

import pytest

from lightrag.api.bimnemo import reintento
from lightrag.base import DocStatus

# Importar document_routes pasa un argparse sobre sys.argv; con los argumentos
# de pytest delante revienta. Igual que tests/parser/test_hint_params.py.
_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
importlib.import_module("lightrag.api.routers.document_routes")
sys.argv = _argv


class _DocStatus:
    def __init__(self, registros):
        self.registros = registros
        self.escritos: dict = {}

    async def get_full_docs_by_ids(self, ids, *, strict=False):
        return {i: self.registros[i] for i in ids if i in self.registros}

    async def upsert(self, datos):
        self.escritos.update(datos)


class _FullDocs:
    def __init__(self, contenidos):
        self.contenidos = contenidos

    async def get_by_id(self, doc_id):
        return self.contenidos.get(doc_id)


class _Rag:
    def __init__(self, registros, contenidos):
        self.doc_status = _DocStatus(registros)
        self.full_docs = _FullDocs(contenidos)
        self.indexados = 0

    def _build_pending_reset_update(self, registro, contenido):
        return {"status": DocStatus.PENDING, "error_msg": ""}, "", {}

    async def apipeline_process_enqueue_documents(self):
        self.indexados += 1


def _registro(status):
    return SimpleNamespace(status=status, metadata={})


@pytest.fixture
def reserva(monkeypatch):
    """La reserva de la tubería, sin tubería de verdad."""
    import lightrag.api.routers.document_routes as rutas

    estado = {"libre": True, "soltadas": 0}

    async def adquirir(rag, token, *, kind, operation_record):
        return estado["libre"], None if estado["libre"] else "busy"

    async def soltar(rag, token):
        estado["soltadas"] += 1

    monkeypatch.setattr(rutas, "_acquire_destructive_busy", adquirir)
    monkeypatch.setattr(rutas, "_release_destructive_busy", soltar)
    return estado


def _correr(rag, doc_id):
    async def _todo():
        tareas: set = set()
        respuesta = await reintento.reintentar_uno(rag, doc_id, tareas)
        await asyncio.gather(*tareas)
        return respuesta

    return asyncio.run(_todo())


def test_solo_pasa_a_pendiente_el_documento_elegido(reserva):
    rag = _Rag(
        {"doc-a": _registro(DocStatus.FAILED), "doc-b": _registro(DocStatus.FAILED)},
        {"doc-a": {"content": "x"}, "doc-b": {"content": "y"}},
    )
    respuesta = _correr(rag, "doc-a")

    assert respuesta["status"] == "queued"
    assert list(rag.doc_status.escritos) == ["doc-a"]
    assert rag.indexados == 1
    assert reserva["soltadas"] == 1


def test_con_la_memoria_ocupada_no_toca_nada(reserva):
    reserva["libre"] = False
    rag = _Rag({"doc-a": _registro(DocStatus.FAILED)}, {"doc-a": {"content": "x"}})
    respuesta = _correr(rag, "doc-a")

    assert respuesta["status"] == "busy"
    assert rag.doc_status.escritos == {}
    assert rag.indexados == 0


def test_un_documento_que_no_esta_fallido_no_se_reintenta(reserva):
    rag = _Rag({"doc-a": _registro(DocStatus.PROCESSED)}, {"doc-a": {"content": "x"}})
    respuesta = _correr(rag, "doc-a")

    assert respuesta["status"] == "nothing"
    assert rag.doc_status.escritos == {}
    assert reserva["soltadas"] == 1


def test_sin_contenido_pide_volver_a_subirlo(reserva):
    rag = _Rag({"doc-a": _registro(DocStatus.FAILED)}, {})
    respuesta = _correr(rag, "doc-a")

    assert respuesta["status"] == "nothing"
    assert "vuelve a subirlo" in respuesta["message"]
    assert rag.doc_status.escritos == {}
