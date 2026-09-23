"""El chat responde con el modelo elegido, también preguntando a todas.

`/bimnemo/memory/ask-all` —el chat con «Todas las memorias»— redactaba la
respuesta con ``llm_model_func``, la función base de LightRAG. Esa función no
lleva la configuración de ningún rol: con OpenAI colaba, porque el modelo va
escrito dentro de la que monta el servidor, pero los conectores que lo leen
de ``hashing_kv`` —Claude, Ollama, LoLLMs— lo recibían **vacío** y respondían
con su modelo por defecto.

Se notó cuando la tabla de uso y coste empezó a medir: salían llamadas de
«Palabras clave» —esas sí van por su rol— y ninguna de «Responder».
"""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from typing import Any

import pytest

# Importar el paquete de routers pasa un argparse sobre sys.argv.
_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
importlib.import_module("lightrag.api.routers.document_routes")
sys.argv = _argv

from lightrag.api.routers.nemo_query_routes import (  # noqa: E402
    MultiSearchRequest,
    create_nemo_query_routes,
)

pytestmark = pytest.mark.offline


class _Rag:
    """Una memoria con rol `query` y función base, para ver cuál se usa."""

    def __init__(self) -> None:
        self.workspace = ""
        self.usados: list[str] = []

    async def llm_model_func(self, prompt, system_prompt=None, **kwargs) -> str:
        self.usados.append("base")
        return "la escribió la función base"

    def llm_role_func(self, role: str = "query"):
        async def responder(prompt, system_prompt=None, **kwargs) -> str:
            self.usados.append(role)
            return "la escribió el rol " + role

        return responder

    async def aquery(self, consulta, param=None) -> str:
        return f"Lo que dice esta memoria sobre {consulta}."


class _Manager:
    def __init__(self, rag: _Rag) -> None:
        self._rag = rag

    async def get(self, _nemo_id):
        return self._rag

    async def map(self, nemo_ids, funcion) -> dict[str, Any]:
        return {n: await funcion(n, self._rag) for n in nemo_ids}


class _Registro:
    default_id = ""

    def list(self):
        return [
            SimpleNamespace(id="", name="General"),
            SimpleNamespace(id="obra-sur", name="Obra Sur"),
        ]

    def resolve(self, pedida):
        return pedida or ""

    def get(self, nemo_id):
        return next((n for n in self.list() if n.id == nemo_id), None)


def _ask_all(rag: _Rag):
    router = create_nemo_query_routes(_Registro(), _Manager(rag), None, None)
    ruta = next(r for r in router.routes if r.path == "/bimnemo/memory/ask-all")
    return ruta.endpoint


async def test_preguntar_a_todas_responde_con_el_rol_del_chat():
    """Con el rol van el modelo elegido, su razonamiento y su medición."""
    rag = _Rag()
    respuesta = await _ask_all(rag)(
        MultiSearchRequest(query="¿qué dice la norma?", nemos=["", "obra-sur"])
    )

    assert "query" in rag.usados, "debe responder el rol del chat"
    assert "base" not in rag.usados, (
        "llm_model_func no lleva modelo: con Claude u Ollama contesta otro"
    )
    assert "el rol query" in respuesta.response


async def test_el_rol_es_el_mismo_que_usa_el_chat_de_una_sola_memoria():
    """Dos caminos con dos modelos distintos serían dos productos."""
    from lightrag.llm_roles import ROLE_NAMES

    rag = _Rag()
    await _ask_all(rag)(MultiSearchRequest(query="¿y?"))
    assert set(rag.usados) <= set(ROLE_NAMES) and rag.usados == ["query"]
