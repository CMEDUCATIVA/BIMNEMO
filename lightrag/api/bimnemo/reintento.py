"""Reintentar **un** documento fallido, no todos los de la memoria.

El reintento que trae LightRAG es por memoria: su fase EXCLUSIVE_RESET pasa
a PENDING **todos** los FAILED (``pipeline._run_exclusive_failed_reset``). En
la ventana el botón está en una fila, y una fila se lee «este documento».

Aquí se hace lo mismo que ese reinicio, pero para un solo ``doc_id``:

1. se reserva el hueco exclusivo de la tubería —el mismo que usa el
   borrado—, porque escribir ``doc_status`` con la tubería trabajando es
   pisarle el trabajo;
2. se pasa ese documento a PENDING con ``_build_pending_reset_update``, la
   función que usa el propio reinicio de LightRAG (no se reescribe);
3. se suelta la reserva y se lanza la tubería. Su barrido automático recoge
   PENDING y **nunca** FAILED (``_AUTO_RESUME_DOC_STATUSES``), así que los
   demás fallidos se quedan donde estaban.
"""

from __future__ import annotations

from uuid import uuid4

from lightrag.base import DocStatus
from lightrag.utils import logger

#: Lo que se contesta cuando la tubería está ocupada. El motivo que da
#: LightRAG viene en inglés y habla de «clearing or deleting».
OCUPADA = (
    "La memoria está indexando o revisando documentos. Reintenta este cuando termine."
)


async def reintentar_uno(target_rag, doc_id: str, managed_tasks: set) -> dict:
    """Vuelve a encolar ``doc_id`` y solo ese. Devuelve ``{status, message}``.

    ``status``: ``queued`` (en cola), ``busy`` (ahora no), ``nothing`` (no
    hay nada que reintentar en ese documento).
    """
    from lightrag.api.routers.document_routes import (
        _acquire_destructive_busy,
        _release_destructive_busy,
    )
    from lightrag.kg.shared_storage import start_reserved_background_task
    from lightrag.utils_pipeline import doc_status_custom_chunk_patch

    token = uuid4().hex
    adquirido, _motivo = await _acquire_destructive_busy(
        target_rag,
        token,
        kind="retry",
        operation_record={"kind": "retry", "doc_ids": [doc_id]},
    )
    if not adquirido:
        return {"status": "busy", "message": OCUPADA}

    try:
        registros = await target_rag.doc_status.get_full_docs_by_ids(
            [doc_id], strict=True
        )
        registro = registros.get(doc_id)
        # `DocStatus` es un enum de texto: compara igual con el miembro o con
        # la cadena cruda, que es como lo guardan algunos almacenes.
        if registro is None or getattr(registro, "status", None) != DocStatus.FAILED:
            return {
                "status": "nothing",
                "message": "Este documento ya no está fallido; no hay nada que reintentar.",
            }
        if doc_status_custom_chunk_patch(registro) is not None:
            # Una operación a medias es dueña de este documento; reiniciarlo
            # le quitaría el ancla con la que se recupera.
            return {
                "status": "nothing",
                "message": "Este documento tiene una operación a medias; espera a que termine.",
            }

        contenido = await target_rag.full_docs.get_by_id(doc_id)
        if not contenido:
            # Sin contenido volvería a fallar igual: lo único útil es volver
            # a subirlo.
            return {
                "status": "nothing",
                "message": (
                    "No queda el texto de este documento en la memoria. "
                    "Bórralo y vuelve a subirlo."
                ),
            }

        cambio, _, _ = target_rag._build_pending_reset_update(registro, contenido)
        await target_rag.doc_status.upsert({doc_id: cambio})
    finally:
        await _release_destructive_busy(target_rag, token)

    async def _indexar(started):
        started.set()
        await target_rag.apipeline_process_enqueue_documents()

    async def _sin_respaldo():
        return None

    try:
        await start_reserved_background_task(
            managed_tasks, work=_indexar, backstop_release=_sin_respaldo
        )
    except Exception as exc:
        # El documento ya está en PENDING: el próximo barrido lo recogerá
        # aunque este arranque haya fallado.
        logger.error("BIMNEMO: no se pudo lanzar la tubería tras reintentar: %s", exc)

    return {"status": "queued", "message": "El documento vuelve a la cola."}
