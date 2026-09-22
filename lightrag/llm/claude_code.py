"""Binding ``claude_code``: usar la suscripción de Claude (Claude Code) como LLM.

LightRAG habla con los modelos a través de funciones asíncronas con la firma
``xxx_complete_if_cache``. Este binding no llama a una API: ejecuta el binario
de Claude Code en modo ``-p`` (print, sin sesión interactiva) y devuelve su
salida de texto. Es la vía para usar una suscripción de Claude Pro/Max —el
login OAuth de ``claude auth login``— en lugar de una clave de API.

Cada llamada arranca un proceso nuevo. Es más lento que una API HTTP y no
ofrece streaming; para la extracción y la consulta de BIMNEMO es suficiente.
El binario se resuelve así, en orden:

1. ``CLAUDE_CODE_BIN`` si está en el entorno (ruta explícita).
2. ``claude`` en el ``PATH``.

Los mensajes de error incluyen el estado del proceso y la salida de Claude
Code, acotada, para que un modelo mal escrito o una sesión caducada se puedan
diagnosticar desde la pantalla de configuración.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import AsyncIterator
from typing import Any

from lightrag.utils import logger

#: Plazo por defecto de una llamada. Claude Code arranca un proceso por cada
#: petición; en frío tarda más, pero cinco minutos es un margen prudente para
#: una consulta de extracción.
TIMEOUT_POR_DEFECTO = 300.0

#: Modo de permisos de la llamada. ``plan`` es solo lectura: Claude Code puede
#: leer para razonar, pero no escribir ni ejecutar nada. Para una extracción o
#: una respuesta es exactamente lo que se quiere.
MODO_PERMISOS = "plan"


def _binario() -> str:
    """El ejecutable de Claude Code, con la ruta explícita ganando al PATH."""
    explicito = os.environ.get("CLAUDE_CODE_BIN", "").strip()
    if explicito:
        return explicito
    return shutil.which("claude") or "claude"


def _texto_de_bloque(contenido: Any) -> str:
    """El texto de un ``content`` que puede ser cadena o lista de bloques.

    LightRAG pasa el historial como ``{"role": ..., "content": ...}`` y el
    contenido, según el camino, es una cadena o una lista estilo OpenAI
    (``{"type": "text", "text": ...}``). Aquí se normaliza a texto plano.
    """
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        return " ".join(
            bloque.get("text", "")
            for bloque in contenido
            if isinstance(bloque, dict) and bloque.get("type") == "text"
        )
    return ""


def _armar_prompt(
    prompt: str,
    system_prompt: str | None,
    history_messages: list[dict[str, Any]] | None,
) -> str:
    """Un solo mensaje con el contexto del sistema y el historial delante.

    Claude Code en ``-p`` no recibe un ``system`` separado como la API, así que
    el sistema se antepone de forma explícita. El historial se conserva para
    que las consultas multi-turno no pierdan el hilo.
    """
    partes: list[str] = []
    if system_prompt:
        partes.append(f"<system>\n{system_prompt}\n</system>")
    for mensaje in history_messages or []:
        rol = mensaje.get("role") or "assistant"
        texto = _texto_de_bloque(mensaje.get("content"))
        if texto.strip():
            partes.append(f"<{rol}>\n{texto}\n</{rol}>")
    partes.append(f"<user>\n{prompt}\n</user>")
    return "\n\n".join(partes)


async def claude_code_complete_if_cache(
    model: str,
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict[str, Any]] | None = None,
    enable_cot: bool = False,
    base_url: str | None = None,
    api_key: str | None = None,
    image_inputs: list[Any] | None = None,
    token_tracker: Any | None = None,
    **kwargs: Any,
) -> str | AsyncIterator[str]:
    """Ejecuta una compleción contra Claude Code y devuelve el texto.

    Los argumentos ``base_url``, ``api_key`` e ``image_inputs`` existen por
    compatibilidad con la firma común de los bindings y aquí se ignoran: la
    suscripción autentica por el login OAuth de Claude Code, no por clave.
    """
    kwargs.pop("hashing_kv", None)
    timeout = kwargs.pop("timeout", None) or TIMEOUT_POR_DEFECTO
    if enable_cot:
        logger.debug("claude_code: enable_cot=True se ignora (no es una API).")

    binario = _binario()
    texto = _armar_prompt(prompt, system_prompt, history_messages)

    orden = [
        binario,
        "-p",
        texto,
        "--output-format",
        "text",
        "--max-turns",
        "1",
        "--no-session-persistence",
        "--permission-mode",
        MODO_PERMISOS,
    ]
    if model:
        orden += ["--model", model]

    try:
        proceso = await asyncio.create_subprocess_exec(
            *orden,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "No se encontró el binario de Claude Code. Descárgalo e inicia "
            "sesión en Configuración IA (Claude → por suscripción)."
        ) from None
    except OSError as exc:
        raise RuntimeError(f"No se pudo ejecutar Claude Code: {exc}") from exc

    try:
        salida, error = await asyncio.wait_for(proceso.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proceso.kill()
        except OSError:
            pass
        raise RuntimeError("Claude Code tardó demasiado en responder.") from None

    if proceso.returncode != 0:
        detalle = (error or salida).decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"Claude Code terminó con error ({proceso.returncode}): "
            f"{detalle[:500] or 'sin detalle'}"
        )

    return salida.decode("utf-8", errors="replace").strip()


async def claude_code_complete(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> str | AsyncIterator[str]:
    """Envoltorio genérico: el modelo sale de la configuración del motor.

    Es el mismo patrón que ``anthropic_complete``: el nombre del modelo se lee
    de ``hashing_kv``, que es lo que el motor rellena en cada llamada.
    """
    if history_messages is None:
        history_messages = []
    modelo = ""
    hashing_kv = kwargs.get("hashing_kv")
    if hashing_kv is not None and hasattr(hashing_kv, "global_config"):
        modelo = hashing_kv.global_config.get("llm_model_name", "") or ""
    return await claude_code_complete_if_cache(
        modelo,
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        **kwargs,
    )
