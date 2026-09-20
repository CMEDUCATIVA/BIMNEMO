"""Endpoints de NEMOs: gestión de las memorias y acceso a cada una.

Dos superficies, con propósitos distintos:

* ``/bimnemo/nemos…`` — crear, listar, renombrar y borrar memorias. Lo usa la
  interfaz.
* ``/nemo/{nemo}/…`` — **rutas espejo**. Lo mismo que ya ofrecían
  ``/query``, ``/documents/upload`` y la fachada de memoria, pero contra la
  NEMO que se nombra en la URL. Es la vía por la que una IA externa elige
  memoria.

## Por qué rutas espejo y no cambiar las que hay

``POST /documents/upload`` y ``POST /query`` los usa el WebUI de LightRAG y
cualquier integración anterior. **No se les cambia la firma.** Siguen
apuntando a la NEMO por defecto y se comportan exactamente igual que antes.
Lo nuevo se añade al lado; nada de lo que ya funcionaba se entera.

Quien prefiera no cambiar de URL tiene la otra vía: la cabecera
``LIGHTRAG-WORKSPACE``, que es la convención que el propio LightRAG define.
Ambas resuelven al mismo sitio porque el registro sanea los nombres igual que
lo hace el servidor con esa cabecera.

## Una NEMO desconocida da 404, no cae en la de por defecto

Es el fallo más caro posible aquí: silencioso, y solo se descubre cuando
alguien pregunta a una memoria y le responde otra. Mejor un error claro.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from lightrag.api.bimnemo.nemo_registry import NemoError, NemoRegistry
from lightrag.api.bimnemo.stats import (
    scan_storage,
    summarize_memory,
    summarize_storage,
)
from lightrag.utils import logger

from ..utils_api import get_combined_auth_dependency
from .nemo_query_routes import create_nemo_query_routes

#: Cabecera que LightRAG ya define para seleccionar workspace. Se respeta tal
#: cual para que una integración escrita contra el motor siga valiendo.
WORKSPACE_HEADER = "LIGHTRAG-WORKSPACE"


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------


class NemoModel(BaseModel):
    id: str = Field(description="Identificador y workspace real")
    name: str = Field(description="Nombre visible")
    created_at: str
    protected: bool = Field(description="La memoria base no se puede borrar")
    live: bool = Field(description="Tiene instancia abierta ahora mismo")


class NemoListResponse(BaseModel):
    nemos: list[NemoModel]
    default: str
    live: list[str] = Field(description="NEMOs con instancia abierta")


class CreateNemoRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60, description="Nombre visible")


class RenameNemoRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class DeleteNemoRequest(BaseModel):
    confirm_name: str = Field(
        description=(
            "El nombre exacto de la NEMO. Borrar es irreversible, así que se "
            "exige escribirlo: un clic de más no puede costar una memoria."
        )
    )
    purge_files: bool = Field(
        default=False,
        description="Además de quitarla del índice, borrar su carpeta de datos",
    )


class DeleteNemoResponse(BaseModel):
    deleted: str
    files_removed: bool
    message: str


class NemosStatsResponse(BaseModel):
    total: dict[str, Any] = Field(
        description="Suma de todas las NEMOs: archivos, bytes y categorías"
    )
    nemos: list[dict[str, Any]] = Field(description="Desglose memoria a memoria")
    default: str


class SimpleResponse(BaseModel):
    status: str
    nemo: str
    message: str


# ---------------------------------------------------------------------------
# Factoría
# ---------------------------------------------------------------------------


def create_nemo_routes(
    registry: NemoRegistry,
    manager,
    doc_manager,
    working_dir: str,
    api_key: Optional[str] = None,
) -> APIRouter:
    """Router de gestión y acceso por NEMO.

    Args:
        registry: índice de memorias.
        manager: ``NemoManager`` que sirve la instancia de cada una.
        doc_manager: ``DocumentManager`` del servidor; de él sale el
            directorio de entrada y la lista viva de extensiones admitidas.
        working_dir: directorio de datos del motor, raíz de las carpetas
            de cada NEMO.
        api_key: clave del servidor, si la hay.
    """
    combined_auth = get_combined_auth_dependency(api_key)
    router = APIRouter(tags=["nemo"])

    def _resolve(requested: str | None) -> str:
        try:
            return registry.resolve(requested)
        except NemoError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def _as_model(nemo, live_ids: list[str]) -> NemoModel:
        return NemoModel(**nemo.to_payload(), live=nemo.id in live_ids)

    # -- Gestión -----------------------------------------------------------

    @router.get(
        "/bimnemo/nemos",
        response_model=NemoListResponse,
        dependencies=[Depends(combined_auth)],
        summary="Listar las memorias (NEMO) existentes",
    )
    async def list_nemos() -> NemoListResponse:
        live = manager.live_ids()
        return NemoListResponse(
            nemos=[_as_model(n, live) for n in registry.list()],
            default=registry.default_id,
            live=live,
        )

    @router.post(
        "/bimnemo/nemos",
        response_model=NemoModel,
        status_code=201,
        dependencies=[Depends(combined_auth)],
        summary="Crear una memoria nueva",
    )
    async def create_nemo(request: CreateNemoRequest) -> NemoModel:
        """Registra una NEMO. **No crea carpetas ni indexa nada.**

        La carpeta la crea el almacenamiento la primera vez que se use. Así un
        fallo aquí no deja carpetas huérfanas por el disco.
        """
        try:
            nemo = registry.create(request.name)
        except NemoError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _as_model(nemo, manager.live_ids())

    @router.patch(
        "/bimnemo/nemos/{nemo_id}",
        response_model=NemoModel,
        dependencies=[Depends(combined_auth)],
        summary="Renombrar una memoria",
    )
    async def rename_nemo(nemo_id: str, request: RenameNemoRequest) -> NemoModel:
        """Cambia el nombre visible. El identificador —y la carpeta— no se tocan."""
        try:
            nemo = registry.rename(nemo_id, request.name)
        except NemoError as exc:
            code = 404 if "No existe" in str(exc) else 409
            raise HTTPException(status_code=code, detail=str(exc)) from exc
        return _as_model(nemo, manager.live_ids())

    @router.patch(
        "/bimnemo/nemos",
        response_model=NemoModel,
        dependencies=[Depends(combined_auth)],
        summary="Renombrar una memoria, indicándola por parámetro",
    )
    async def rename_nemo_por_parametro(
        request: RenameNemoRequest,
        nemo: str = Query(
            default="",
            description=(
                "Identificador de la memoria. Vacío o ausente: la de por defecto."
            ),
        ),
    ) -> NemoModel:
        """Igual que la ruta con el identificador en el camino, pero por parámetro.

        Existe porque **la memoria por defecto tiene el identificador vacío**
        —es el espacio de trabajo sin nombre de LightRAG— y una cadena vacía no
        cabe en una ruta: ``/bimnemo/nemos/`` responde 307 y ``/bimnemo/nemos``
        405. Sin esto, la única memoria que todo el mundo tiene es la única que
        no se puede renombrar.

        Además es como funciona **todo lo demás** en BIMNEMO: la memoria se
        indica con ``?nemo=``, y omitirlo significa la de por defecto. La ruta
        con el identificador en el camino era la excepción; se mantiene por si
        algo la usa.
        """
        return await rename_nemo(nemo, request)

    @router.post(
        "/bimnemo/nemos/default",
        response_model=NemoListResponse,
        dependencies=[Depends(combined_auth)],
        summary="Fijar la memoria por defecto, indicándola por parámetro",
    )
    async def set_default_por_parametro(
        nemo: str = Query(
            default="",
            description=(
                "Identificador de la memoria. Vacío o ausente: la de por defecto."
            ),
        ),
    ) -> NemoListResponse:
        """Mismo motivo que arriba: un identificador vacío no cabe en una ruta."""
        return await set_default_nemo(nemo)

    @router.post(
        "/bimnemo/nemos/{nemo_id}/default",
        response_model=NemoListResponse,
        dependencies=[Depends(combined_auth)],
        summary="Fijar la memoria por defecto",
    )
    async def set_default_nemo(nemo_id: str) -> NemoListResponse:
        try:
            registry.set_default(nemo_id)
        except NemoError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        live = manager.live_ids()
        return NemoListResponse(
            nemos=[_as_model(n, live) for n in registry.list()],
            default=registry.default_id,
            live=live,
        )

    # DELETE con cuerpo: es la convención que el propio LightRAG usa en
    # `DELETE /documents/delete_document`, y aquí hace falta para exigir el
    # nombre de confirmación.
    @router.delete(
        "/bimnemo/nemos/{nemo_id}",
        response_model=DeleteNemoResponse,
        dependencies=[Depends(combined_auth)],
        summary="Borrar una memoria",
    )
    async def delete_nemo(
        nemo_id: str, request: DeleteNemoRequest
    ) -> DeleteNemoResponse:
        """Quita la NEMO del índice y, si se pide, borra su carpeta.

        Exige repetir el nombre. Borrar una memoria es irreversible y no puede
        depender de un clic: la confirmación escrita obliga a leer qué se está
        borrando.

        La instancia se **cierra antes** de tocar el disco. En Windows un
        fichero abierto no se borra, y a medio camino quedaría una carpeta
        mutilada.
        """
        nemo = registry.get(nemo_id)
        if nemo is None:
            raise HTTPException(
                status_code=404, detail=f"No existe la NEMO {nemo_id!r}"
            )
        if request.confirm_name.strip() != nemo.name:
            raise HTTPException(
                status_code=400,
                detail=(
                    "El nombre de confirmación no coincide. Escribe "
                    f"{nemo.name!r} para borrarla."
                ),
            )

        try:
            registry.delete(nemo_id)
        except NemoError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        await manager.close(nemo_id)

        files_removed = False
        if request.purge_files and nemo_id:
            target = Path(working_dir) / nemo_id
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                    files_removed = True
                inputs = Path(doc_manager.base_input_dir) / nemo_id
                if inputs.is_dir():
                    shutil.rmtree(inputs)
            except OSError as exc:
                # El índice ya está actualizado: la NEMO ha desaparecido de la
                # interfaz. Que además quede la carpeta es recuperable; fingir
                # que se borró no lo sería.
                logger.error(
                    "BIMNEMO: no se pudo borrar la carpeta de %r: %s", nemo_id, exc
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"La NEMO se quitó del índice pero su carpeta no se pudo "
                        f"borrar: {exc}"
                    ),
                ) from exc

        return DeleteNemoResponse(
            deleted=nemo.name,
            files_removed=files_removed,
            message=(
                f"NEMO {nemo.name!r} eliminada"
                + (" junto con sus archivos." if files_removed else " del índice.")
            ),
        )

    # -- Métricas de todas las NEMO ---------------------------------------

    def _nemo_paths(nemo_id: str) -> tuple[Path, frozenset[str]]:
        """Carpeta de entrada de una NEMO y qué subcarpetas no son suyas.

        La memoria base usa la RAÍZ de ``inputs/``, y las demás viven en
        subcarpetas suyas. Sin excluirlas, la base contaría los archivos de
        todas y el total del panel saldría duplicado.
        """
        base = Path(doc_manager.base_input_dir)
        if nemo_id:
            return base / nemo_id, frozenset()
        otras = {n.id for n in registry.list() if n.id}
        return base, frozenset(otras)

    @router.get(
        "/bimnemo/nemos/stats",
        response_model=NemosStatsResponse,
        dependencies=[Depends(combined_auth)],
        summary="Totales generales y desglose por NEMO",
    )
    async def nemos_stats() -> NemosStatsResponse:
        """Lo que hay almacenado en cada memoria, y la suma de todas.

        Solo se abre la instancia de las NEMOs que YA estaban abiertas: el
        recuento de documentos de una memoria dormida se deja en ``null`` en
        lugar de despertarla. Abrir seis memorias para pintar un panel
        significaría seis grafos en RAM por mirar una cifra.

        Los bytes sí salen de todas, porque eso se lee del disco y no cuesta
        abrir nada.
        """
        detalle: list[dict[str, Any]] = []
        total_files = 0
        total_bytes = 0
        total_docs = 0
        categorias: dict[str, dict[str, Any]] = {}

        for nemo in registry.list():
            entrada, excluir = _nemo_paths(nemo.id)
            snapshot = await scan_storage(entrada, exclude=excluir)
            resumen = summarize_storage(snapshot)

            viva = manager.peek(nemo.id)
            memoria: dict[str, Any] | None = None
            if viva is not None:
                memoria = await summarize_memory(viva)
                total_docs += memoria.get("total_documents", 0) or 0

            total_files += resumen["total_files"]
            total_bytes += resumen["total_bytes"]

            # El reparto por categoría del panel es el de TODAS las NEMOs
            # sumadas: es la vista general que pidió el usuario.
            for categoria in resumen["categories"]:
                acumulada = categorias.setdefault(
                    categoria["key"],
                    {**categoria, "files": 0, "size_bytes": 0},
                )
                acumulada["files"] += categoria["files"]
                acumulada["size_bytes"] += categoria["size_bytes"]

            detalle.append(
                {
                    "id": nemo.id,
                    "name": nemo.name,
                    "protected": nemo.protected,
                    "live": viva is not None,
                    "files": resumen["total_files"],
                    "size_bytes": resumen["total_bytes"],
                    "categories_in_use": resumen["categories_in_use"],
                    "types_in_use": resumen["types_in_use"],
                    "documents": (memoria or {}).get("total_documents"),
                    "chunks": (memoria or {}).get("total_chunks"),
                    "scan_error": resumen["scan_error"],
                }
            )

        lista = list(categorias.values())
        return NemosStatsResponse(
            total={
                "nemos": len(detalle),
                "total_files": total_files,
                "total_bytes": total_bytes,
                "documents_in_live_nemos": total_docs,
                "categories": lista,
                "categories_in_use": sum(1 for c in lista if c["files"] > 0),
                "categories_available": len(lista),
            },
            nemos=detalle,
            default=registry.default_id,
        )

    # El acceso por NEMO vive en su propio módulo y se monta aquí, para que
    # el servidor siga dando de alta un solo router de NEMO.
    router.include_router(
        create_nemo_query_routes(registry, manager, doc_manager, api_key)
    )

    return router


__all__ = ["create_nemo_routes"]
