"""Qué puedes hacer con un documento: borrarlo, reintentarlo, pausarlo.

Separado de ``bimnemo_routes`` porque responde a otra pregunta: aquel dice
**qué hay guardado**, este ofrece las **acciones** sobre un documento
concreto. El «¿cómo va?» vive en ``bimnemo_progreso_routes``.

## Por qué no se usan los endpoints que ya trae LightRAG

``/documents/pipeline_status``, ``/documents/delete_document`` y
``/documents/reprocess_failed`` funcionan, pero **miran la memoria base**: el
estado de la tubería se guarda por workspace y esos endpoints resuelven
siempre con la instancia por defecto del servidor. Con varias NEMO enseñarían
—y borrarían— en la memoria equivocada.

Es la misma ceguera que ya se corrigió en ``/graphs`` y en
``/bimnemo/stats/graph``. Aquí se repite la forma: resolver la NEMO y
**reutilizar** el trabajo pesado que ya existe, no reescribirlo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from lightrag.base import DocStatus
from lightrag.utils import logger

from ..utils_api import get_combined_auth_dependency, internal_server_error
from lightrag.kg.shared_storage import append_pipeline_history

from .document_routes import get_managed_background_tasks


class DeleteDocsRequest(BaseModel):
    doc_ids: list[str] = Field(description="Identificadores de documento a borrar")
    delete_file: bool = Field(
        default=True, description="Borrar también el fichero del directorio de entrada"
    )


class ActionResponse(BaseModel):
    status: str
    message: str


def create_bimnemo_documents_routes(
    doc_manager,
    resolve_rag,
    api_key: Optional[str] = None,
) -> APIRouter:
    """Construye el router de acciones sobre documentos.

    ``resolve_rag`` se **inyecta** desde el router padre en lugar de
    reimplementarla: una segunda versión de esa resolución acabaría
    discrepando de la primera, y entonces una pantalla borraría en una memoria
    distinta de la que está enseñando.
    """
    combined_auth = get_combined_auth_dependency(api_key)
    router = APIRouter(tags=["bimnemo"])

    async def _rag_de(nemo: Optional[str]):
        target_rag, _, _ = await resolve_rag(nemo)
        return target_rag

    # -- Borrado -----------------------------------------------------------

    @router.delete(
        "/documents",
        response_model=ActionResponse,
        dependencies=[Depends(combined_auth)],
        summary="Borrar documentos de una NEMO, con su índice y su fichero",
    )
    async def delete_documents(
        nemo: Optional[str] = Query(
            default=None, description="NEMO donde borrar; por defecto, la activa"
        ),
        request: DeleteDocsRequest = Body(...),
        managed_tasks: set = Depends(get_managed_background_tasks),
    ) -> ActionResponse:
        """Borra documentos de **esta** memoria y todo lo que arrastran.

        Se apoya en ``background_delete_documents``, que es lo que usa la API
        pública: reserva el hueco destructivo de la tubería, quita los
        fragmentos, rehace el grafo y borra el fichero. Reimplementarlo aquí
        sería la forma más rápida de dejar una memoria a medio borrar.

        **Responde en cuanto el trabajo está lanzado, no cuando termina.**
        Purgar los fragmentos de un documento y rehacer el grafo lleva
        segundos; esperarlos dentro de la petición dejaba la pantalla mirando
        cifras viejas sin saber por qué. El hueco destructivo se reserva
        **antes** de responder —si no, una subida podría colarse entre la
        respuesta y el trabajo— y la tarea lo suelta en su propio ``finally``.

        El ``DocumentManager`` se construye apuntando a la carpeta de la NEMO,
        que es donde de verdad está su fichero.
        """
        # Los cuatro viven en `document_routes`: es el módulo que implementa el
        # borrado de la API pública, y aquí se reutiliza tal cual.
        from lightrag.api.routers.document_routes import (
            DocumentManager,
            _acquire_destructive_busy,
            _release_destructive_busy,
            background_delete_documents,
        )
        from lightrag.kg.shared_storage import start_reserved_background_task

        if not request.doc_ids:
            raise HTTPException(status_code=400, detail="No hay documentos que borrar.")

        target_rag = await _rag_de(nemo)
        gestor = DocumentManager(
            str(doc_manager.base_input_dir), getattr(target_rag, "workspace", "") or ""
        )

        token = uuid4().hex
        adquirido, motivo = await _acquire_destructive_busy(
            target_rag,
            token,
            kind="delete",
            operation_record={"kind": "delete", "doc_ids": request.doc_ids},
        )
        if not adquirido:
            # Ocupado no es un error: es «ahora no, que estoy indexando».
            return ActionResponse(
                status="busy",
                message=motivo or "La memoria está ocupada; inténtalo al terminar.",
            )

        async def _trabajo(started):
            # `started.set()` va primero y sin ningún await por delante: la
            # barrera confirma el relevo antes de que la ruta responda, así
            # que cancelar el envío de la respuesta no puede dejar la reserva
            # huérfana. `background_delete_documents` suelta el hueco en su
            # propio finally, comprobando el dueño por `token`.
            started.set()
            await background_delete_documents(
                target_rag,
                gestor,
                request.doc_ids,
                request.delete_file,
                True,
                token,
            )

        async def _respaldo():
            # Solo actúa si la tarea nunca llegó a tomar el relevo. Comprueba
            # el dueño y es idempotente, así que llamarlo de más no hace daño.
            await _release_destructive_busy(target_rag, token)

        try:
            await start_reserved_background_task(
                managed_tasks, work=_trabajo, backstop_release=_respaldo
            )
        except Exception as exc:
            logger.error("BIMNEMO: no se pudo lanzar el borrado: %s", exc)
            await _release_destructive_busy(target_rag, token)
            raise internal_server_error(exc)

        return ActionResponse(
            status="deleting",
            message=f"Borrando {len(request.doc_ids)} documento(s) de la memoria.",
        )

    # -- Reintento ---------------------------------------------------------

    @router.post(
        "/documents/retry",
        response_model=ActionResponse,
        dependencies=[Depends(combined_auth)],
        summary="Reintentar un documento fallido, o todos los de una NEMO",
    )
    async def retry_failed(
        nemo: Optional[str] = Query(
            default=None, description="NEMO a reintentar; por defecto, la activa"
        ),
        doc_id: Optional[str] = Query(
            default=None,
            description="Solo este documento; sin él, todos los fallidos de la NEMO",
        ),
        managed_tasks: set = Depends(get_managed_background_tasks),
    ) -> ActionResponse:
        """Vuelve a encolar lo que falló **en esta memoria**.

        Un fallo de indexado casi nunca es culpa del documento: es la clave,
        el crédito de la cuenta o el modelo. Cuando eso se arregla, hay que
        poder reintentar sin volver a subir nada.

        Sigue **el mismo camino** que ``/documents/reprocess_failed``: publica
        una petición de reintento en el ingreso del workspace y deja que la
        tubería la recoja. No se reencola documento a documento —
        ``apipeline_process_enqueue_documents`` ni siquiera acepta una lista —
        y saltarse el ingreso se llevaría por delante el vallado que protege
        de un borrado simultáneo.

        Con ``doc_id`` se reintenta **solo ese documento**: es lo que pide el
        botón de una fila (``bimnemo/reintento.py``).
        """
        if doc_id:
            from ..bimnemo import espera
            from ..bimnemo.reintento import reintentar_uno

            try:
                target_rag = await _rag_de(nemo)
                resultado = await reintentar_uno(target_rag, doc_id, managed_tasks)
            except HTTPException:
                raise
            except Exception as exc:
                logger.error("BIMNEMO: fallo al reintentar %s: %s", doc_id, exc)
                raise internal_server_error(exc)
            if resultado["status"] != "busy":
                return ActionResponse(**resultado)

            # Con otro documento indexándose no se niega: se apunta y se hace
            # en cuanto la memoria quede libre (bimnemo/espera.py).
            registro = await target_rag.doc_status.get_by_id(doc_id) or {}
            nombre = Path(str(registro.get("file_path") or doc_id)).name

            async def intento() -> bool:
                hecho = await reintentar_uno(target_rag, doc_id, managed_tasks)
                return hecho["status"] != "busy"

            espera.apuntar(managed_tasks, target_rag.workspace, nombre, intento)
            return ActionResponse(
                status="waiting",
                message=(
                    "En espera: se volverá a leer en cuanto termine lo que se "
                    "está indexando."
                ),
            )

        from lightrag.exceptions import PipelineNotInitializedError
        from lightrag.kg.shared_storage import (
            ManualIntentRefused,
            commit_manual_retry_request,
            get_namespace_data,
            get_namespace_lock,
            get_pipeline_ingress,
            start_committed_background_task,
        )

        target_rag = await _rag_de(nemo)
        request_id = uuid4().hex

        try:
            fallidos = await target_rag.doc_status.get_docs_by_statuses(
                [DocStatus.FAILED], strict=False
            )
        except Exception as exc:
            logger.error("BIMNEMO: no se pudo listar lo fallido: %s", exc)
            raise internal_server_error(exc)

        if not fallidos:
            return ActionResponse(
                status="nothing", message="No hay documentos fallidos que reintentar."
            )

        try:
            pipeline_status = await get_namespace_data(
                "pipeline_status", workspace=target_rag.workspace
            )
        except PipelineNotInitializedError:
            pipeline_status = None

        async def _work():
            await target_rag.apipeline_process_enqueue_documents()

        async def _sin_backstop():
            return None

        if pipeline_status is None:
            # Sin tubería arrancada no hay vallado ni ingreso donde publicar.
            from lightrag.kg.shared_storage import start_reserved_background_task

            async def _directo(started):
                started.set()
                await _work()

            await start_reserved_background_task(
                managed_tasks, work=_directo, backstop_release=_sin_backstop
            )
            return ActionResponse(
                status="queued",
                message=f"{len(fallidos)} documento(s) vuelven a la cola.",
            )

        bloqueo = get_namespace_lock("pipeline_status", workspace=target_rag.workspace)
        ingreso = await get_pipeline_ingress(target_rag.workspace)

        async def _commit(state):
            return await commit_manual_retry_request(
                pipeline_status, bloqueo, ingreso, request_id, state
            )

        try:
            await start_committed_background_task(
                managed_tasks,
                commit=_commit,
                work=_work,
                backstop_release=_sin_backstop,
            )
        except ManualIntentRefused as rechazo:
            # Lleno = reintentar más tarde (429); vallado o id ya cerrado = 503.
            raise HTTPException(
                status_code=429 if rechazo.capacity_exceeded else 503,
                detail=str(rechazo),
            ) from rechazo
        except Exception as exc:
            logger.error("BIMNEMO: fallo al reencolar: %s", exc)
            raise internal_server_error(exc)

        return ActionResponse(
            status="queued",
            message=(
                f"{len(fallidos)} documento(s) vuelven a la cola. Si la memoria "
                "está indexando, entrarán en cuanto termine."
            ),
        )

    # -- Pausa -------------------------------------------------------------

    @router.post(
        "/documents/pause",
        response_model=ActionResponse,
        dependencies=[Depends(combined_auth)],
        summary="Pausar la indexación de una NEMO",
    )
    async def pause_indexing(
        nemo: Optional[str] = Query(
            default=None, description="NEMO a pausar; por defecto, la activa"
        ),
    ) -> ActionResponse:
        """Detiene la indexación **de esta memoria**; se reanuda con Reintentar.

        Hace lo mismo que ``/documents/cancel_pipeline`` —levantar
        ``cancellation_requested`` y dejar que la tubería pare en su
        siguiente punto seguro—, pero en el ``pipeline_status`` de la NEMO
        pedida: la oficial solo mira la memoria por defecto, y con varias no
        había forma de parar las demás.

        Lo que estaba en curso queda FAILED con «User cancelled…», que la
        pantalla enseña como «En pausa». Reanudar no vuelve a pagar lo ya
        extraído mientras no se cambie de modelo: la caché de extracción
        guarda cada fragmento.
        """
        from lightrag.exceptions import PipelineNotInitializedError
        from lightrag.kg.shared_storage import get_namespace_data, get_namespace_lock

        target_rag = await _rag_de(nemo)
        try:
            estado = await get_namespace_data(
                "pipeline_status", workspace=target_rag.workspace
            )
        except PipelineNotInitializedError:
            estado = None
        if estado is None:
            return ActionResponse(
                status="not_busy", message="Esta memoria no está indexando nada."
            )

        bloqueo = get_namespace_lock("pipeline_status", workspace=target_rag.workspace)
        async with bloqueo:
            if not estado.get("busy", False):
                return ActionResponse(
                    status="not_busy", message="Esta memoria no está indexando nada."
                )
            aviso = "Pipeline cancellation requested by user"
            estado.update({"cancellation_requested": True, "latest_message": aviso})
            append_pipeline_history(estado, aviso)

        logger.info("BIMNEMO: pausa pedida en la memoria %r", target_rag.workspace)
        return ActionResponse(
            status="pausing",
            message=(
                "Pausando: termina el fragmento en curso y se detiene. Pulsa ⟳ "
                "en la fila para seguir; lo ya extraído no se vuelve a pagar si "
                "no cambias de modelo."
            ),
        )

    # -- Borrado de un fichero sin indexar ---------------------------------

    @router.delete(
        "/files",
        response_model=ActionResponse,
        dependencies=[Depends(combined_auth)],
        summary="Borrar un fichero que todavía no está indexado",
    )
    async def delete_file(
        name: str = Query(description="Nombre del fichero, sin ruta"),
        nemo: Optional[str] = Query(
            default=None, description="NEMO donde está; por defecto, la activa"
        ),
    ) -> ActionResponse:
        """Quita del disco un fichero subido pero aún no indexado.

        Existe porque el borrado de documentos trabaja por ``doc_id``, y un
        fichero que todavía no ha pasado por la tubería no tiene ninguno. Sin
        esto, la papelera de esas filas no podría hacer nada.
        """
        _, entrada, _ = await resolve_rag(nemo)

        # Solo el nombre: un ``..`` aquí permitiría borrar fuera de la carpeta
        # de la memoria.
        limpio = Path(name).name
        if not limpio or limpio != name:
            raise HTTPException(status_code=400, detail="Nombre de fichero no válido.")

        objetivo = Path(entrada) / limpio
        if not objetivo.is_file():
            raise HTTPException(status_code=404, detail=f"No existe {limpio}.")

        try:
            objetivo.unlink()
        except OSError as exc:
            logger.error("BIMNEMO: no se pudo borrar %s: %s", objetivo, exc)
            raise internal_server_error(exc)

        return ActionResponse(status="deleted", message=f"{limpio} borrado.")

    return router


__all__ = ["create_bimnemo_documents_routes"]
