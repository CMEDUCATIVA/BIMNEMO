"""Qué está funcionando: configuración del motor y versión de la interfaz.

Separado de ``bimnemo_routes`` porque responde a otra pregunta. Aquél dice
**qué hay guardado** —catálogo, métricas, ficheros, memoria—; éste dice **con
qué está corriendo**: qué modelo, qué almacenes, qué versión de la interfaz.

Es lo que se mira cuando algo no cuadra, y por eso conviene que no esté
mezclado con lo que se mira cuando todo va bien.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from lightrag.api.bimnemo import BIMNEMO_NAME, BIMNEMO_VERSION
from lightrag.api.bimnemo.build import (
    boot_at,
    boot_id,
    compute_fingerprint,
    startup_fingerprint,
)

from ..utils_api import get_combined_auth_dependency


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------


class EngineResponse(BaseModel):
    nemos: dict[str, Any] = Field(
        default_factory=dict,
        description="Qué memoria se describe y cuáles están abiertas",
    )
    product: dict[str, str]
    storages: dict[str, str]
    llm: dict[str, Any]
    embedding: dict[str, Any]
    chunking: dict[str, Any]
    query_defaults: dict[str, Any]
    workspace: str
    working_dir: str
    input_dir: str


# ---------------------------------------------------------------------------
# Factoría
# ---------------------------------------------------------------------------


def create_bimnemo_engine_routes(
    rag,
    doc_manager,
    resolve_rag,
    api_key: Optional[str] = None,
    registry=None,
    manager=None,
) -> APIRouter:
    """Router del estado del motor. Sin prefijo: lo aporta quien lo incluye.

    ``resolve_rag`` es la misma función que usa el router principal para
    elegir la instancia de una NEMO. Se inyecta en vez de duplicarla: una
    segunda versión de esa resolución acabaría discrepando de la primera.
    """
    combined_auth = get_combined_auth_dependency(api_key)
    router = APIRouter(tags=["bimnemo"])
    _resolve_rag = resolve_rag

    # -- Motor -------------------------------------------------------------

    @router.get(
        "/engine",
        response_model=EngineResponse,
        dependencies=[Depends(combined_auth)],
        summary="Configuración en curso del motor LightRAG",
    )
    async def get_engine(
        nemo: Optional[str] = Query(
            default=None, description="NEMO a describir; por defecto, la activa"
        ),
    ) -> EngineResponse:
        """La configuración efectiva, saneada.

        Nunca sale una credencial: se exponen nombres de modelo, de backend y
        parámetros numéricos, jamás claves de API ni cadenas de conexión. Para
        las claves solo se dice si están puestas o no.
        """
        target_rag, _, _ = await _resolve_rag(nemo)
        embedding_func = getattr(target_rag, "embedding_func", None)

        entry = registry.get(getattr(target_rag, "workspace", "")) if registry else None
        return EngineResponse(
            nemos={
                "describing": getattr(target_rag, "workspace", ""),
                "name": entry.name if entry else "General",
                "live": manager.live_ids() if manager else [],
                "total": len(registry.list()) if registry else 1,
            },
            product={
                "name": BIMNEMO_NAME,
                "version": BIMNEMO_VERSION,
                "engine": "LightRAG",
                "engine_version": _engine_version(),
            },
            storages={
                "kv": getattr(target_rag, "kv_storage", "?"),
                "vector": getattr(target_rag, "vector_storage", "?"),
                "graph": getattr(target_rag, "graph_storage", "?"),
                "doc_status": getattr(target_rag, "doc_status_storage", "?"),
            },
            llm={
                "model": getattr(rag, "llm_model_name", "?"),
                "binding": os.getenv("LLM_BINDING", "(sin definir)"),
                "host": os.getenv("LLM_BINDING_HOST", "(sin definir)"),
                "api_key_set": bool(os.getenv("LLM_BINDING_API_KEY")),
                "max_async": getattr(rag, "llm_model_max_async", None),
                "cache_enabled": getattr(rag, "enable_llm_cache", None),
                "summary_max_tokens": getattr(rag, "summary_max_tokens", None),
            },
            embedding={
                "binding": os.getenv("EMBEDDING_BINDING", "(sin definir)"),
                "model": os.getenv("EMBEDDING_MODEL", "(sin definir)"),
                "host": os.getenv("EMBEDDING_BINDING_HOST", "(sin definir)"),
                "api_key_set": bool(os.getenv("EMBEDDING_BINDING_API_KEY")),
                "dim": getattr(embedding_func, "embedding_dim", None),
                "batch_num": getattr(rag, "embedding_batch_num", None),
            },
            chunking={
                "chunk_token_size": getattr(rag, "chunk_token_size", None),
                "overlap_token_size": getattr(rag, "chunk_overlap_token_size", None),
                "chunker": os.getenv("CUSTOM_CHUNKER", "token_size (por defecto)"),
                "max_parallel_insert": getattr(rag, "max_parallel_insert", None),
            },
            query_defaults={
                "top_k": getattr(rag, "top_k", None),
                "cosine_threshold": getattr(rag, "cosine_better_than_threshold", None),
                "rerank_enabled": getattr(rag, "rerank_model_func", None) is not None,
                "rerank_binding": os.getenv("RERANK_BINDING", "null"),
            },
            workspace=getattr(target_rag, "workspace", "") or "",
            working_dir=str(getattr(target_rag, "working_dir", "")),
            input_dir=str(doc_manager.input_dir),
        )

    @router.get(
        "/app-build",
        dependencies=[Depends(combined_auth)],
        summary="Huella de la versión de la interfaz",
    )
    async def app_build() -> dict[str, Any]:
        """Qué versión de la interfaz hay en disco ahora mismo.

        La ventana se queda con esta huella al cargar y la vuelve a pedir cada
        cierto tiempo. Si cambió, es que se actualizó BIMNEMO y lo que se está
        ejecutando es el código anterior — una página que no se recarga no
        vuelve a pedir sus módulos, por mucho que el servidor los sirva sin
        caché.

        Sin esto, el síntoma es indistinguible de un fallo del programa: una
        lista desactualizada, o un botón que «no aparece».
        """
        actual = compute_fingerprint()
        return {
            "fingerprint": actual,
            "startup_fingerprint": startup_fingerprint(),
            "changed_since_startup": actual != startup_fingerprint(),
            # Identidad del proceso, que es otra pregunta: la huella resume
            # los ficheros en disco y no cambia al reiniciar. Quien espera a
            # que vuelva el motor mira esto, no `/health`, porque el proceso
            # moribundo sigue respondiendo un rato.
            "boot_id": boot_id(),
            "boot_at": boot_at(),
        }

    return router


# de datos, secreto de sesión…).
def _engine_version() -> str:
    """Versión del motor, sin romper si el paquete no la expone."""
    try:
        from lightrag import __version__

        return str(__version__)
    except Exception:  # pragma: no cover
        return "desconocida"


__all__ = ["create_bimnemo_engine_routes"]
