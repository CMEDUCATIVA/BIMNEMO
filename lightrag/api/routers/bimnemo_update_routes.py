"""Rutas para saber si hay versión nueva y traerla.

Van en su propio módulo porque son otra cosa que el resto: no hablan de la
memoria, hablan del **programa**. Y porque `bimnemo_routes.py` ya andaba cerca
del tope de líneas.

## Por qué el trabajo va en segundo plano

`git fetch` y `pip install` pueden tardar un minuto largo. Esperarlos dentro
de la petición deja al navegador colgado sin saber si sigue vivo — que es
exactamente el fallo que tuvo el borrado hasta que se arregló. Así que la ruta
responde en cuanto lanza el trabajo, y la ventana sigue el progreso con la
misma cortina del reinicio.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from lightrag.api.bimnemo import actualizacion
from lightrag.api.bimnemo.runtime import RESTART_EXIT_CODE
from lightrag.utils import logger

from ..utils_api import get_combined_auth_dependency


class ApplyRequest(BaseModel):
    discard_local_changes: bool = Field(
        default=False,
        description=(
            "Descartar los cambios locales en el código. Sin esto, si los hay, "
            "la actualización se niega en vez de borrarlos."
        ),
    )


class ApplyResponse(BaseModel):
    status: str
    message: str


def create_bimnemo_update_routes(
    rag,
    check_pipeline_busy_or_raise,
    api_key: str | None = None,
) -> APIRouter:
    """Construye el router de actualización.

    ``check_pipeline_busy_or_raise`` se inyecta en vez de reimplementarse: es
    la misma comprobación que usa el reinicio, y dos versiones de «¿está
    ocupado?» acabarían discrepando justo cuando importa.
    """
    combined_auth = get_combined_auth_dependency(api_key)
    router = APIRouter(tags=["bimnemo"])

    @router.get(
        "/update",
        dependencies=[Depends(combined_auth)],
        summary="¿Hay una versión nueva de BIMNEMO publicada?",
    )
    async def update_status(force: bool = False) -> dict[str, Any]:
        """Compara el commit instalado con el último de la rama publicada.

        Se consulta la API pública de GitHub **sin credenciales**: el
        repositorio es público y no guardar un token es mejor que guardarlo
        bien. La respuesta se cachea unos minutos, así que abrir tres ventanas
        no son tres consultas.

        **Si GitHub no contesta, no es un error.** Se devuelve
        ``reachable: false`` y la pantalla lo dice sin alarmar: una aplicación
        de escritorio tiene que funcionar sin red.
        """
        # A un hilo: `urllib` y `git` son bloqueantes, y este endpoint lo llama
        # una pantalla que no puede permitirse bloquear el bucle de eventos.
        return await asyncio.to_thread(actualizacion.estado, force)

    @router.post(
        "/update/apply",
        response_model=ApplyResponse,
        dependencies=[Depends(combined_auth)],
        summary="Traer la versión publicada y reiniciar",
    )
    async def update_apply(request: ApplyRequest = Body(default=ApplyRequest())):
        """Descarga la versión nueva, instala lo que haga falta y reinicia.

        **Se niega si el motor está indexando** (HTTP 409), igual que el
        reinicio: cortar una ingesta a medias deja documentos sin terminar y
        almacenes a medio escribir.

        Responde en cuanto lanza el trabajo. Lo que pasa después —descargar,
        instalar, morir— lo sigue la ventana mirando el ``boot_id``, que es la
        única señal fiable de que el motor ya es otro.
        """
        await check_pipeline_busy_or_raise(rag)

        estado = await asyncio.to_thread(actualizacion.estado, True)
        if not estado.get("supported"):
            raise HTTPException(status_code=400, detail=estado.get("reason", ""))
        if not estado.get("reachable"):
            raise HTTPException(
                status_code=503,
                detail="No se pudo consultar GitHub. Comprueba la conexión.",
            )
        if not estado.get("behind"):
            return ApplyResponse(
                status="up_to_date",
                message="Ya tienes la última versión publicada.",
            )
        if estado.get("dirty") and not request.discard_local_changes:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Hay cambios locales en el código de BIMNEMO. Actualizar "
                    "los borraría; guárdalos o confirma que se descarten."
                ),
            )

        async def _trabajo() -> None:
            resultado = await asyncio.to_thread(
                actualizacion.aplicar, request.discard_local_changes
            )
            if not resultado.get("ok"):
                logger.error(
                    "BIMNEMO: la actualización falló (%s): %s",
                    resultado.get("reason"),
                    resultado.get("message"),
                )
                return

            if resultado.get("dependencies_changed"):
                logger.info("BIMNEMO: cambiaron las dependencias; instalando…")
                ok, salida = await asyncio.to_thread(
                    actualizacion.instalar_dependencias
                )
                if not ok:
                    # Se sigue adelante a propósito: el código ya está en
                    # disco, y arrancar con las dependencias viejas suele
                    # funcionar y deja ver el fallo. Pararse aquí dejaría la
                    # instalación a medias y sin motor.
                    logger.error("BIMNEMO: pip falló: %s", salida)

            logger.info(
                "BIMNEMO: actualizado a %s; reiniciando", resultado.get("installed")
            )
            try:
                await rag.finalize_storages()
            except Exception as exc:  # cerrar mal es peor que no cerrar
                logger.warning("BIMNEMO: fallo al cerrar los almacenes: %s", exc)
            os._exit(RESTART_EXIT_CODE)

        async def _lanzar() -> None:
            # Medio segundo para que la respuesta salga por el socket antes de
            # que empiece el trajín. Mismo motivo que en el reinicio.
            await asyncio.sleep(0.5)
            await _trabajo()

        asyncio.create_task(_lanzar())

        return ApplyResponse(
            status="updating",
            message="Descargando la versión nueva. La ventana volverá sola.",
        )

    return router
