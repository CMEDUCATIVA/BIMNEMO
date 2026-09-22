"""Mover la barra de razonamiento se aplica sin reiniciar, también indexando."""

from __future__ import annotations

import json
import os

import numpy as np
import pytest

from lightrag import ROLES, LightRAG, RoleLLMConfig
from lightrag.api.bimnemo import razonamiento
from lightrag.utils import EmbeddingFunc, Tokenizer

pytestmark = pytest.mark.offline


class _Tokenizador:
    def encode(self, texto):
        return [ord(c) for c in texto]

    def decode(self, fichas):
        return "".join(chr(f) for f in fichas)


async def _embeddings(textos):
    return np.random.rand(len(textos), 16)


async def _llm(*args, **kwargs):
    return "ok"


def _rag(tmp_path, construidos):
    """Un LightRAG de verdad, con el constructor de roles registrado como en el servidor."""
    rag = LightRAG(
        working_dir=str(tmp_path / "rag"),
        workspace="caliente",
        llm_model_func=_llm,
        embedding_func=EmbeddingFunc(
            embedding_dim=16, max_token_size=4096, func=_embeddings
        ),
        tokenizer=Tokenizer("t", _Tokenizador()),
        role_llm_configs={
            spec.name: RoleLLMConfig(
                func=_llm,
                metadata={
                    "binding": "openai",
                    "base_binding": "openai",
                    "model": "deepseek-flash",
                    "host": "https://api.deepseek.com/v1",
                    "provider_options": {"temperature": 0.2},
                },
            )
            for spec in ROLES
        },
    )

    def constructor(rol, meta):
        construidos.append((rol, dict(meta.get("provider_options") or {})))
        return _llm, {}

    rag.register_role_llm_builder(constructor)
    return rag


async def test_apagar_al_extraer_reconstruye_solo_extraer_y_palabras_clave(
    tmp_path, monkeypatch
):
    construidos: list = []
    rag = _rag(tmp_path, construidos)
    for clave in razonamiento.GESTIONADAS:
        monkeypatch.delenv(clave, raising=False)

    cambios = razonamiento.a_variables(
        "deepseek", "deepseek-flash", {"indexar": "off", "responder": ""}
    )
    hechos = razonamiento.aplicar_en_caliente([rag], cambios)
    await rag.wait_for_retired_llm_queues()

    por_rol = {rol: opciones for rol, opciones in construidos}
    apagado = {"thinking": {"type": "disabled"}}
    assert por_rol["extract"]["extra_body"] == apagado
    assert por_rol["keyword"]["extra_body"] == apagado
    # Lo que ya tenía el rol se conserva.
    assert por_rol["extract"]["temperature"] == 0.2
    # Responder va en «lo que decida el modelo»: sin extra_body.
    assert "extra_body" not in por_rol.get("query", {})
    assert set(hechos) == {"extract", "keyword", "query"}

    # Una memoria que se abra después lee el entorno: ya lleva el nivel nuevo.
    assert json.loads(os.environ["EXTRACT_OPENAI_LLM_EXTRA_BODY"]) == apagado
    assert "QUERY_OPENAI_LLM_EXTRA_BODY" not in os.environ


async def test_volver_a_por_defecto_quita_lo_que_habia(tmp_path, monkeypatch):
    construidos: list = []
    rag = _rag(tmp_path, construidos)
    monkeypatch.setenv("EXTRACT_OPENAI_LLM_EXTRA_BODY", '{"x":1}')

    razonamiento.aplicar_en_caliente(
        [rag], razonamiento.a_variables("deepseek", "deepseek-flash", {"indexar": ""})
    )
    await rag.wait_for_retired_llm_queues()

    extraer = [o for r, o in construidos if r == "extract"][-1]
    assert "extra_body" not in extraer
    assert "EXTRACT_OPENAI_LLM_EXTRA_BODY" not in os.environ


def test_cada_memoria_abierta_una_sola_vez():
    import importlib
    import sys
    from types import SimpleNamespace

    # Importar las rutas pasa un argparse sobre sys.argv.
    argv = sys.argv[:]
    sys.argv = [sys.argv[0]]
    importlib.import_module("lightrag.api.routers.document_routes")
    sys.argv = argv
    from lightrag.api.routers.bimnemo_settings_routes import _instancias_vivas

    defecto, obra = object(), object()
    gestor = SimpleNamespace(
        live_ids=lambda: ["", "obra"],
        peek=lambda i: {"": defecto, "obra": obra}[i],
    )
    assert _instancias_vivas(defecto, gestor) == [defecto, obra]
    assert _instancias_vivas(defecto, None) == [defecto]
