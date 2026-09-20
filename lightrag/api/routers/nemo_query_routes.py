"""Acceso a cada NEMO y consulta a varias a la vez.

Separado de ``nemo_routes`` porque son cosas distintas: aquél administra las
memorias —crearlas, renombrarlas, borrarlas—, éste las usa. Se montan juntos,
así que desde fuera es una sola superficie.

## Rutas espejo, no firmas cambiadas

``POST /documents/upload`` y ``POST /query`` los usa el WebUI de LightRAG y
cualquier integración anterior. **No se les cambia la firma.** Siguen
apuntando a la NEMO por defecto. Lo nuevo vive en ``/nemo/{nemo}/…`` y nada de
lo que ya funcionaba se entera.

## Buscar en varias es abanico de RECUPERACIÓN

Se pide el contexto a cada memoria en paralelo y se redacta **una sola**
respuesta con todos. Pedir a cada una su propia respuesta y fundirlas después
cuesta N llamadas al modelo redactor y produce respuestas que se contradicen
sin que nadie pueda arbitrar.

El presupuesto de tokens se reparte entre las memorias consultadas: N
contextos enteros no caben en uno.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from lightrag.api.bimnemo.nemo_registry import NemoError, NemoRegistry
from lightrag.base import QueryParam
from lightrag.utils import logger

from ..utils_api import get_combined_auth_dependency, internal_server_error
from .document_routes import get_managed_background_tasks

#: Cabecera que LightRAG ya define para seleccionar workspace. Se respeta tal
#: cual para que una integración escrita contra el motor siga valiendo.
WORKSPACE_HEADER = "LIGHTRAG-WORKSPACE"


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------


class NemoSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: Literal["local", "global", "hybrid", "naive", "mix"] = "mix"
    top_k: Optional[int] = Field(default=None, ge=1, le=500)
    chunk_top_k: Optional[int] = Field(default=None, ge=1, le=200)


class NemoSearchResponse(BaseModel):
    nemo: str
    query: str
    mode: str
    context: str


class NemoRememberRequest(BaseModel):
    text: str = Field(min_length=1)
    source: Optional[str] = None


class NemoAskRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: Literal["local", "global", "hybrid", "naive", "mix"] = "mix"
    top_k: Optional[int] = Field(default=None, ge=1, le=500)


class NemoAskResponse(BaseModel):
    nemo: str
    query: str
    mode: str
    response: str


class MultiSearchRequest(BaseModel):
    """Consulta a varias NEMO a la vez."""

    query: str = Field(min_length=1)
    mode: Literal["local", "global", "hybrid", "naive", "mix"] = "mix"
    nemos: Optional[list[str]] = Field(
        default=None,
        description="Memorias a consultar. Vacío o ausente = todas.",
    )
    top_k: Optional[int] = Field(default=None, ge=1, le=500)
    max_total_tokens: int = Field(
        default=30000,
        ge=2000,
        le=200000,
        description=(
            "Presupuesto TOTAL de contexto, repartido entre las memorias "
            "consultadas. N contextos enteros no caben en uno."
        ),
    )


class MultiSearchResponse(BaseModel):
    query: str
    mode: str
    searched: list[str]
    results: list[dict[str, Any]] = Field(
        description="Un bloque por memoria que aportó algo, con su nombre"
    )
    failures: list[dict[str, Any]] = Field(
        description="Memorias que fallaron; no impiden responder con las demás"
    )


class MultiAskResponse(BaseModel):
    query: str
    mode: str
    searched: list[str]
    consulted: list[dict[str, Any]] = Field(
        description="Memorias que realmente aportaron contexto"
    )
    failures: list[dict[str, Any]]
    response: str
    llm_generated: bool


class SimpleResponse(BaseModel):
    status: str
    nemo: str
    message: str
    track_id: str = Field(
        default="",
        description=(
            "Identificador para seguir el indexado en "
            "/documents/track_status/{track_id}. Vacío cuando la operación no "
            "encola nada."
        ),
    )


# ---------------------------------------------------------------------------
# Factoría
# ---------------------------------------------------------------------------


def create_nemo_query_routes(
    registry: NemoRegistry,
    manager,
    doc_manager,
    api_key: Optional[str] = None,
) -> APIRouter:
    """Router de acceso por NEMO. Sin prefijo: lo aporta quien lo incluye."""
    combined_auth = get_combined_auth_dependency(api_key)
    router = APIRouter(tags=["nemo"])

    def _resolve(requested: str | None) -> str:
        try:
            return registry.resolve(requested)
        except NemoError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # -- Acceso por NEMO ---------------------------------------------------

    @router.post(
        "/nemo/{nemo}/memory/search",
        response_model=NemoSearchResponse,
        dependencies=[Depends(combined_auth)],
        summary="Recuperar contexto de una NEMO concreta, sin generar",
    )
    async def nemo_search(nemo: str, request: NemoSearchRequest) -> NemoSearchResponse:
        """Recuperación sin generación contra la NEMO nombrada en la URL.

        Es lo que quiere un agente que ya tiene su propio modelo: se ahorra la
        llamada al LLM que redacta.
        """
        nemo_id = _resolve(nemo)
        rag = await manager.get(nemo_id)

        param = QueryParam(mode=request.mode, only_need_context=True, stream=False)
        if request.top_k is not None:
            param.top_k = request.top_k
        if request.chunk_top_k is not None:
            param.chunk_top_k = request.chunk_top_k

        try:
            context = await rag.aquery(request.query, param=param)
        except Exception as exc:
            logger.error("BIMNEMO: fallo buscando en la NEMO %r: %s", nemo_id, exc)
            raise internal_server_error(exc)

        return NemoSearchResponse(
            nemo=nemo_id,
            query=request.query,
            mode=request.mode,
            context=context if isinstance(context, str) else "",
        )

    @router.post(
        "/nemo/{nemo}/query",
        response_model=NemoAskResponse,
        dependencies=[Depends(combined_auth)],
        summary="Preguntar a una NEMO concreta y recibir respuesta generada",
    )
    async def nemo_ask(nemo: str, request: NemoAskRequest) -> NemoAskResponse:
        nemo_id = _resolve(nemo)
        rag = await manager.get(nemo_id)

        param = QueryParam(mode=request.mode, stream=False)
        if request.top_k is not None:
            param.top_k = request.top_k

        try:
            answer = await rag.aquery(request.query, param=param)
        except Exception as exc:
            logger.error("BIMNEMO: fallo consultando la NEMO %r: %s", nemo_id, exc)
            raise internal_server_error(exc)

        return NemoAskResponse(
            nemo=nemo_id,
            query=request.query,
            mode=request.mode,
            response=answer if isinstance(answer, str) else "",
        )

    @router.post(
        "/nemo/{nemo}/memory/remember",
        response_model=SimpleResponse,
        dependencies=[Depends(combined_auth)],
        summary="Guardar texto en una NEMO concreta",
    )
    async def nemo_remember(nemo: str, request: NemoRememberRequest) -> SimpleResponse:
        nemo_id = _resolve(nemo)
        rag = await manager.get(nemo_id)
        source = request.source or f"bimnemo://{nemo_id or 'general'}"

        try:
            await rag.ainsert(request.text, file_paths=source)
        except Exception as exc:
            logger.error("BIMNEMO: fallo guardando en la NEMO %r: %s", nemo_id, exc)
            raise internal_server_error(exc)

        return SimpleResponse(
            status="accepted",
            nemo=nemo_id,
            message=(
                "Texto encolado. La extracción corre en segundo plano; sigue su "
                "estado en /documents/pipeline_status."
            ),
        )

    @router.post(
        "/nemo/{nemo}/documents/upload",
        response_model=SimpleResponse,
        dependencies=[Depends(combined_auth)],
        summary="Subir un fichero a una NEMO concreta",
    )
    async def nemo_upload(
        nemo: str,
        request: Request,
        file: UploadFile = File(...),
        managed_tasks: set = Depends(get_managed_background_tasks),
    ) -> SimpleResponse:
        """Guarda el fichero en la carpeta de esa NEMO y lo manda a indexar.

        El fichero se guarda bajo ``<input_dir>/<nemo>/``: cada memoria tiene
        su propia carpeta de entrada, igual que tiene su propio almacén.

        **Hace exactamente lo mismo que ``POST /documents/upload``**, con la
        instancia de esta memoria. Esa ruta ya resuelve lo difícil —elegir el
        parser de cada formato, encolar, llevar la cuenta— y aquí se reutiliza
        en lugar de reinventarlo.

        Antes esta ruta hacía tres cosas mal, y las tres se veían:

        1. Leía el fichero **entero en memoria**; un `.docx` de 50 MB lo
           cargaba de golpe. Ahora se escribe a disco por trozos.
        2. Para texto, llamaba a ``ainsert`` **dentro de la petición**, que no
           respondía hasta terminar de indexar — minutos con el LLM extrayendo
           entidades, con la ventana sin poder hacer nada. Ahora el trabajo va
           en segundo plano y la respuesta es inmediata.
        3. Para un binario **no lo indexaba**: lo dejaba en disco diciendo que
           había que lanzar un escaneo a mano. El `.docx` se quedaba en «Sin
           indexar» para siempre, y como no había nada en la tubería, la barra
           de progreso no tenía nada que enseñar.
        """
        from lightrag.api.routers.document_routes import (
            _adopt_or_new_enqueue_token,
            _release_enqueue_slot,
            pipeline_index_file,
        )
        from lightrag.kg.shared_storage import start_reserved_background_task
        from lightrag.utils import generate_track_id

        nemo_id = _resolve(nemo)
        rag = await manager.get(nemo_id)

        filename = Path(file.filename or "").name
        if not filename:
            raise HTTPException(status_code=400, detail="El fichero no tiene nombre.")

        target_dir = (
            Path(doc_manager.base_input_dir) / nemo_id
            if nemo_id
            else Path(doc_manager.input_dir)
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / filename

        # A disco por trozos, no de una vez: el fichero puede ser grande y no
        # hay motivo para tenerlo entero en memoria.
        try:
            with destination.open("wb") as salida:
                while True:
                    trozo = await file.read(1024 * 1024)
                    if not trozo:
                        break
                    await asyncio.to_thread(salida.write, trozo)
        except OSError as exc:
            logger.error("BIMNEMO: no se pudo guardar %s: %s", destination, exc)
            raise internal_server_error(exc)
        finally:
            await file.close()

        track_id = generate_track_id("upload")
        token, _ = _adopt_or_new_enqueue_token(request)

        async def _indexar(started):
            # `started.set()` va primero y sin ningún await por delante: la
            # barrera de arranque confirma el relevo antes de que la ruta
            # responda, así que una cancelación al enviar el cuerpo no puede
            # dejar el hueco de admisión colgado.
            started.set()
            try:
                await pipeline_index_file(
                    rag, destination, track_id, admission_token=token
                )
            finally:
                await _release_enqueue_slot(rag, token)

        async def _por_si_acaso():
            # Idempotente: solo hace algo si la tarea no llegó a tomar el
            # relevo. Sin esto, un fallo entre reservar y arrancar dejaría a la
            # tubería creyendo que hay una subida pendiente para siempre.
            await _release_enqueue_slot(rag, token)

        try:
            await start_reserved_background_task(
                managed_tasks, work=_indexar, backstop_release=_por_si_acaso
            )
        except Exception as exc:
            await _release_enqueue_slot(rag, token)
            logger.error("BIMNEMO: no se pudo encolar %s: %s", filename, exc)
            raise internal_server_error(exc)

        return SimpleResponse(
            status="success",
            nemo=nemo_id,
            message=f"{filename} subido. Se está indexando en segundo plano.",
            track_id=track_id,
        )

    # -- Consulta a varias NEMO a la vez -----------------------------------

    async def _gather_context(
        nemo_ids: list[str], request: MultiSearchRequest
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Recupera contexto de varias NEMOs a la vez.

        Abanico de **recuperación**, no de generación. La alternativa —pedir a
        cada memoria una respuesta completa y luego fundirlas— cuesta N
        llamadas al modelo que redacta y produce respuestas que se contradicen
        entre sí sin que nadie pueda arbitrar.

        El presupuesto de tokens se reparte entre las memorias consultadas: N
        contextos enteros no caben en uno solo, y dejar que cada una pida el
        máximo haría que la última llegara con el contexto ya lleno.
        """
        if not nemo_ids:
            return [], []

        por_memoria = max(2000, request.max_total_tokens // len(nemo_ids))

        async def _one(nemo_id: str, rag_instance: Any) -> str:
            param = QueryParam(mode=request.mode, only_need_context=True, stream=False)
            param.max_total_tokens = por_memoria
            if request.top_k is not None:
                param.top_k = request.top_k
            resultado = await rag_instance.aquery(request.query, param=param)
            return resultado if isinstance(resultado, str) else ""

        crudos = await manager.map(nemo_ids, _one)

        bloques: list[dict[str, Any]] = []
        fallos: list[dict[str, Any]] = []
        for nemo_id in nemo_ids:
            valor = crudos.get(nemo_id)
            entry = registry.get(nemo_id)
            nombre = entry.name if entry else nemo_id
            if isinstance(valor, BaseException):
                # Una memoria rota no puede dejar sin respuesta a las demás.
                logger.warning(
                    "BIMNEMO: la NEMO %r falló al buscar: %s", nemo_id, valor
                )
                fallos.append({"nemo": nemo_id, "name": nombre, "error": str(valor)})
            elif valor:
                bloques.append({"nemo": nemo_id, "name": nombre, "context": valor})

        return bloques, fallos

    @router.post(
        "/bimnemo/memory/search-all",
        response_model=MultiSearchResponse,
        dependencies=[Depends(combined_auth)],
        summary="Recuperar contexto de varias NEMO a la vez, sin generar",
    )
    async def search_all(request: MultiSearchRequest) -> MultiSearchResponse:
        """Busca en las memorias indicadas —o en todas— y devuelve sus contextos.

        Cada bloque viene etiquetado con su memoria, así que quien reciba esto
        puede citar de dónde sale cada cosa. Es lo que quiere un agente con su
        propio modelo.
        """
        objetivo = request.nemos or [n.id for n in registry.list()]
        try:
            objetivo = [registry.resolve(n) for n in objetivo]
        except NemoError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        bloques, fallos = await _gather_context(objetivo, request)
        return MultiSearchResponse(
            query=request.query,
            mode=request.mode,
            searched=objetivo,
            results=bloques,
            failures=fallos,
        )

    @router.post(
        "/bimnemo/memory/ask-all",
        response_model=MultiAskResponse,
        dependencies=[Depends(combined_auth)],
        summary="Preguntar a varias NEMO a la vez y recibir una sola respuesta",
    )
    async def ask_all(request: MultiSearchRequest) -> MultiAskResponse:
        """Recupera de varias memorias y redacta **una** respuesta con todas.

        Una sola llamada al modelo sobre el contexto ya reunido. El aviso del
        sistema le pide que diga de qué memoria sale cada cosa: con varias
        memorias en juego, «según X» deja de ser un adorno y pasa a ser la
        información más útil de la respuesta.
        """
        objetivo = request.nemos or [n.id for n in registry.list()]
        try:
            objetivo = [registry.resolve(n) for n in objetivo]
        except NemoError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        bloques, fallos = await _gather_context(objetivo, request)

        if not bloques:
            return MultiAskResponse(
                query=request.query,
                mode=request.mode,
                searched=objetivo,
                consulted=[],
                failures=fallos,
                response=(
                    "No he encontrado nada sobre eso en ninguna de las memorias "
                    "consultadas."
                ),
                llm_generated=False,
            )

        contexto = "\n\n".join(
            f"### Memoria: {b['name']}\n{b['context']}" for b in bloques
        )
        system_prompt = (
            "Respondes a partir de varias memorias de conocimiento separadas. "
            "Cada bloque de contexto lleva el nombre de la memoria del que "
            "procede.\n"
            "Reglas:\n"
            "1. Usa SOLO la información de los bloques. Si no está, dilo.\n"
            "2. Indica siempre de qué memoria sale cada dato, por su nombre.\n"
            "3. Si dos memorias se contradicen, dilo explícitamente en lugar "
            "de elegir una.\n"
            "4. Responde en el idioma de la pregunta."
        )
        prompt = f"{contexto}\n\n---\n\nPregunta: {request.query}"

        # Se usa el LLM de la instancia por defecto: la configuración de
        # modelos es común a todas las memorias, así que cualquiera daría el
        # mismo, y la de por defecto siempre está abierta.
        base = await manager.get(registry.default_id)
        try:
            answer = await base.llm_model_func(prompt, system_prompt=system_prompt)
        except Exception as exc:
            logger.error("BIMNEMO: fallo redactando sobre varias NEMO: %s", exc)
            raise internal_server_error(exc)

        return MultiAskResponse(
            query=request.query,
            mode=request.mode,
            searched=objetivo,
            consulted=[{"nemo": b["nemo"], "name": b["name"]} for b in bloques],
            failures=fallos,
            response=answer if isinstance(answer, str) else str(answer),
            llm_generated=True,
        )

    # -- Resolución por cabecera ------------------------------------------

    @router.get(
        "/bimnemo/nemos/resolve",
        dependencies=[Depends(combined_auth)],
        summary="Qué NEMO resolvería esta petición",
    )
    async def resolve_nemo(
        request: Request,
        nemo: Optional[str] = Query(default=None, description="Nombre o identificador"),
    ) -> dict[str, Any]:
        """Diagnóstico: dice a qué memoria iría una petición y por qué.

        Existe porque el fallo típico al integrar es escribir en una memoria
        distinta de la que se cree, y sin esto solo se descubre consultando y
        no encontrando nada.
        """
        header_value = request.headers.get(WORKSPACE_HEADER, "").strip() or None
        requested = nemo or header_value
        nemo_id = _resolve(requested)
        entry = registry.get(nemo_id)
        return {
            "resolved": nemo_id,
            "name": entry.name if entry else None,
            "source": (
                "parámetro" if nemo else ("cabecera" if header_value else "por defecto")
            ),
            "header": WORKSPACE_HEADER,
        }

    return router


__all__ = ["WORKSPACE_HEADER", "create_nemo_query_routes"]
