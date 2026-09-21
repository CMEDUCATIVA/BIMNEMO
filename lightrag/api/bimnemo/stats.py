"""Agregación de las métricas que enseña el panel de BIMNEMO.

Dos fuentes distintas, y el panel no las mezcla nunca:

* **Almacenamiento** — un recorrido del directorio de entrada del
  ``DocumentManager``. Da bytes reales en disco (``st_size``). Es lo que
  responde a «total almacenado».
* **Memoria** — los registros de ``doc_status`` del motor. Dan qué documentos
  conoce LightRAG, en qué estado están, cuántos fragmentos produjeron y cuántos
  caracteres de texto se extrajeron.

Confundirlas produce un número sin significado: ``content_length`` son
caracteres del texto extraído, no bytes del fichero. Un PDF de 40 MB puede dar
30.000 caracteres, y un .txt de 50 KB puede dar más.

Los contadores del grafo viven aparte (:func:`graph_counts`) y con tope, porque
recorrer el grafo entero es caro y el panel no debe quedarse colgado de él.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from lightrag.api.bimnemo.catalog import (
    CATEGORIES,
    UNKNOWN,
    categorize,
    file_type_label,
)
from lightrag.base import DocStatus
from lightrag.exceptions import StorageCapabilityError
from lightrag.utils import logger

# Tope por defecto del recuento del grafo. Por encima, la respuesta se marca
# como truncada y el panel lo dice: un número redondeado y honesto vale más que
# una cifra exacta que tarda un minuto en llegar.
DEFAULT_GRAPH_COUNT_CAP = 200_000

# Tamaño de lote de la iteración acotada del grafo.
GRAPH_ITER_BATCH = 1_000

# Recorrer el directorio de entrada es E/S bloqueante; se hace en un hilo para
# no parar el bucle de eventos mientras el servidor atiende otras peticiones.
_SCAN_TIMEOUT_SECONDS = 30.0


@dataclass
class StoredFile:
    """Un fichero encontrado en el directorio de entrada."""

    name: str
    relative_path: str
    size_bytes: int
    modified_at: float
    category_key: str
    type_label: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.relative_path,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "category": self.category_key,
            "type": self.type_label,
        }


@dataclass
class StorageSnapshot:
    """Resultado de recorrer el directorio de entrada."""

    files: list[StoredFile] = field(default_factory=list)
    unreadable: int = 0
    scan_error: str | None = None

    @property
    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)


def _scan_input_dir_blocking(
    input_dir: Path, exclude: frozenset[str] = frozenset()
) -> StorageSnapshot:
    """Recorre el directorio de entrada. Bloqueante: llamar vía hilo.

    ``exclude`` son nombres de subcarpeta de primer nivel que NO se cuentan.
    Existe por las NEMOs: la memoria base usa la raíz de ``inputs/``, y las
    demás viven en subcarpetas suyas. Sin excluirlas, la base contaría los
    archivos de todas y el panel sumaría lo mismo dos veces.
    """
    snapshot = StorageSnapshot()
    if not input_dir.exists():
        # Directorio aún sin crear no es un error: es «todavía no hay nada».
        return snapshot

    for path in input_dir.rglob("*"):
        if exclude:
            try:
                first = path.relative_to(input_dir).parts[0]
            except (ValueError, IndexError):  # pragma: no cover
                first = ""
            if first in exclude:
                continue
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except OSError:
            # Un fichero puede desaparecer entre el listado y el stat, o estar
            # bloqueado por otro proceso. Se cuenta y se sigue: un panel que
            # falla entero por un fichero es peor que uno que informa de él.
            snapshot.unreadable += 1
            continue

        category = categorize(path.name)
        try:
            relative = path.relative_to(input_dir).as_posix()
        except ValueError:  # pragma: no cover - rglob siempre da descendientes
            relative = path.name

        snapshot.files.append(
            StoredFile(
                name=path.name,
                relative_path=relative,
                size_bytes=stat.st_size,
                modified_at=stat.st_mtime,
                category_key=category.key,
                type_label=file_type_label(path.name),
            )
        )

    return snapshot


async def scan_storage(
    input_dir: Path, exclude: frozenset[str] = frozenset()
) -> StorageSnapshot:
    """Recorre el directorio de entrada sin bloquear el bucle de eventos.

    Un directorio enorme o un disco de red lento no deben dejar el servidor sin
    atender: pasado el plazo se devuelve un resultado vacío con ``scan_error``,
    y el panel enseña el aviso en lugar de una cifra inventada.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_scan_input_dir_blocking, input_dir, exclude),
            timeout=_SCAN_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "BIMNEMO: el recorrido de %s superó %.0f s; se informa sin datos "
            "de almacenamiento",
            input_dir,
            _SCAN_TIMEOUT_SECONDS,
        )
        return StorageSnapshot(
            scan_error=f"El recorrido del directorio superó {_SCAN_TIMEOUT_SECONDS:.0f} s"
        )
    except OSError as exc:
        logger.warning("BIMNEMO: no se pudo recorrer %s: %s", input_dir, exc)
        return StorageSnapshot(scan_error=str(exc))


def summarize_storage(snapshot: StorageSnapshot) -> dict[str, Any]:
    """Totales y reparto por categoría y por tipo, listos para el panel.

    Todas las categorías del catálogo aparecen SIEMPRE, también con cero
    ficheros: el panel enseña «N / <cuántas hay>» y necesita todas sus
    ranuras para pintar las que están vacías. ``other`` solo aparece si de verdad hay algo sin
    clasificar, y nunca cuenta como categoría en uso.
    """
    by_category: dict[str, dict[str, Any]] = {
        category.key: {
            "key": category.key,
            "label": category.label,
            "icon": category.icon,
            "color": category.color,
            "files": 0,
            "size_bytes": 0,
        }
        for category in CATEGORIES
    }

    by_type: dict[str, dict[str, Any]] = {}
    total_bytes = 0

    for stored in snapshot.files:
        bucket = by_category.get(stored.category_key)
        if bucket is None:
            bucket = by_category.setdefault(
                UNKNOWN.key,
                {
                    "key": UNKNOWN.key,
                    "label": UNKNOWN.label,
                    "icon": UNKNOWN.icon,
                    "color": UNKNOWN.color,
                    "files": 0,
                    "size_bytes": 0,
                },
            )
        bucket["files"] += 1
        bucket["size_bytes"] += stored.size_bytes
        total_bytes += stored.size_bytes

        type_bucket = by_type.setdefault(
            stored.type_label,
            {"type": stored.type_label, "files": 0, "size_bytes": 0},
        )
        type_bucket["files"] += 1
        type_bucket["size_bytes"] += stored.size_bytes

    categories = list(by_category.values())
    types = sorted(by_type.values(), key=lambda t: (-t["size_bytes"], t["type"]))

    return {
        "total_files": len(snapshot.files),
        "total_bytes": total_bytes,
        "categories": categories,
        "categories_in_use": sum(
            1 for c in categories if c["files"] > 0 and c["key"] != UNKNOWN.key
        ),
        "categories_available": len(CATEGORIES),
        "types": types,
        "types_in_use": len(types),
        "unreadable_files": snapshot.unreadable,
        "scan_error": snapshot.scan_error,
    }


async def summarize_memory(rag: Any) -> dict[str, Any]:
    """Qué documentos conoce el motor, por estado, con sus fragmentos.

    Lee con ``strict=False`` a propósito: esto es una ruta de listado para la
    interfaz, y el contrato documentado en ``BaseDocStatusStorage`` reserva
    ``strict=True`` para el plano de control del planificador. Un registro
    ilegible aquí debe restar de la cifra, no tumbar el panel.
    """
    statuses = [
        DocStatus.PENDING,
        DocStatus.PARSING,
        DocStatus.ANALYZING,
        DocStatus.PROCESSING,
        DocStatus.PREPROCESSED,
        DocStatus.PROCESSED,
        DocStatus.FAILED,
    ]

    try:
        documents = await rag.doc_status.get_docs_by_statuses(statuses, strict=False)
    except Exception as exc:  # el panel informa, no revienta
        logger.warning("BIMNEMO: no se pudo leer doc_status: %s", exc)
        return {
            "total_documents": 0,
            "by_status": {},
            "total_chunks": 0,
            "total_text_chars": 0,
            "documents_error": str(exc),
            "failed_reason": None,
        }

    by_status: dict[str, int] = {}
    total_chunks = 0
    total_text_chars = 0
    failed_reason: Optional[str] = None
    copia_repetida: Optional[str] = None

    for record in documents.values():
        status_value = getattr(record.status, "value", str(record.status))
        by_status[status_value] = by_status.get(status_value, 0) + 1
        total_chunks += getattr(record, "chunks_count", None) or 0
        total_text_chars += getattr(record, "content_length", None) or 0

        # El motivo del primer fallo, para que el panel pueda decir POR QUÉ.
        # Antes solo salía «N documentos fallaron», y la causa —una clave
        # rechazada, una cuenta sin crédito, un modelo que no existe— quedaba
        # en el registro del motor, donde nadie la busca.
        if status_value != DocStatus.FAILED.value:
            continue
        error = getattr(record, "error_msg", None)
        original = original_de_copia(error, documents)
        if original is not None:
            # Una copia repetida no es un fallo: se guarda aparte, y solo se
            # enseña si no hay ningún fallo de verdad que decir antes.
            if copia_repetida is None:
                copia_repetida = explicar_copia(_nombre_de(record), original)
        elif failed_reason is None:
            failed_reason = _clean_reason(error)

    return {
        "total_documents": len(documents),
        "by_status": by_status,
        "total_chunks": total_chunks,
        "total_text_chars": total_text_chars,
        "documents_error": None,
        "failed_reason": failed_reason or copia_repetida,
        # Para que la ventana lo pinte como aviso y no como error.
        "failed_kind": "error" if failed_reason else ("duplicate" if copia_repetida else None),
    }


#: Lo que cabe de un motivo de fallo sin convertir el aviso en un muro.
MAX_REASON = 300

#: El rechazo del motor a indexar dos veces el mismo contenido.
#:
#: Llega en inglés y con el identificador interno del original: «Identical
#: content already exists under another filename. Original doc_id: doc-…,
#: Status: DocStatus.PROCESSING». Quien lo leía no sabía qué había pasado ni
#: qué hacer, y en rojo parecía que se había perdido algo. No se ha perdido
#: nada: el contenido ya está en la memoria, una vez.
_DUPLICADO = re.compile(
    r"Identical content already exists under another filename\.\s*"
    r"Original doc_id:\s*(doc-[0-9a-fA-F]+)"
)


def _nombre_de(record: Any) -> str:
    ruta = getattr(record, "file_path", "") or ""
    return ruta.replace("\\", "/").rsplit("/", 1)[-1]


def original_de_copia(error_msg: Any, documents: dict[str, Any]) -> Optional[str]:
    """Si el fallo es una copia repetida, el nombre del original; si no, None.

    Devuelve cadena vacía si es una copia pero el original ya no se encuentra
    —se borró después—: sigue siendo una copia, aunque no se pueda decir de
    cuál.
    """
    encontrado = _DUPLICADO.search(str(error_msg or ""))
    if encontrado is None:
        return None
    original = documents.get(encontrado.group(1))
    return _nombre_de(original) if original is not None else ""


def explicar_copia(copia: str, original: str) -> str:
    """El aviso de una copia repetida, en castellano y con qué hacer."""
    de_cual = f"«{original}»" if original else "otro archivo"
    return (
        f"«{copia}» tiene exactamente el mismo contenido que {de_cual}, que ya "
        "está en la memoria, así que no se ha vuelto a leer. No falta nada. "
        f"Puedes borrar «{copia}» en Archivos: es solo una copia."
    )

#: Traducción de las excepciones que llegan **sin su mensaje**.
#:
#: Existe por cómo se pierde la causa por el camino: los reintentos envuelven
#: la excepción original en un ``RetryError`` de tenacity, y lo que queda
#: guardado es ``RetryError[<Future at 0x… raised RateLimitError>]``. La frase
#: del proveedor —«Your account is not active…»— solo aparece en el registro
#: del motor, donde el usuario no va a mirar.
#:
#: Aquí no se inventa lo que dijo el proveedor: se nombra el tipo de fallo y se
#: dice qué comprobar, que es lo que hace falta para poder arreglarlo.
_EXCEPTION_HINTS: tuple[tuple[str, str], ...] = (
    (
        "AuthenticationError",
        "el proveedor rechazó la clave de API (AuthenticationError). "
        "Compruébala en Configuración IA.",
    ),
    (
        "PermissionDeniedError",
        "la clave no tiene permiso para este modelo (PermissionDeniedError). "
        "Revisa los permisos del proyecto o de la cuenta de servicio.",
    ),
    (
        "RateLimitError",
        "el proveedor rechazó la petición por límite de uso o por facturación "
        "(RateLimitError). Mira el saldo y el plan de tu cuenta; el motivo "
        "exacto está en lightrag.log.",
    ),
    (
        "NotFoundError",
        "el proveedor no reconoce el modelo configurado (NotFoundError). "
        "Comprueba el nombre en Configuración IA.",
    ),
    (
        "BadRequestError",
        "el proveedor rechazó la petición por mal formada (BadRequestError). "
        "Suele ser el modelo o la dimensión de embeddings.",
    ),
    (
        "APIConnectionError",
        "no se pudo conectar con el proveedor (APIConnectionError). "
        "Comprueba la dirección (host) y tu conexión.",
    ),
    (
        "APITimeoutError",
        "el proveedor tardó más de lo permitido (APITimeoutError).",
    ),
)


#: Lo que se añade a cada aviso: dónde se arregla lo que ya falló.
_REINTENTAR = "Después pulsa «Reintentar» en Archivos."

#: Los fallos de los proveedores que más se repiten, y qué hacer con cada uno.
#:
#: Cada proveedor contesta en inglés y a su manera —«You have no credits
#: remaining», «insufficient_quota», «Your credit balance is too low»— y lo
#: que se enseñaba era esa frase tal cual. El usuario no tiene por qué saber
#: inglés ni qué es una cuota: tiene que saber qué ha pasado y qué hacer.
#:
#: Se busca en el texto entero, en minúsculas, porque el código del error
#: (``insufficient_quota``) viaja fuera de la frase. **El orden importa**: la
#: falta de saldo llega como un 429, igual que el exceso de peticiones, y hay
#: que reconocerla antes para no mandar a nadie a «esperar unos minutos» a una
#: cuenta que está a cero.
_PROVEEDOR_EN_CASTELLANO: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "no credits remaining",
            "insufficient_quota",
            "exceeded your current quota",
            "credit balance is too low",
            "insufficient balance",
            "billing_hard_limit",
            "payment required",
        ),
        "Tu cuenta del proveedor de IA se ha quedado sin saldo, así que no se "
        "pudo leer el documento. Añade crédito{donde}. Lo que ya estaba en la "
        "memoria no se ha perdido. " + _REINTENTAR,
    ),
    (
        ("account is not active", "account_deactivated", "account has been deactivated"),
        "La cuenta del proveedor de IA no está activa. Revísala en su web. "
        + _REINTENTAR,
    ),
    (
        (
            "incorrect api key",
            "invalid_api_key",
            "invalid x-api-key",
            "api key not valid",
            "invalid api key",
            "authenticationerror",
        ),
        "El proveedor de IA rechazó la clave de API. Revísala en Configuración "
        "IA. " + _REINTENTAR,
    ),
    (
        ("model_not_found", "does not exist", "notfounderror", "unknown model"),
        "El proveedor de IA no reconoce el modelo{modelo}. Elige otro en "
        "Configuración IA. " + _REINTENTAR,
    ),
    (
        ("context_length_exceeded", "maximum context length", "too many tokens"),
        "El texto es demasiado largo para el modelo elegido. Prueba con un "
        "modelo que admita más contexto en Configuración IA. " + _REINTENTAR,
    ),
    (
        ("rate limit", "rate_limit", "too many requests", "ratelimiterror"),
        "El proveedor de IA ha frenado las peticiones por ir demasiado rápido. "
        "Espera unos minutos. " + _REINTENTAR,
    ),
    (
        ("overloaded", "service unavailable", "internal server error", "bad gateway"),
        "El servicio del proveedor de IA está saturado o caído en este "
        "momento. No es cosa tuya: vuelve a intentarlo más tarde. " + _REINTENTAR,
    ),
    (
        (
            "apiconnectionerror",
            "connection error",
            "connecterror",
            "failed to establish",
            "name or service not known",
            "getaddrinfo failed",
        ),
        "No se pudo conectar con el proveedor de IA. Comprueba tu conexión a "
        "internet y la dirección en Configuración IA. " + _REINTENTAR,
    ),
    (
        ("timed out", "timeout", "apitimeouterror"),
        "El proveedor de IA tardó demasiado en contestar. " + _REINTENTAR,
    ),
)

#: A partir de cuántos caracteres una ruta de Windows da problemas. El límite
#: clásico es 260; se avisa un poco antes porque el lector de documentos
#: todavía añade nombres de fichero por debajo de la ruta que sale en el error.
RUTA_LARGA = 240

#: Una ruta de Windows entre comillas dentro de un mensaje de error.
_RUTA = re.compile(r"'([A-Za-z]:\\[^']+)'")

_RUTA_DEMASIADO_LARGA = (
    "El nombre del archivo es demasiado largo para Windows: al leerlo, "
    "BIMNEMO crea carpetas con ese nombre y la ruta pasa del límite. "
    "Renómbralo con un nombre más corto, bórralo en Archivos y vuelve a "
    "subirlo."
)


def _ruta_demasiado_larga(texto: str, minusculas: str) -> bool:
    """¿Es un fallo por pasarse del límite de longitud de ruta de Windows?

    Windows lo dice de tres maneras según dónde falle: «WinError 206» (el
    nombre es demasiado largo), y también «WinError 3» o «Errno 2» (no
    encuentra la ruta), porque la carpeta que debía contenerla no se llegó a
    crear. Las dos últimas solo cuentan si la ruta es de verdad larga: con una
    corta son otro problema.
    """
    if "winerror 206" in minusculas or "is too long" in minusculas:
        return True
    if not any(c in minusculas for c in ("winerror 3]", "errno 2]")):
        return False
    rutas = [r.replace("\\\\", "\\") for r in _RUTA.findall(texto)]
    return any(len(r) >= RUTA_LARGA for r in rutas)


_ENLACE = re.compile(r"https?://[^\s'\"<>]+")
_MODELO = re.compile(r"model[`'\" ]+([\w.\-:/]+)[`'\"]", re.IGNORECASE)


def en_castellano(raw: Any) -> Optional[str]:
    """El fallo de un proveedor dicho en castellano, con qué hacer; o None.

    ``None`` si no es ninguno de los conocidos: entonces se enseña lo que dijo
    el proveedor, que es mejor que inventarse un motivo.
    """
    texto = " ".join(str(raw or "").split())
    minusculas = texto.lower()
    if _ruta_demasiado_larga(texto, minusculas):
        return _RUTA_DEMASIADO_LARGA
    for claves, plantilla in _PROVEEDOR_EN_CASTELLANO:
        if not any(clave in minusculas for clave in claves):
            continue
        enlace = _ENLACE.search(texto)
        modelo = _MODELO.search(texto)
        return plantilla.format(
            donde=f" en {enlace.group(0).rstrip('.,;)')}" if enlace else "",
            modelo=f" «{modelo.group(1)}»" if modelo else "",
        )[:MAX_REASON]
    return None


def _clean_reason(raw: Any) -> Optional[str]:
    """Deja un motivo de fallo legible a partir de la excepción del motor.

    Tres intentos, de más útil a menos:

    1. La frase del proveedor, si viaja dentro del error.
    2. Si los reintentos se la tragaron, el tipo de fallo traducido a qué hay
       que comprobar.
    3. El texto crudo recortado, que siempre es mejor que nada.
    """
    if not raw:
        return None

    # Primero lo que se sabe explicar en castellano: sin saldo, clave mala…
    traducido = en_castellano(raw)
    if traducido:
        return traducido

    texto = " ".join(str(raw).split())

    # Las dos formas se dan de verdad: el SDK de OpenAI escupe el `repr` de un
    # diccionario de Python (comilla simple) y otros clientes reenvían el JSON
    # del proveedor tal cual (comilla doble). Buscar solo una era jugárselo a
    # cara o cruz según por dónde llegara el error.
    for marca in ("'message':", '"message":'):
        if marca not in texto:
            continue
        resto = texto.split(marca, 1)[1].lstrip()
        comilla = resto[:1]
        if comilla not in {"'", '"'}:
            continue
        cerrada = resto.find(comilla, 1)
        if cerrada > 1:
            mensaje = resto[1:cerrada].strip()
            if mensaje:
                return mensaje[:MAX_REASON]

    for nombre, explicacion in _EXCEPTION_HINTS:
        if nombre in texto:
            return explicacion[:MAX_REASON]

    return texto[:MAX_REASON]


async def graph_counts(rag: Any, cap: int = DEFAULT_GRAPH_COUNT_CAP) -> dict[str, Any]:
    """Entidades y relaciones del grafo, contadas con memoria acotada.

    Usa ``iter_labels`` / ``iter_edges`` en lugar de ``get_all_labels`` /
    ``get_all_edges``: el propio ``BaseGraphStorage`` advierte de que las
    segundas no deben usarse con un grafo grande, y las primeras están para
    exactamente esto. Un backend que no las implemente falla en cerrado con
    ``StorageCapabilityError``; entonces se devuelve ``supported: false`` en
    vez de arrastrar el grafo entero a memoria.

    Al llegar al tope se deja de contar y se marca ``truncated``.
    """
    graph = getattr(rag, "chunk_entity_relation_graph", None)
    if graph is None:
        return {
            "supported": False,
            "reason": "El motor no expone almacenamiento de grafo",
            "entities": 0,
            "relations": 0,
            "truncated": False,
        }

    async def _count(iterator_name: str) -> tuple[int, bool]:
        iterator = getattr(graph, iterator_name, None)
        if iterator is None:
            raise StorageCapabilityError(f"{iterator_name} no disponible")
        counted = 0
        truncated = False
        async for batch in iterator(GRAPH_ITER_BATCH):
            counted += len(batch)
            if counted >= cap:
                truncated = True
                break
        return counted, truncated

    try:
        entities, entities_truncated = await _count("iter_labels")
        relations, relations_truncated = await _count("iter_edges")
    except StorageCapabilityError as exc:
        return {
            "supported": False,
            "reason": str(exc),
            "entities": 0,
            "relations": 0,
            "truncated": False,
        }
    except Exception as exc:
        logger.warning("BIMNEMO: no se pudo contar el grafo: %s", exc)
        return {
            "supported": False,
            "reason": str(exc),
            "entities": 0,
            "relations": 0,
            "truncated": False,
        }

    return {
        "supported": True,
        "reason": None,
        "entities": entities,
        "relations": relations,
        "truncated": entities_truncated or relations_truncated,
        "cap": cap,
    }


def merge_files_with_memory(
    snapshot: StorageSnapshot, documents: dict[str, Any]
) -> list[dict[str, Any]]:
    """Cruza los ficheros en disco con lo que el motor sabe de ellos.

    El cruce es por **nombre de fichero**, que es lo que ``doc_status`` guarda
    en ``file_path`` para lo subido por la API. Un fichero en disco que el motor
    no conoce sale con ``status: null`` — está subido pero aún sin indexar, o se
    borró de la memoria y quedó el fichero. Ambas cosas son útiles de ver.
    """
    # Se guarda la CLAVE junto al registro: el identificador del documento es
    # la clave del diccionario, no un campo de `DocProcessingStatus` — ese
    # dataclass no tiene `id`. Leerlo de ahí devolvía siempre `None`, y sin
    # identificador la papelera de la tabla no podía borrar el índice: solo
    # quitaba el fichero y dejaba las entidades en el grafo.
    by_name: dict[str, Any] = {}
    for doc_id, record in documents.items():
        raw_path = getattr(record, "file_path", "") or ""
        name = raw_path.replace("\\", "/").rsplit("/", 1)[-1]
        if name:
            by_name.setdefault(name, (doc_id, record))

    rows: list[dict[str, Any]] = []
    for stored in snapshot.files:
        payload = stored.to_payload()
        encontrado = by_name.get(stored.name)
        if encontrado is None:
            payload.update(
                {
                    "status": None,
                    "chunks_count": None,
                    "text_chars": None,
                    "doc_id": None,
                    "updated_at": None,
                    "error_msg": None,
                    "duplicate_of": None,
                }
            )
        else:
            doc_id, record = encontrado
            error = getattr(record, "error_msg", None)
            original = original_de_copia(error, documents)
            payload.update(
                {
                    "status": getattr(record.status, "value", str(record.status)),
                    "chunks_count": getattr(record, "chunks_count", None),
                    "text_chars": getattr(record, "content_length", None),
                    "doc_id": doc_id,
                    "updated_at": getattr(record, "updated_at", None),
                    "error_msg": (
                        explicar_copia(stored.name, original)
                        if original is not None
                        else _clean_reason(error)
                    ),
                    # El original, si es una copia repetida; `None` si no.
                    "duplicate_of": original,
                }
            )
        rows.append(payload)

    rows.sort(key=lambda r: r["modified_at"], reverse=True)
    return rows


__all__ = [
    "DEFAULT_GRAPH_COUNT_CAP",
    "StorageSnapshot",
    "StoredFile",
    "graph_counts",
    "merge_files_with_memory",
    "scan_storage",
    "summarize_memory",
    "summarize_storage",
]
