"""Cuánto se gasta: tokens y coste de cada llamada a la IA, por día y modelo.

Existe porque una ley de 49 fragmentos costó unos 4 USD y nada en BIMNEMO lo
decía. El usuario se enteró por la factura.

## Qué se mide y de dónde sale

**Lo que cuenta el proveedor, no una estimación.** Los bindings de LightRAG
ya aceptan un ``token_tracker`` y le pasan el ``usage`` de la respuesta real
(``openai.py``, ``gemini.py``, ``ollama.py``, ``bedrock.py``). Este módulo
es ese contador. El servidor lo engancha en un solo punto por tipo:

- LLM: la función de cada rol (``create_role_llm_func``);
- embeddings: las ramas ``openai`` y ``gemini`` de la función de embeddings.

Una respuesta servida desde la caché de LLM no llama al proveedor y no se
cuenta, que es justo lo que no se paga.

La salida se toma como ``max(completion, total − prompt)``. En OpenAI y
DeepSeek los tokens de razonamiento ya van dentro de ``completion``; en
Gemini no (van en ``thoughts``), pero sí en el total, y se cobran igual.

## El coste se fija al llamar

DeepSeek cobra el doble en hora punta, y eso depende de la hora de la llamada.
Por eso cada registro guarda su coste en el momento, en vez de recalcularlo
al pintar la tabla.

## Dónde se guarda

``<working_dir>/bimnemo_consumo.json``, agregado por
(fecha local, tipo, tarea, modelo). Es **global a todas las memorias**: lo que
se paga es la cuenta del proveedor, no una memoria. Se escribe entero y de
forma atómica en cada cambio; es un fichero pequeño (una fila por día y
modelo), y así un cierre brusco nunca lo deja a medias.
"""

from __future__ import annotations

import contextvars
import functools
import json
import os
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from lightrag.api.bimnemo import precios
from lightrag.utils import logger

NOMBRE_FICHERO = "bimnemo_consumo.json"

#: El archivo que se está indexando en esta tarea, para saber a quién cargar
#: cada llamada. Vacío fuera de una indexación (una pregunta del chat).
#:
#: Llega hasta la llamada al proveedor aunque esta pase por la cola de
#: prioridad del rol: ``priority_limit_async_func_call`` copia el contexto de
#: quien encola (``contextvars.copy_context()``) y ejecuta la llamada dentro de
#: él, y las tareas que crea el documento heredan el suyo al crearse.
DOCUMENTO: contextvars.ContextVar[str] = contextvars.ContextVar(
    "bimnemo_documento", default=""
)

#: El rol del motor → la tarea que entiende quien mira la tabla.
TAREAS = {
    "extract": "Indexar",
    "keyword": "Palabras clave",
    "query": "Responder",
    "vlm": "Imágenes",
    "embedding": "Embeddings",
}

#: Bindings cuyo conector acepta ``token_tracker``. Pasárselo a otro sería un
#: ``TypeError`` en la llamada, no un no-op (ver ``ollama.py``).
CON_CONTADOR_LLM = frozenset({"openai", "gemini", "ollama", "bedrock", "claude_code"})
CON_CONTADOR_EMBEDDING = frozenset({"openai", "gemini"})


class _Registro:
    """El agregado en memoria y su fichero. Uno por proceso."""

    def __init__(self) -> None:
        self._cerrojo = threading.Lock()
        self._ruta: Optional[Path] = None
        self._filas: dict[str, dict[str, Any]] = {}
        #: Cambia con cada llamada contada: la vista lo compara para saber si
        #: repintar, igual que el sello de /bimnemo/progress.
        self.revision = 0

    def iniciar(self, carpeta: Path) -> None:
        with self._cerrojo:
            self._ruta = Path(carpeta) / NOMBRE_FICHERO
            self._filas = self._leer(self._ruta)

    @staticmethod
    def _leer(ruta: Path) -> dict[str, dict[str, Any]]:
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            # Un fichero ilegible no puede impedir que el motor arranque: se
            # empieza de cero y se dice.
            logger.warning("BIMNEMO: consumo ilegible, se empieza de cero: %s", exc)
            return {}
        filas = datos.get("filas") if isinstance(datos, dict) else None
        return filas if isinstance(filas, dict) else {}

    def anotar(
        self,
        tipo: str,
        tarea: str,
        modelo: str,
        host: str,
        entrada: int,
        salida: int,
        momento: Optional[datetime] = None,
        archivo: str = "",
        nivel: str = "",
        razonando: int = 0,
        inicio: Optional[datetime] = None,
    ) -> None:
        """Suma una llamada.

        ``nivel`` es el razonamiento configurado para esa tarea al llamar
        («Apagado», «Alto», «Lo que decida el modelo»…); ``razonando``, los
        tokens de salida que el proveedor dice que fueron razonamiento. Con
        los dos se ve si lo configurado se cumplió: «Apagado» con un 60 %
        pensando es que el proveedor no hizo caso.

        ``inicio`` es cuándo empezó la llamada y ``momento`` cuándo acabó. La
        fila guarda el primer inicio y el último fin —de qué hora a qué hora
        se trabajó en ese archivo— y la suma de lo que tardó cada llamada.
        """
        momento = momento or datetime.now(timezone.utc)
        inicio = inicio or momento
        p = precios.precio(tipo, modelo, host, momento)
        importe = precios.coste(p, entrada, salida)
        dia = momento.astimezone().date().isoformat()
        clave = "|".join((dia, tipo, tarea, modelo, archivo, nivel))

        with self._cerrojo:
            fila = self._filas.setdefault(
                clave,
                {
                    "fecha": dia,
                    "tipo": tipo,
                    "tarea": tarea,
                    "modelo": modelo,
                    "archivo": archivo,
                    "nivel": nivel,
                    "llamadas": 0,
                    "entrada": 0,
                    "salida": 0,
                    "razonando": 0,
                    "coste": 0.0,
                    "sin_precio": False,
                },
            )
            fila["llamadas"] += 1
            fila["entrada"] += int(entrada)
            fila["salida"] += int(salida)
            # Las filas de antes de contar el razonamiento o el tiempo no traen
            # esas claves.
            fila["razonando"] = fila.get("razonando", 0) + int(razonando)
            ini, fin = inicio.astimezone(timezone.utc), momento.astimezone(timezone.utc)
            if not fila.get("inicio") or ini.isoformat() < fila["inicio"]:
                fila["inicio"] = ini.isoformat()
            if not fila.get("fin") or fin.isoformat() > fila["fin"]:
                fila["fin"] = fin.isoformat()
            fila["segundos"] = round(
                fila.get("segundos", 0.0) + max((fin - ini).total_seconds(), 0.0), 3
            )
            if importe is None:
                fila["sin_precio"] = True
            else:
                fila["coste"] = round(fila["coste"] + importe, 6)
            self.revision += 1
            self._guardar()

    def _guardar(self) -> None:
        """Escribe el agregado entero, sin dejar nunca el fichero a medias."""
        if self._ruta is None:
            return
        try:
            self._ruta.parent.mkdir(parents=True, exist_ok=True)
            fd, temporal = tempfile.mkstemp(
                dir=self._ruta.parent, prefix=".consumo-", suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"filas": self._filas}, f, ensure_ascii=False)
            os.replace(temporal, self._ruta)
        except OSError as exc:
            # Medir no puede tumbar una indexación.
            logger.warning("BIMNEMO: no se pudo guardar el consumo: %s", exc)

    def borrar(self, clave: str) -> bool:
        """Quita una fila de la tabla. Solo del registro: la factura es otra cosa."""
        with self._cerrojo:
            if self._filas.pop(clave, None) is None:
                return False
            self.revision += 1
            self._guardar()
            return True

    def resumen(self, dias: int = 30, hoy: Optional[date] = None) -> dict[str, Any]:
        """Filas de los últimos ``dias`` y totales de hoy, 7 y 30 días."""
        hoy = hoy or datetime.now().astimezone().date()
        desde = (hoy - timedelta(days=max(dias, 1) - 1)).isoformat()
        hace7 = (hoy - timedelta(days=6)).isoformat()
        hace30 = (hoy - timedelta(days=29)).isoformat()
        with self._cerrojo:
            # `id` es la clave del agregado: con ella se borra una fila.
            filas = [dict(f, id=clave) for clave, f in self._filas.items()]
            revision = self.revision

        def suma(desde_dia: str) -> dict[str, Any]:
            elegidas = [f for f in filas if f["fecha"] >= desde_dia]
            return {
                "coste": round(sum(f["coste"] for f in elegidas), 4),
                "entrada": sum(f["entrada"] for f in elegidas),
                "salida": sum(f["salida"] for f in elegidas),
                "llamadas": sum(f["llamadas"] for f in elegidas),
                "sin_precio": any(f["sin_precio"] for f in elegidas),
            }

        # Lo último primero: por día y, dentro del día, por cuándo acabó.
        visibles = sorted(
            (f for f in filas if f["fecha"] >= desde),
            key=lambda f: (f["fecha"], f.get("fin") or "", f["coste"]),
            reverse=True,
        )
        return {
            "rows": visibles,
            "totals": {
                "today": suma(hoy.isoformat()),
                "week": suma(hace7),
                "month": suma(hace30),
            },
            "prices_checked": precios.COMPROBADO,
            "revision": revision,
        }


REGISTRO = _Registro()


class Contador:
    """El ``token_tracker`` que se le pasa a un binding para una llamada."""

    def __init__(
        self, tipo: str, tarea: str, modelo: str, host: str = "", nivel: str = ""
    ) -> None:
        self.tipo = tipo
        self.tarea = tarea
        self.modelo = modelo or "?"
        self.host = host or ""
        self.nivel = nivel
        # Se crea justo antes de llamar al proveedor: es el inicio de la llamada.
        self.inicio = datetime.now(timezone.utc)

    def add_usage(self, cuentas: dict[str, Any]) -> None:
        try:
            entrada = int(cuentas.get("prompt_tokens") or 0)
            completado = int(cuentas.get("completion_tokens") or 0)
            total = int(cuentas.get("total_tokens") or 0)
            salida = max(completado, total - entrada) if total else completado
            # Lo que el proveedor dice que fue razonamiento. OpenAI y DeepSeek
            # lo dan aparte (dentro de `completion`); Gemini no, pero lo que
            # sobra del total por encima de lo visible es justo eso.
            razonando = int(cuentas.get("reasoning_tokens") or 0) or max(
                total - entrada - completado, 0
            )
            REGISTRO.anotar(
                self.tipo,
                self.tarea,
                self.modelo,
                self.host,
                entrada,
                max(salida, 0),
                archivo=DOCUMENTO.get(),
                nivel=self.nivel,
                razonando=min(razonando, max(salida, 0)),
                inicio=self.inicio,
            )
        except Exception as exc:  # medir nunca rompe la llamada que se mide
            logger.warning("BIMNEMO: no se pudo contar el consumo: %s", exc)


def _nivel(binding: str, modelo: str, host: str, opciones: dict[str, Any]) -> str:
    """El razonamiento configurado para esa tarea, dicho como en la barra."""
    try:
        from lightrag.api.bimnemo import razonamiento
        from lightrag.api.bimnemo.providers import match_provider

        proveedor = match_provider("llm", binding, host) or binding
        return razonamiento.nivel_de_opciones(proveedor, modelo, opciones or {})
    except Exception as exc:  # una etiqueta no puede impedir medir
        logger.warning("BIMNEMO: no se pudo saber el nivel de razonamiento: %s", exc)
        return ""


def medir_llm(
    func,
    rol: str,
    binding: str,
    modelo: str,
    host: str,
    opciones: Optional[dict[str, Any]] = None,
):
    """Envuelve la función de un rol para que cuente lo que gasta.

    Solo para bindings que aceptan ``token_tracker``; al resto se les
    devuelve la función tal cual. Si quien llama ya trae su propio contador,
    se respeta. ``opciones`` son las que el rol manda al proveedor; de ellas
    sale el nivel de razonamiento que se apunta con cada llamada.
    """
    if binding not in CON_CONTADOR_LLM:
        return func

    tarea = TAREAS.get(rol, rol)
    nivel = _nivel(binding, modelo, host, opciones or {})

    @functools.wraps(func)
    async def medida(*args, **kwargs):
        kwargs.setdefault("token_tracker", Contador("llm", tarea, modelo, host, nivel))
        return await func(*args, **kwargs)

    return medida


def contador_embeddings(binding: str, modelo: str, host: str) -> Optional[Contador]:
    """El contador para una llamada de embeddings, o ``None`` si no se puede medir."""
    if binding not in CON_CONTADOR_EMBEDDING:
        return None
    return Contador("embedding", TAREAS["embedding"], modelo, host)


def instalar_marcador() -> None:
    """Marca en :data:`DOCUMENTO` el archivo que procesa cada tarea.

    Envuelve ``process_single_document`` —el que lleva un documento de la
    extracción a la fusión— en vez de editar la tubería de LightRAG: es un
    solo punto, no cambia nada de lo que hace, y deja el motor intacto. Se
    instala una vez; llamarlo de nuevo no lo envuelve dos veces.
    """
    from lightrag.pipeline import _PipelineMixin

    def ruta_proceso(kwargs: dict[str, Any]) -> str:
        estado = kwargs.get("status_doc")
        return str(getattr(estado, "file_path", "") or kwargs.get("doc_id") or "")

    def ruta_analisis(kwargs: dict[str, Any]) -> str:
        return str(kwargs.get("file_path") or kwargs.get("doc_id") or "")

    # Dos fases gastan por un documento: el análisis de tablas, ecuaciones e
    # imágenes (``analyze_multimodal``, en su propio trabajador) y la
    # extracción y fusión (``process_single_document``). Sin la primera, lo
    # que cuesta analizar las tablas de un Word salía sin archivo.
    for nombre, ruta_de in (
        ("process_single_document", ruta_proceso),
        ("analyze_multimodal", ruta_analisis),
    ):
        original = getattr(_PipelineMixin, nombre)
        if getattr(original, "_bimnemo_marcado", False):
            continue

        def envolver(original, ruta_de):
            @functools.wraps(original)
            async def marcado(self, *args, **kwargs):
                ruta = ruta_de(kwargs)
                testigo = DOCUMENTO.set(Path(ruta).name if ruta else "")
                try:
                    return await original(self, *args, **kwargs)
                finally:
                    DOCUMENTO.reset(testigo)

            marcado._bimnemo_marcado = True
            return marcado

        setattr(_PipelineMixin, nombre, envolver(original, ruta_de))


def iniciar(carpeta: Path) -> None:
    """Carga lo ya contado y empieza a marcar archivos. Lo llama el servidor."""
    REGISTRO.iniciar(carpeta)
    instalar_marcador()


__all__ = [
    "Contador",
    "REGISTRO",
    "contador_embeddings",
    "iniciar",
    "medir_llm",
]
