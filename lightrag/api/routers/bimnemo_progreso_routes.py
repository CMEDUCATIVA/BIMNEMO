"""Qué está haciendo la memoria ahora mismo: ``GET /bimnemo/progress``.

Separado de ``bimnemo_documents_routes`` porque responde a otra pregunta
—«¿cómo va?» en vez de «haz esto con este documento»— y porque aquel fichero
rozaba su tope de 600 líneas.

La respuesta trae tres cosas:

* **El estado de la memoria**: cuántos documentos hay por estado y si la
  tubería está ocupada.
* **El avance por documento** (``docs``), que es lo que pinta cada barra.
  Sale de los contadores que el motor publica por documento y fase
  (``lightrag/doc_progress.py``), traducidos por ``bimnemo/avance.py``.
* **Un sello** (``revision``): cambia cuando cambia algo que la pantalla
  enseña, para que la vista sepa si tiene que volver a pedir la lista.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from lightrag.api.bimnemo import avance
from lightrag.base import DocStatus
from lightrag.utils import logger

from ..utils_api import get_combined_auth_dependency

#: Estados que significan «todavía hay trabajo por delante».
EN_MARCHA = (
    DocStatus.PENDING,
    DocStatus.PARSING,
    DocStatus.ANALYZING,
    DocStatus.PROCESSING,
    DocStatus.PREPROCESSED,
)

#: El avance fino dentro de un documento viaja ahora como datos
#: (``doc_progress``). Esta expresión se conserva como red: si el motor
#: dejara de publicarlos, el porcentaje del documento en curso se recupera
#: del mensaje de texto, que es lo que había antes.
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
    docs: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Avance por documento en marcha: doc_id, fase, hechos, total, la "
            "etiqueta que se enseña y su porcentaje (nulo si esa fase no sabe "
            "cuánto queda)"
        ),
    )
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


def sello(entrada: Path, por_estado: dict[str, int], total: int) -> str:
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


def create_bimnemo_progreso_routes(
    resolve_rag, api_key: Optional[str] = None
) -> APIRouter:
    """Sin prefijo propio: se monta dentro del router de BIMNEMO."""
    combined_auth = get_combined_auth_dependency(api_key)
    router = APIRouter(tags=["bimnemo"])

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
        """Estado de la tubería y avance de cada documento de **esta** memoria.

        El porcentaje general sale de documentos terminados sobre el total, no
        del lote: el lote es una unidad interna del motor y no le dice nada a
        quien mira la pantalla. El de cada documento sale de sus fases.

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
        activos: dict[str, str] = {}
        en_marcha = {s.value for s in EN_MARCHA}
        for doc_id, registro in documentos.items():
            clave = getattr(registro.status, "value", str(registro.status))
            por_estado[clave] = por_estado.get(clave, 0) + 1
            if clave in en_marcha:
                activos[doc_id] = clave

        working = sum(por_estado.get(s.value, 0) for s in EN_MARCHA)
        done = por_estado.get(DocStatus.PROCESSED.value, 0)
        failed = por_estado.get(DocStatus.FAILED.value, 0)
        total = len(documentos)
        busy = bool(tuberia.get("busy", False))
        mensaje = str(tuberia.get("latest_message") or "")

        filas = avance.filas(tuberia, activos)

        # Red por si el motor dejara de publicar contadores: el avance del
        # documento en curso, sacado del mensaje de texto como se hacía antes.
        fragmento = FRAGMENTO_RE.search(mensaje)
        chunk_done = int(fragmento.group(1)) if fragmento else 0
        chunk_total = int(fragmento.group(2)) if fragmento else 0

        avance_docs = float(done + failed)
        if busy and chunk_total > 0:
            avance_docs += min(chunk_done, chunk_total) / chunk_total
        percent = min(100, round((avance_docs / total) * 100)) if total else 0

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
            docs=filas,
            revision=sello(Path(entrada), por_estado, total),
            total=total,
            percent=percent,
            stalled=working > 0 and not busy,
        )

    return router


__all__ = ["EN_MARCHA", "ProgressResponse", "create_bimnemo_progreso_routes", "sello"]
