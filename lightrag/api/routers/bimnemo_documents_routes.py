"""Qué está pasando con lo que subes, y qué puedes hacer con ello.

Separado de ``bimnemo_routes`` porque responde a otra pregunta: aquel dice
**qué hay guardado**, este dice **qué está ocurriendo ahora** y ofrece las
acciones sobre un documento concreto.

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

import hashlib
import re
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from lightrag.base import DocStatus
from lightrag.utils import logger

from ..utils_api import get_combined_auth_dependency, internal_server_error
from .document_routes import get_managed_background_tasks

#: Estados que significan «todavía hay trabajo por delante».
EN_MARCHA = (
    DocStatus.PENDING,
    DocStatus.PARSING,
    DocStatus.ANALYZING,
    DocStatus.PROCESSING,
    DocStatus.PREPROCESSED,
)

#: Estados que significan «ya no se va a mover».
TERMINADOS = (DocStatus.PROCESSED, DocStatus.FAILED)

#: El avance fino dentro de un documento solo viaja como TEXTO.
#:
#: El motor lo escribe en ``latest_message`` (``operate.py:4495``) con esta
#: forma: «Chunk 3 of 7 extracted 53 Ent + 40 Rel doc-...». No hay campos
#: numéricos equivalentes en ``pipeline_status``.
#:
#: Leerlo de ahí es frágil —es un mensaje en inglés que puede cambiar— y por
#: eso se hace **aquí y en un solo sitio**: si el patrón deja de encajar, el
#: porcentaje vuelve al cálculo por documentos, que es peor pero nunca está
#: roto.
FRAGMENTO_RE = re.compile(r"Chunk (\d+) of (\d+)", re.IGNORECASE)


class ProgressResponse(BaseModel):
    """Lo que hace falta para pintar una barra honesta."""

    busy: bool = Field(description="La tubería de esta NEMO está trabajando")
    job_name: str = Field(default="", description="Qué trabajo corre ahora")
    latest_message: str = Field(default="", description="Último paso del motor")
    cur_batch: int = Field(default=0, description="Lote en curso")
    batchs: int = Field(default=0, description="Lotes del trabajo")
    by_status: dict[str, int] = Field(
        default_factory=dict, description="Documentos por estado"
    )
    working: int = Field(default=0, description="Documentos aún sin terminar")
    done: int = Field(default=0, description="Documentos indexados")
    failed: int = Field(default=0, description="Documentos que fallaron")
    total: int = Field(default=0, description="Documentos que conoce la memoria")
    percent: int = Field(default=0, description="Terminados sobre el total, 0-100")
    chunk_done: int = Field(default=0, description="Fragmento en curso")
    chunk_total: int = Field(default=0, description="Fragmentos del documento")
    revision: str = Field(
        default="",
        description=(
            "Sello del estado de esta memoria. Cambia cuando cambia algo que "
            "la pantalla enseña; la vista lo compara para saber si refrescar."
        ),
    )
    stalled: bool = Field(
        default=False,
        description=(
            "Hay documentos esperando y la tubería NO está trabajando: "
            "o acaba de encolarse, o se quedó parado"
        ),
    )


class DeleteDocsRequest(BaseModel):
    doc_ids: list[str] = Field(description="Identificadores de documento a borrar")
    delete_file: bool = Field(
        default=True, description="Borrar también el fichero del directorio de entrada"
    )


class ActionResponse(BaseModel):
    status: str
    message: str


def _sello(entrada: Path, por_estado: dict[str, int], total: int) -> str:
    """Resumen corto de lo que la pantalla enseña de esta memoria.

    Existe para que la vista sepa **si tiene que refrescar** sin volver a
    pedir todos los datos. Cambia cuando cambia algo visible: un fichero que
    entra o sale, uno que cambia de peso, un documento que pasa de estado.

    Se mira solo el primer nivel del directorio y sin leer nada: nombre,
    tamaño y fecha de cada entrada. Es una llamada que se repite cada pocos
    segundos, así que no puede permitirse recorrer el árbol entero.
    """
    resumen = hashlib.sha256()
    try:
        for hijo in sorted(entrada.iterdir(), key=lambda x: x.name):
            if not hijo.is_file():
                continue
            st = hijo.stat()
            resumen.update(f"{hijo.name}:{st.st_size}:{st.st_mtime_ns};".encode())
    except OSError:
        # Un directorio que no se puede leer no debe tumbar el sondeo: se
        # queda con lo que sabe del estado de los documentos.
        resumen.update(b"sin-directorio;")

    for clave in sorted(por_estado):
        resumen.update(f"{clave}={por_estado[clave]};".encode())
    resumen.update(str(total).encode())
    return resumen.hexdigest()[:16]


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

    # -- Progreso ----------------------------------------------------------

    @router.get(
        "/progress",
        response_model=ProgressResponse,
        dependencies=[Depends(combined_auth)],
        summary="Qué está indexando ahora mismo esta NEMO",
    )
    async def get_progress(
        nemo: Optional[str] = Query(
            default=None, description="NEMO a observar; por defecto, la activa"
        ),
    ) -> ProgressResponse:
        """Estado de la tubería y recuento de documentos de **esta** memoria.

        El porcentaje sale de documentos terminados sobre el total, no del
        lote: el lote es una unidad interna del motor y no le dice nada a
        quien mira la pantalla.

        ``stalled`` existe por la pregunta que hizo el usuario —«¿está
        bloqueado?»—: hay documentos esperando y nadie trabajando. No siempre
        es un problema (acaban de encolarse), pero es justo lo que hay que
        poder ver.
        """
        from lightrag.kg.shared_storage import get_namespace_data

        target_rag, entrada, _ = await resolve_rag(nemo)

        try:
            estado = await get_namespace_data(
                "pipeline_status", workspace=target_rag.workspace
            )
            tuberia = dict(estado)
        except Exception as exc:  # el panel informa, no revienta
            logger.warning("BIMNEMO: no se pudo leer la tubería: %s", exc)
            tuberia = {}

        try:
            documentos = await target_rag.doc_status.get_docs_by_statuses(
                list(DocStatus), strict=False
            )
        except Exception as exc:
            logger.warning("BIMNEMO: doc_status ilegible al medir progreso: %s", exc)
            documentos = {}

        por_estado: dict[str, int] = {}
        for registro in documentos.values():
            clave = getattr(registro.status, "value", str(registro.status))
            por_estado[clave] = por_estado.get(clave, 0) + 1

        working = sum(por_estado.get(s.value, 0) for s in EN_MARCHA)
        done = por_estado.get(DocStatus.PROCESSED.value, 0)
        failed = por_estado.get(DocStatus.FAILED.value, 0)
        total = len(documentos)
        busy = bool(tuberia.get("busy", False))
        mensaje = str(tuberia.get("latest_message") or "")

        # Avance DENTRO del documento en curso. Sin esto, con un solo documento
        # la barra solo puede valer 0 % o 100 %: no hay nada entre medias, y
        # justo ahí es donde el usuario se queda mirando sin saber si avanza.
        fragmento = FRAGMENTO_RE.search(mensaje)
        chunk_done = int(fragmento.group(1)) if fragmento else 0
        chunk_total = int(fragmento.group(2)) if fragmento else 0

        avance = float(done + failed)
        if busy and chunk_total > 0:
            avance += min(chunk_done, chunk_total) / chunk_total
        percent = min(100, round((avance / total) * 100)) if total else 0

        return ProgressResponse(
            busy=busy,
            job_name=str(tuberia.get("job_name") or ""),
            latest_message=mensaje,
            cur_batch=int(tuberia.get("cur_batch") or 0),
            batchs=int(tuberia.get("batchs") or 0),
            by_status=por_estado,
            working=working,
            done=done,
            failed=failed,
            chunk_done=chunk_done,
            chunk_total=chunk_total,
            revision=_sello(entrada, por_estado, total),
            total=total,
            percent=percent,
            stalled=working > 0 and not busy,
        )

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
        summary="Reintentar los documentos fallidos de una NEMO",
    )
    async def retry_failed(
        nemo: Optional[str] = Query(
            default=None, description="NEMO a reintentar; por defecto, la activa"
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
        """
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
