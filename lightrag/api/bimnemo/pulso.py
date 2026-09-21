"""Cuándo se ha usado la memoria de verdad.

Sirve para una sola cosa: que el grafo del Panel se encienda cuando alguien
—una IA conectada, un guion, el propio chat— usa la memoria. La ventana
pregunta por este contador y, cuando sube, dispara una sinapsis.

## Qué se cuenta y qué no

Solo lo que **es usar la memoria**: consultarla, añadirle algo o quitarle
algo. Son los grupos `consultar`, `guardar` y `borrar` del manifiesto.

Lo de `explorar` —cuántos ficheros hay, las cifras del panel, el grafo— no
cuenta, y no es un capricho: eso es justo lo que la propia ventana sondea
cada pocos segundos para pintarse. Contándolo, el cerebro parpadearía sin
parar por mirarse a sí mismo.

## Por qué en un módulo y no en el router

Porque lo alimenta un middleware, que ve *todas* las peticiones venga quien
venga, y lo lee un endpoint. Los dos necesitan el mismo contador, y un
contador que vive dentro de uno de ellos es un contador que el otro no ve.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from lightrag.api.bimnemo.manifiesto import ENDPOINTS

#: Los grupos que cuentan como «se ha usado la memoria».
GRUPOS_QUE_CUENTAN = frozenset({"consultar", "guardar", "borrar"})

#: Cuántas llamadas recientes se recuerdan. Es para que la ventana pueda
#: enseñar qué se usó, no para llevar un registro: si hace falta auditoría,
#: se mira el log del motor, que sí lo guarda todo.
RECUERDO = 20


def _plantillas() -> tuple[tuple[str, str], ...]:
    """Verbo y ruta del manifiesto que cuentan como usar la memoria.

    **El verbo importa tanto como la ruta.** `/bimnemo/files` está en dos
    grupos: `GET` es explorar —lo que la ventana sondea— y `DELETE` es
    borrar. Filtrando solo por ruta, cada refresco de la lista de archivos
    contaba como uso de la memoria; medido, el contador subía a uno antes de
    que nadie hubiera preguntado nada.

    De la ruta se guarda el trozo fijo del principio: `/nemo/{nemo}/query`
    se convierte en `/nemo/`, y así una llamada con el nombre de la memoria
    dentro también casa. Es tosco a propósito — aquí solo hace falta saber
    si era de las que usan la memoria, no cuál era exactamente.
    """
    fijas: set[tuple[str, str]] = set()
    for endpoint in ENDPOINTS:
        if endpoint.get("group") not in GRUPOS_QUE_CUENTAN:
            continue
        ruta = str(endpoint.get("path") or "").split("{", 1)[0]
        fijas.add((str(endpoint.get("method") or "").upper(), ruta))
    return tuple(sorted(fijas))


PLANTILLAS = _plantillas()


class _Contador:
    """El estado, en un objeto para que no haya `global` por medio."""

    def __init__(self) -> None:
        self.total = 0
        self.recientes: deque[dict[str, Any]] = deque(maxlen=RECUERDO)

    def anotar(self, metodo: str, ruta: str) -> None:
        self.total += 1
        self.recientes.append(
            {"method": metodo, "path": ruta, "at": time.time()}
        )

    def estado(self) -> dict[str, Any]:
        return {"total": self.total, "recent": list(self.recientes)}


CONTADOR = _Contador()


def cuenta(metodo: str, ruta: str) -> bool:
    """¿Esta llamada es de las que usan la memoria?"""
    arriba = (metodo or "").upper()
    return any(
        arriba == verbo and ruta.startswith(inicio)
        for verbo, inicio in PLANTILLAS
    )


def anotar(metodo: str, ruta: str) -> None:
    if cuenta(metodo, ruta):
        CONTADOR.anotar(metodo, ruta)


def estado() -> dict[str, Any]:
    return CONTADOR.estado()


__all__ = ["GRUPOS_QUE_CUENTAN", "PLANTILLAS", "anotar", "cuenta", "estado"]
