"""Nombres de archivo que caben: el límite de cada memoria y renombrar.

Aparte de ``bimnemo_documents_routes`` porque responde a otra pregunta —¿este
nombre sirve?— y porque aquel ya roza el tope de 600 líneas.

La regla está en ``bimnemo/nombres.py``. Aquí solo se sabe lo que la ventana
no puede saber: **la ruta real** de la memoria en este equipo, de la que
depende cuántos caracteres caben.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from lightrag.api.bimnemo import nombres
from lightrag.constants import PARSED_DIR_NAME
from lightrag.utils import logger

from ..utils_api import get_combined_auth_dependency
from .document_routes import get_managed_background_tasks


class LimitsResponse(BaseModel):
    parsed_root_len: int = Field(
        description=(
            "Longitud de «<entrada>\\__parsed__\\» en este equipo; con ella y la "
            "extensión, nombres.maximo() da cuántos caracteres caben"
        )
    )
    max_docx: int = Field(description="Caracteres que caben para un .docx")
    max_pdf: int = Field(description="Caracteres que caben para un .pdf")


class RenameRequest(BaseModel):
    name: str = Field(description="Nombre actual del archivo, sin ruta")
    new_name: str = Field(description="Nombre nuevo, con la misma extensión")


class RenameResponse(BaseModel):
    status: str
    message: str


def _raiz_leidos(entrada: Path) -> int:
    return len(str(Path(entrada) / PARSED_DIR_NAME)) + 1


def create_bimnemo_nombres_routes(
    doc_manager, resolve_rag, api_key: Optional[str] = None
) -> APIRouter:
    """Sin prefijo propio: se monta dentro del router de BIMNEMO."""
    combined_auth = get_combined_auth_dependency(api_key)
    router = APIRouter(tags=["bimnemo"])

    @router.get(
        "/files/limits",
        response_model=LimitsResponse,
        dependencies=[Depends(combined_auth)],
        summary="Cuántos caracteres caben en un nombre de archivo en esta memoria",
    )
    async def get_limits(
        nemo: Optional[str] = Query(
            default=None, description="NEMO; por defecto, la activa"
        ),
    ) -> LimitsResponse:
        _, entrada, _ = await resolve_rag(nemo)
        raiz = _raiz_leidos(entrada)
        return LimitsResponse(
            parsed_root_len=raiz,
            max_docx=nombres.maximo(raiz, ".docx"),
            max_pdf=nombres.maximo(raiz, ".pdf"),
        )

    @router.post(
        "/files/rename",
        response_model=RenameResponse,
        dependencies=[Depends(combined_auth)],
        summary="Renombrar un archivo y volver a indexarlo",
    )
    async def rename_file(
        nemo: Optional[str] = Query(
            default=None, description="NEMO; por defecto, la activa"
        ),
        request: RenameRequest = Body(...),
        tareas: set = Depends(get_managed_background_tasks),
    ) -> RenameResponse:
        """Renombra un archivo de la memoria y lo vuelve a indexar con su nombre nuevo.

        Existe para los que fallaron por nombre largo: sin esto había que
        borrarlo, renombrarlo en el PC y volver a subirlo. Solo para archivos
        **sin indexar o fallidos**; uno que ya está en la memoria no se toca,
        que renombrarlo obligaría a rehacer su grafo.

        Si tiene registro de documento (fallido), primero se borra ese
        registro —no el archivo— con el borrado de siempre, que reserva la
        tubería; después se renombra y se encola. Todo en segundo plano: la
        respuesta sale en cuanto está lanzado.
        """
        from lightrag.api.routers.document_routes import (
            DocumentManager,
            _acquire_destructive_busy,
            _release_destructive_busy,
            background_delete_documents,
            pipeline_index_file,
        )
        from lightrag.base import DocStatus
        from lightrag.kg.shared_storage import start_reserved_background_task

        target_rag, entrada, _ = await resolve_rag(nemo)
        entrada = Path(entrada)
        viejo, nuevo = request.name.strip(), request.new_name.strip()

        # Solo el nombre: un «..» o una barra aquí sacarían el archivo de su
        # carpeta.
        if Path(viejo).name != viejo or Path(nuevo).name != nuevo:
            raise HTTPException(status_code=400, detail="Solo el nombre, sin carpetas.")
        origen = entrada / viejo
        if not origen.is_file():
            raise HTTPException(
                status_code=404, detail=f"No está «{viejo}» en esta memoria."
            )
        if nombres.extension(nuevo).lower() != nombres.extension(viejo).lower():
            raise HTTPException(
                status_code=400,
                detail="El nombre nuevo tiene que conservar la extensión "
                f"«{nombres.extension(viejo)}».",
            )
        existentes = frozenset(
            p.name for p in entrada.iterdir() if p.is_file() and p.name != viejo
        )
        fallos = nombres.problemas(
            nuevo,
            nombres.maximo(_raiz_leidos(entrada), nombres.extension(nuevo)),
            existentes,
        )
        if fallos:
            raise HTTPException(status_code=400, detail=" ".join(fallos))

        doc_id: Optional[str] = None
        try:
            registros = await target_rag.doc_status.get_docs_by_statuses(
                list(DocStatus), strict=False
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        for clave, registro in registros.items():
            if Path(str(getattr(registro, "file_path", "") or "")).name == viejo:
                if registro.status != DocStatus.FAILED:
                    raise HTTPException(
                        status_code=409,
                        detail="Solo se pueden renombrar archivos sin indexar o "
                        "que fallaron.",
                    )
                doc_id = clave
                break

        destino = entrada / nuevo

        async def _renombrar_e_indexar() -> None:
            origen.rename(destino)
            logger.info("BIMNEMO: «%s» renombrado a «%s»", viejo, nuevo)
            await pipeline_index_file(target_rag, destino)

        if doc_id is None:

            async def _sin_registro(started):
                started.set()
                await _renombrar_e_indexar()

            async def _nada():
                return None

            await start_reserved_background_task(
                tareas, work=_sin_registro, backstop_release=_nada
            )
            return RenameResponse(status="renaming", message=f"Renombrado a «{nuevo}».")

        token = uuid4().hex
        adquirido, _ = await _acquire_destructive_busy(
            target_rag,
            token,
            kind="delete",
            operation_record={"kind": "delete", "doc_ids": [doc_id]},
        )
        if not adquirido:
            return RenameResponse(
                status="busy",
                message="La memoria está indexando. Renómbralo cuando termine.",
            )
        gestor = DocumentManager(
            str(doc_manager.base_input_dir), getattr(target_rag, "workspace", "") or ""
        )

        async def _con_registro(started):
            started.set()
            # El borrado suelta la reserva en su propio finally.
            await background_delete_documents(
                target_rag, gestor, [doc_id], False, False, token
            )
            if await target_rag.doc_status.get_by_id(doc_id):
                logger.error(
                    "BIMNEMO: no se pudo borrar el registro de «%s»; no se renombra",
                    viejo,
                )
                return
            await _renombrar_e_indexar()

        async def _respaldo():
            await _release_destructive_busy(target_rag, token)

        await start_reserved_background_task(
            tareas, work=_con_registro, backstop_release=_respaldo
        )
        return RenameResponse(
            status="renaming",
            message=f"Renombrando a «{nuevo}» y volviendo a indexarlo.",
        )

    return router


__all__ = ["create_bimnemo_nombres_routes"]
