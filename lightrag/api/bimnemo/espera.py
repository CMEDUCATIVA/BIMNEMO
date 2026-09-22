"""Acciones que esperan a que la memoria quede libre, en vez de negarse.

Reintentar o renombrar un documento fallido necesita la tubería **libre** un
momento —reservarla, reescribir su registro, soltarla—, porque tocarlo con
otro documento indexándose sería pisarle el trabajo. Antes eso se contestaba
con «la memoria está indexando; inténtalo al terminar», y el usuario tenía
que quedarse mirando hasta que acabara para pulsar otra vez.

Ahora la acción se **apunta** y se hace sola en cuanto se puede:

- Cada memoria tiene su fila (un ``asyncio.Lock``, que atiende por orden de
  llegada). La primera prueba cada pocos segundos; cuando consigue la
  reserva, lanza su trabajo y deja paso a la siguiente, que esperará a que
  ese trabajo termine de indexar. Nunca se pisan.
- Mientras espera, el nombre del archivo está en :func:`en_espera`, y la
  lista de Archivos lo enseña «En espera».

Lo apuntado vive en memoria: si el motor se cierra antes, se pierde, y el
documento sigue fallido como estaba. No se escribe nada a medias.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from lightrag.utils import logger

#: Cada cuánto vuelve a probar una acción que espera.
INTERVALO = 3.0

_EN_ESPERA: dict[str, set[str]] = {}
_FILAS: dict[str, asyncio.Lock] = {}


def en_espera(espacio: str) -> frozenset[str]:
    """Los archivos de esa memoria con una acción apuntada."""
    return frozenset(_EN_ESPERA.get(espacio or "", ()))


def apuntar(
    tareas: set,
    espacio: str,
    nombre: str,
    intento: Callable[[], Awaitable[bool]],
    intervalo: float = INTERVALO,
) -> None:
    """Hace ``intento`` en cuanto se pueda. ``intento`` dice si ya se hizo.

    Devuelve ``False`` mientras la memoria esté ocupada, y ``True`` cuando
    haya lanzado su trabajo (o cuando ya no tenga sentido seguir: un error
    se registra y la acción se abandona, no se reintenta sin fin).
    """
    espacio = espacio or ""
    _EN_ESPERA.setdefault(espacio, set()).add(nombre)
    fila = _FILAS.setdefault(espacio, asyncio.Lock())

    async def esperar() -> None:
        try:
            async with fila:
                while True:
                    await asyncio.sleep(intervalo)
                    try:
                        if await intento():
                            return
                    except Exception as exc:
                        logger.error(
                            "BIMNEMO: la acción apuntada sobre «%s» falló: %s",
                            nombre,
                            exc,
                        )
                        return
        finally:
            _EN_ESPERA.get(espacio, set()).discard(nombre)

    tarea = asyncio.ensure_future(esperar())
    tareas.add(tarea)
    tarea.add_done_callback(tareas.discard)


__all__ = ["INTERVALO", "apuntar", "en_espera"]
