"""Lógica del catálogo de proveedores de IA de BIMNEMO.

Las tablas de proveedores viven en
:mod:`lightrag.api.bimnemo.provider_catalog`; aquí está lo que se hace con
ellas: validarlas, buscarlas, deducir cuál corresponde a una configuración ya
guardada y serializarlas para la vista.

**Un proveedor del catálogo no es un binding nuevo del motor.** La lista de
bindings reales es corta y fija (``lightrag/api/config.py``), y lo que la
multiplica es que el binding ``openai`` habla con cualquier API compatible con
OpenAI: DeepSeek, Groq, Mistral, OpenRouter, LM Studio o vLLM no necesitan
código, necesitan ese binding apuntando a su ``base_url``. El catálogo guarda
esa correspondencia para que elegir «DeepSeek» rellene lo correcto en vez de
obligar a saberse la URL.
"""

from __future__ import annotations

from typing import Any

from lightrag.api.bimnemo.provider_catalog import (
    LLM_PROVIDERS,
    Kind,
    Provider,
)
from lightrag.api.bimnemo.provider_catalog_retrieval import (
    EMBEDDING_PROVIDERS,
    RERANK_PROVIDERS,
)

_BY_KIND: dict[str, tuple[Provider, ...]] = {
    "llm": LLM_PROVIDERS,
    "embedding": EMBEDDING_PROVIDERS,
    "rerank": RERANK_PROVIDERS,
}

# Bindings que el motor admite de verdad, copiados de los `choices` del
# analizador de argumentos. Se comprueban al importar para que un preajuste
# mal editado falle aquí y no al arrancar el servidor.
VALID_BINDINGS: dict[str, frozenset[str]] = {
    "llm": frozenset(
        {
            "lollms",
            "ollama",
            "openai",
            "openai-ollama",
            "azure_openai",
            "bedrock",
            "gemini",
        }
    ),
    "embedding": frozenset(
        {
            "lollms",
            "ollama",
            "openai",
            "azure_openai",
            "bedrock",
            "jina",
            "gemini",
            "voyageai",
        }
    ),
    "rerank": frozenset({"null", "cohere", "jina", "aliyun"}),
}


def _validate_catalog() -> None:
    """Falla al importar si un preajuste apunta a un binding inexistente."""
    for kind, providers in _BY_KIND.items():
        allowed = VALID_BINDINGS[kind]
        seen: set[str] = set()
        for provider in providers:
            if provider.binding not in allowed:
                raise ValueError(
                    f"BIMNEMO: el proveedor {provider.key!r} de {kind} declara el "
                    f"binding {provider.binding!r}, que el motor no admite. "
                    f"Válidos: {sorted(allowed)}"
                )
            if provider.key in seen:
                raise ValueError(
                    f"BIMNEMO: clave de proveedor duplicada {provider.key!r} en {kind}"
                )
            seen.add(provider.key)


_validate_catalog()


def providers_for(kind: Kind) -> tuple[Provider, ...]:
    return _BY_KIND[kind]


def find(kind: Kind, key: str) -> Provider | None:
    for provider in _BY_KIND[kind]:
        if provider.key == key:
            return provider
    return None


def match_provider(kind: Kind, binding: str, host: str) -> str:
    """Deduce qué preajuste corresponde a un binding y host guardados.

    Hace falta porque ``.env`` guarda el binding real, no el preajuste: cinco
    proveedores distintos escriben ``LLM_BINDING=openai`` y solo el host los
    distingue. Sin esto, al reabrir la configuración el desplegable volvería
    siempre al primero de la lista y parecería que no se guardó nada.
    """
    normalized = (host or "").rstrip("/").lower()

    # 1. Coincidencia exacta de binding + host.
    for provider in _BY_KIND[kind]:
        if (
            provider.binding == binding
            and provider.host.rstrip("/").lower() == normalized
        ):
            return provider.key

    # 2. Mismo binding y host propio (los que lo dejan al motor).
    for provider in _BY_KIND[kind]:
        if provider.binding == binding and not provider.host:
            return provider.key

    # 3. Un binding openai con un host que no reconocemos es, por definición,
    #    «otro compatible»: es la respuesta correcta, no un descarte.
    if binding == "openai":
        return "openai_compatible"

    for provider in _BY_KIND[kind]:
        if provider.binding == binding:
            return provider.key

    return _BY_KIND[kind][0].key


def catalog_payload() -> dict[str, Any]:
    """El catálogo entero, tal y como lo consume la vista.

    ``reasoning`` lleva, por modelo, los niveles de la barra de razonamiento.
    Se calcula de ``razonamiento.esquema`` y no se escribe en las tablas: el
    control depende del modelo, no del proveedor, y así hay una sola fuente.
    """
    from lightrag.api.bimnemo import razonamiento

    def serialize(provider: Provider, kind: str) -> dict[str, Any]:
        return {
            "reasoning": (
                razonamiento.para_catalogo(provider.key, provider.models)
                if kind == "llm"
                else {}
            ),
            "key": provider.key,
            "label": provider.label,
            "binding": provider.binding,
            "group": provider.group,
            "host": provider.host,
            "models": list(provider.models),
            "needs_key": provider.needs_key,
            "key_hint": provider.key_hint,
            "key_url": provider.key_url,
            "note": provider.note,
            "dims": list(provider.dims),
            "host_hint": provider.host_hint,
            "host_used": provider.host_used,
        }

    return {
        kind: [serialize(p, kind) for p in providers]
        for kind, providers in _BY_KIND.items()
    }


__all__ = [
    "EMBEDDING_PROVIDERS",
    "LLM_PROVIDERS",
    "RERANK_PROVIDERS",
    "VALID_BINDINGS",
    "Provider",
    "catalog_payload",
    "find",
    "match_provider",
    "providers_for",
]
