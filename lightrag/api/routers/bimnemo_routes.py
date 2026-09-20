"""Superficie REST de BIMNEMO.

Dos grupos de endpoints, con propósitos distintos:

* ``/bimnemo/…`` — lo que necesita el panel: catálogo, métricas de
  almacenamiento, estado de la memoria, recuentos del grafo y la configuración
  del motor en curso.
* ``/bimnemo/memory/…`` — la superficie pensada para que **otro agente** se
  conecte a la memoria. Es fachada delgada sobre ``rag.aquery`` y
  ``rag.ainsert``; no reimplementa recuperación ni ingesta.

Lo que ya existe no se duplica. La subida de ficheros sigue siendo
``POST /documents/upload``, el listado paginado ``POST /documents/paginated``,
la respuesta completa ``POST /query`` y su versión en streaming
``POST /query/stream``. El panel los consume tal cual.

Sigue el patrón de factoría del paquete ``routers``: el ``APIRouter`` se
construye dentro de la función, nunca como singleton de módulo, porque un
singleton acumula rutas duplicadas si la factoría se invoca dos veces en el
mismo proceso.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from lightrag.api.bimnemo import BIMNEMO_NAME, BIMNEMO_VERSION
from lightrag.api.bimnemo.catalog import categories_payload, known_extensions
from lightrag.api.bimnemo.stats import (
    DEFAULT_GRAPH_COUNT_CAP,
    graph_counts,
    merge_files_with_memory,
    scan_storage,
    summarize_memory,
    summarize_storage,
)
from lightrag.base import DocStatus, QueryParam
from lightrag.api.bimnemo.manifiesto import AMBITOS, ENDPOINTS, GRUPOS, MODOS
from lightrag.utils import logger

from ..utils_api import get_combined_auth_dependency, internal_server_error
from .bimnemo_documents_routes import create_bimnemo_documents_routes
from .bimnemo_update_routes import create_bimnemo_update_routes
from .bimnemo_engine_routes import create_bimnemo_engine_routes
from .bimnemo_settings_routes import create_bimnemo_settings_routes


# ---------------------------------------------------------------------------
# Modelos de respuesta y petición
# ---------------------------------------------------------------------------


class CategoryModel(BaseModel):
    key: str = Field(description="Clave estable de la categoría")
    label: str = Field(description="Nombre para mostrar")
    icon: str = Field(description="Nombre del icono Lucide")
    color: str = Field(description="Token de color del Lookbook")


class CatalogResponse(BaseModel):
    categories: list[CategoryModel]
    known_extensions: list[str] = Field(
        description="Extensiones que BIMNEMO sabe clasificar en el panel"
    )
    ingestible_extensions: list[str] = Field(
        description=(
            "Extensiones que el motor admite subir ahora mismo. Se deriva viva "
            "del registro de parsers y de LIGHTRAG_PARSER, no de una lista fija."
        )
    )


class StatsResponse(BaseModel):
    storage: dict[str, Any] = Field(
        description="Bytes reales en disco, repartidos por categoría y por tipo"
    )
    memory: dict[str, Any] = Field(
        description="Qué documentos conoce el motor, por estado"
    )
    engine: dict[str, Any] = Field(description="Identidad y salud del motor")


class GraphResponse(BaseModel):
    nodes: list[dict[str, Any]] = Field(
        description="Entidades, con nombre, tipo, grado y descripción"
    )
    edges: list[dict[str, Any]] = Field(description="Relaciones entre entidades")
    truncated: bool = Field(description="Había más nodos de los que caben")
    types: list[dict[str, Any]] = Field(description="Recuento por tipo de entidad")


class FilesResponse(BaseModel):
    files: list[dict[str, Any]]
    total: int
    returned: int
    scan_error: Optional[str] = None


class GraphStatsResponse(BaseModel):
    supported: bool
    entities: int
    relations: int
    truncated: bool
    cap: Optional[int] = None
    reason: Optional[str] = None


class MemorySearchRequest(BaseModel):
    """Recuperación sin generación."""

    query: str = Field(min_length=1, description="Qué se busca en la memoria")
    mode: Literal["local", "global", "hybrid", "naive", "mix"] = Field(
        default="mix", description="Modo de recuperación de LightRAG"
    )
    top_k: Optional[int] = Field(
        default=None, ge=1, le=500, description="Entidades/relaciones a recuperar"
    )
    chunk_top_k: Optional[int] = Field(
        default=None, ge=1, le=200, description="Fragmentos de texto a conservar"
    )
    enable_rerank: Optional[bool] = Field(
        default=None, description="Reordenar con el reranker configurado"
    )


class MemorySearchResponse(BaseModel):
    query: str
    mode: str
    context: str = Field(
        description="Contexto recuperado, sin pasar por el LLM generador"
    )


class MemoryRememberRequest(BaseModel):
    """Inserción de texto en la memoria."""

    text: str = Field(min_length=1, description="Texto a recordar")
    source: Optional[str] = Field(
        default=None,
        description="Origen del texto; se usa como file_path para las citas",
    )


class MemoryRememberResponse(BaseModel):
    status: str
    source: str
    message: str


# ---------------------------------------------------------------------------
# Factoría
# ---------------------------------------------------------------------------


def create_bimnemo_routes(
    rag,
    doc_manager,
    api_key: Optional[str] = None,
    registry=None,
    manager=None,
) -> APIRouter:
    """Construye el router de BIMNEMO.

    Args:
        rag: la instancia ``LightRAG`` por defecto del servidor.
        doc_manager: el ``DocumentManager`` del router de documentos; de él
            salen el directorio de entrada y la lista viva de extensiones
            admitidas, que no se duplica aquí.
        api_key: la clave de API del servidor, si la hay.
        registry: índice de NEMOs. Opcional: sin él, todo responde por la
            instancia por defecto, que es como se comportaba antes de que
            existieran las memorias múltiples.
        manager: gestor de instancias por NEMO, con la misma condición.
    """
    combined_auth = get_combined_auth_dependency(api_key)
    router = APIRouter(prefix="/bimnemo", tags=["bimnemo"])

    async def _resolve_rag(nemo: Optional[str]):
        """Instancia y carpeta de entrada de la NEMO pedida.

        Sin NEMO —o sin registro— responde la de por defecto: es lo que hacía
        este router antes y lo que siguen esperando sus llamadores.

        La carpeta de la memoria base es la RAÍZ de ``inputs/``, donde ahora
        cuelgan las demás; hay que excluirlas o contaría los archivos de todas.
        """
        if registry is None or manager is None:
            return rag, Path(doc_manager.input_dir), frozenset()

        try:
            nemo_id = registry.resolve(nemo)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        base = Path(doc_manager.base_input_dir)
        if nemo_id:
            return await manager.get(nemo_id), base / nemo_id, frozenset()
        otras = frozenset(n.id for n in registry.list() if n.id)
        return await manager.get(nemo_id), base, otras

    def _input_dir() -> Path:
        return Path(doc_manager.input_dir)

    # -- Catálogo ----------------------------------------------------------

    @router.get(
        "/catalog",
        response_model=CatalogResponse,
        dependencies=[Depends(combined_auth)],
        summary="Catálogo de categorías y extensiones",
    )
    async def get_catalog() -> CatalogResponse:
        """Las ocho categorías del panel y qué extensiones caen en cada una.

        ``ingestible_extensions`` no es una copia: se lee de
        ``doc_manager.supported_extensions``, que el motor deriva del registro
        de parsers y de las reglas de enrutado en curso. Una extensión puede
        estar en ``known_extensions`` (BIMNEMO sabe dibujarla) y no en
        ``ingestible_extensions`` (el motor no la parsea con esta config).
        """
        try:
            ingestible = sorted(
                str(ext).lower().lstrip(".") for ext in doc_manager.supported_extensions
            )
        except Exception as exc:  # una config de parser rota no tumba el panel
            logger.warning("BIMNEMO: no se pudieron leer las extensiones: %s", exc)
            ingestible = []

        return CatalogResponse(
            categories=[CategoryModel(**c) for c in categories_payload()],
            known_extensions=list(known_extensions()),
            ingestible_extensions=ingestible,
        )

    # -- Métricas ----------------------------------------------------------

    @router.get(
        "/stats",
        response_model=StatsResponse,
        dependencies=[Depends(combined_auth)],
        summary="Métricas del panel: almacenamiento, categorías, tipos y estado",
    )
    async def get_stats(
        nemo: Optional[str] = Query(
            default=None, description="NEMO a consultar; por defecto, la activa"
        ),
    ) -> StatsResponse:
        """Todo lo que pinta el panel de un vistazo, salvo el grafo.

        El grafo va aparte (``/bimnemo/stats/graph``) porque contarlo es caro y
        el panel no debe esperar a él para enseñar lo demás.
        """
        try:
            target_rag, entrada, excluir = await _resolve_rag(nemo)
            snapshot = await scan_storage(entrada, exclude=excluir)
            storage = summarize_storage(snapshot)
            memory = await summarize_memory(target_rag)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("BIMNEMO: fallo al agregar métricas: %s", exc)
            raise internal_server_error(exc)

        return StatsResponse(
            storage=storage,
            memory=memory,
            engine={
                "product": BIMNEMO_NAME,
                "version": BIMNEMO_VERSION,
                "workspace": getattr(target_rag, "workspace", "") or "(por defecto)",
                "graph_storage": getattr(target_rag, "graph_storage", "desconocido"),
                "vector_storage": getattr(target_rag, "vector_storage", "desconocido"),
            },
        )

    @router.get(
        "/stats/graph",
        response_model=GraphStatsResponse,
        dependencies=[Depends(combined_auth)],
        summary="Recuento de entidades y relaciones del grafo",
    )
    async def get_graph_stats(
        nemo: Optional[str] = Query(
            default=None, description="NEMO a contar; por defecto, la activa"
        ),
        cap: int = Query(
            default=DEFAULT_GRAPH_COUNT_CAP,
            ge=1_000,
            le=5_000_000,
            description="Tope de recuento; por encima la respuesta se marca truncada",
        ),
    ) -> GraphStatsResponse:
        """Cuenta el grafo con memoria acotada y con tope.

        Devuelve ``supported: false`` en lugar de fallar cuando el backend de
        grafo no admite iteración acotada: el panel enseña «no disponible», que
        es la verdad, en vez de arrastrar el grafo entero a memoria.
        """
        target_rag, _, _ = await _resolve_rag(nemo)
        counts = await graph_counts(target_rag, cap=cap)
        return GraphStatsResponse(**counts)

    @router.get(
        "/files",
        response_model=FilesResponse,
        dependencies=[Depends(combined_auth)],
        summary="Ficheros almacenados, con su categoría, tipo, peso y estado",
    )
    async def get_files(
        category: Optional[str] = Query(
            default=None, description="Filtra por clave de categoría"
        ),
        nemo: Optional[str] = Query(
            default=None, description="NEMO a listar; por defecto, la activa"
        ),
        limit: int = Query(default=500, ge=1, le=5000),
    ) -> FilesResponse:
        """Cruza lo que hay en disco con lo que el motor sabe de cada fichero.

        Un fichero con ``status: null`` está en disco pero el motor no lo
        conoce: subido y aún sin escanear, o borrado de la memoria dejando el
        fichero atrás.
        """
        try:
            target_rag, entrada, excluir = await _resolve_rag(nemo)
            snapshot = await scan_storage(entrada, exclude=excluir)
            documents: dict[str, Any] = {}
            try:
                documents = await target_rag.doc_status.get_docs_by_statuses(
                    list(DocStatus), strict=False
                )
            except Exception as exc:
                logger.warning("BIMNEMO: doc_status ilegible al listar: %s", exc)

            rows = merge_files_with_memory(snapshot, documents)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("BIMNEMO: fallo al listar ficheros: %s", exc)
            raise internal_server_error(exc)

        if category:
            rows = [r for r in rows if r["category"] == category]

        return FilesResponse(
            files=rows[:limit],
            total=len(rows),
            returned=min(len(rows), limit),
            scan_error=snapshot.scan_error,
        )

    @router.get(
        "/graph",
        response_model=GraphResponse,
        dependencies=[Depends(combined_auth)],
        summary="Subgrafo de conocimiento de una NEMO, para dibujarlo",
    )
    async def get_graph(
        nemo: Optional[str] = Query(
            default=None, description="NEMO a consultar; por defecto, la activa"
        ),
        label: str = Query(
            default="*",
            description="Entidad desde la que partir. «*» es el grafo entero.",
        ),
        max_depth: int = Query(default=3, ge=1, le=6),
        max_nodes: int = Query(default=250, ge=1, le=2000),
    ) -> GraphResponse:
        """El grafo listo para pintar, con los nodos ya resumidos.

        Se devuelve **aplanado**: el motor da las propiedades en un diccionario
        libre y cada backend mete las suyas, así que dibujar contra eso
        obligaría a la vista a conocer las rarezas de cada almacén. Aquí se
        reduce a lo que un grafo necesita — nombre, tipo, grado, descripción —
        y el resto queda disponible sin que la vista dependa de ello.

        El tope por defecto es 250 nodos, no los 1000 del motor: por encima de
        unos cientos un grafo deja de leerse y solo pesa. Con «*», el motor
        ordena por grado, así que los 250 primeros son los más conectados —
        justo los que dan la forma del conjunto.
        """
        try:
            target_rag, _, _ = await _resolve_rag(nemo)
            graph = await target_rag.get_knowledge_graph(
                node_label=label, max_depth=max_depth, max_nodes=max_nodes
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("BIMNEMO: fallo al leer el grafo: %s", exc)
            raise internal_server_error(exc)

        degrees: dict[str, int] = {}
        for edge in graph.edges:
            degrees[edge.source] = degrees.get(edge.source, 0) + 1
            degrees[edge.target] = degrees.get(edge.target, 0) + 1

        nodes = [
            {
                "id": node.id,
                "label": str(node.properties.get("entity_id") or node.id),
                "type": str(node.properties.get("entity_type") or "desconocido"),
                "degree": degrees.get(node.id, 0),
                "description": str(node.properties.get("description") or "")[:400],
                "file_path": str(node.properties.get("file_path") or ""),
            }
            for node in graph.nodes
        ]
        edges = [
            {
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "label": str(edge.properties.get("keywords") or edge.type or ""),
                "weight": float(edge.properties.get("weight") or 1),
                "description": str(edge.properties.get("description") or "")[:300],
            }
            for edge in graph.edges
        ]

        tipos: dict[str, int] = {}
        for node in nodes:
            tipos[node["type"]] = tipos.get(node["type"], 0) + 1

        return GraphResponse(
            nodes=nodes,
            edges=edges,
            truncated=bool(graph.is_truncated),
            types=sorted(
                ({"type": t, "count": c} for t, c in tipos.items()),
                key=lambda x: (-x["count"], x["type"]),
            ),
        )

    # -- Memoria para agentes ---------------------------------------------

    @router.get(
        "/memory/manifest",
        dependencies=[Depends(combined_auth)],
        summary="Descriptor legible por máquina de la memoria BIMNEMO",
    )
    async def get_memory_manifest() -> dict[str, Any]:
        """Lo que un agente necesita leer una vez para saber usar la memoria.

        Existe porque descubrir la superficie útil dentro del esquema OpenAPI
        completo del servidor es trabajo; esto lo da masticado, con los modos
        de recuperación y cuándo usar cada endpoint.
        """
        return {
            "name": BIMNEMO_NAME,
            "version": BIMNEMO_VERSION,
            "engine": "LightRAG",
            "description": (
                "Memoria de conocimiento con grafo. Recupera con "
                "/bimnemo/memory/search cuando quieras el contexto en crudo y "
                "responder tú; usa /query cuando quieras que responda el motor."
            ),
            "authentication": (
                "Cabecera X-API-Key, o Authorization: Bearer <token>"
                if api_key
                else "Sin autenticación en esta instancia"
            ),
            # La lista vive en `bimnemo/manifiesto.py`: es datos, no rutas,
            # y se toca por un motivo distinto que este fichero. Ahí está
            # también escrito por qué NO están las 32 rutas del servidor.
            "endpoints": ENDPOINTS,
            "groups": GRUPOS,
            "ambitos": AMBITOS,
            "retrieval_modes": MODOS,
            "openapi": "/openapi.json",
            "swagger": "/docs",
        }

    @router.post(
        "/memory/search",
        response_model=MemorySearchResponse,
        dependencies=[Depends(combined_auth)],
        summary="Recuperar contexto de la memoria, sin generar respuesta",
    )
    async def memory_search(request: MemorySearchRequest) -> MemorySearchResponse:
        """Devuelve el contexto recuperado y nada más.

        Es ``rag.aquery`` con ``only_need_context=True``: la recuperación
        completa del motor (grafo, vectores, reordenado si está configurado)
        pero sin la llamada al LLM que redacta. Para un agente que ya tiene su
        propio modelo, esto es lo que quiere — y se ahorra esa llamada.
        """
        param = QueryParam(mode=request.mode, only_need_context=True, stream=False)
        if request.top_k is not None:
            param.top_k = request.top_k
        if request.chunk_top_k is not None:
            param.chunk_top_k = request.chunk_top_k
        if request.enable_rerank is not None:
            param.enable_rerank = request.enable_rerank

        try:
            context = await rag.aquery(request.query, param=param)
        except Exception as exc:
            logger.error("BIMNEMO: fallo en memory/search: %s", exc)
            raise internal_server_error(exc)

        # only_need_context devuelve texto, pero un modo sin resultados puede
        # devolver None; el contrato de este endpoint es siempre cadena.
        return MemorySearchResponse(
            query=request.query,
            mode=request.mode,
            context=context if isinstance(context, str) else "",
        )

    @router.post(
        "/memory/remember",
        response_model=MemoryRememberResponse,
        dependencies=[Depends(combined_auth)],
        summary="Guardar un texto en la memoria",
    )
    async def memory_remember(
        request: MemoryRememberRequest,
    ) -> MemoryRememberResponse:
        """Inserta texto por la vía pública del motor.

        Delega en ``rag.ainsert``, que respeta el pipeline, el doc-status y los
        anclajes de recuperación de purga. No escribe en los almacenes por su
        cuenta.
        """
        source = request.source or "bimnemo://memoria-directa"
        try:
            await rag.ainsert(request.text, file_paths=source)
        except Exception as exc:
            logger.error("BIMNEMO: fallo en memory/remember: %s", exc)
            raise internal_server_error(exc)

        return MemoryRememberResponse(
            status="accepted",
            source=source,
            message=(
                "Texto encolado. La extracción de entidades corre en segundo "
                "plano; consulta /documents/pipeline_status para seguirla."
            ),
        )

    # El estado del motor y la versión de la interfaz viven aparte: son la
    # pregunta «con qué está corriendo», no «qué hay guardado».
    router.include_router(
        create_bimnemo_engine_routes(
            rag, doc_manager, _resolve_rag, api_key, registry, manager
        )
    )
    # La configuración de IA vive en su propio módulo y se monta aquí, de
    # modo que el servidor sigue dando de alta un solo router de BIMNEMO.
    router.include_router(create_bimnemo_settings_routes(rag, api_key))
    # `_resolve_rag` se inyecta por lo mismo que en el router del motor: una
    # segunda resolución acabaría discrepando, y se borraría en otra memoria.
    router.include_router(
        create_bimnemo_documents_routes(doc_manager, _resolve_rag, api_key)
    )
    # Actualizar el programa no es una operación sobre la memoria, pero se
    # niega por lo mismo que el reinicio —una ingesta a medias—, así que se le
    # inyecta la MISMA comprobación de ocupado. Dos versiones de «¿está
    # ocupado?» acabarían discrepando justo cuando importa.
    from .document_routes import check_pipeline_busy_or_raise

    router.include_router(
        create_bimnemo_update_routes(rag, check_pipeline_busy_or_raise, api_key)
    )

    return router


# Lo único que la pantalla de configuración puede escribir en el .env. Es una
# lista blanca a propósito: este endpoint configura la IA, no es una vía
# general para reescribir el despliegue (rutas de datos, credenciales de base


__all__ = ["create_bimnemo_routes"]
