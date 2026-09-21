"""Cómo se colocan los nodos del grafo.

Traducción de `ui/js/grafo-disposicion.js`, con sus mismas constantes y su
mismo criterio. Hay dos clases de disposición y se comportan distinto:

- Las de **simulación** (fuerzas, Force Atlas) no calculan posiciones: ajustan
  las fuerzas y dejan que el grafo se asiente solo.
- Las **fijas** (circular, círculos por tipo, radial) colocan cada nodo en su
  sitio de una vez y la simulación se apaga.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

#: Separación mínima entre centros de nodos en las disposiciones fijas.
SEPARACION = 30.0

#: Separación entre vecinos de un mismo anillo. Es casi el doble que la
#: mínima porque en un anillo los nodos llevan el rótulo debajo: con la
#: separación justa los círculos no se tocan, pero los nombres sí.
SEPARACION_ANILLO = 54.0

#: Las disposiciones que se ofrecen, en el orden del selector.
DISPOSICIONES = (
    ("fuerzas", "Fuerzas", "sim"),
    ("atlas", "Force Atlas", "sim"),
    # Fuerzas otra vez, pero contenidas en una silueta de cerebro. Es de
    # simulación a propósito: los nodos los coloca la física, no la forma.
    ("cerebro", "Cerebro", "sim"),
    ("circular", "Circular", "fija"),
    ("tipos", "Círculos por tipo", "fija"),
    ("radial", "Radial por conexiones", "fija"),
)

#: Con cuál se abre el grafo.
#:
#: «Cerebro» y no «Fuerzas» aunque por debajo sean lo mismo: las dos colocan
#: los nodos con la misma física, así que no se pierde ninguna información
#: por empezar con la silueta puesta. Y para una memoria de conocimiento es
#: la primera imagen que tiene sentido.
POR_DEFECTO = "cerebro"

_CLASE = {clave: clase for clave, _rotulo, clase in DISPOSICIONES}


def es_simulacion(clave: str) -> bool:
    return _CLASE.get(clave, "sim") == "sim"


def _orden(nodos: list[dict[str, Any]], indices: list[int], clave) -> list[int]:
    return sorted(indices, key=lambda i: clave(nodos[i]))


def _circular(nodos: list[dict], pos: np.ndarray) -> None:
    """Todas las entidades en un círculo, agrupadas por tipo.

    Agrupar por tipo es lo que hace útil esta disposición: cada tipo ocupa un
    arco continuo y se ve de un vistazo cuánto pesa cada uno. Ordenadas al
    azar —como haría un círculo «puro»— solo sería una lista doblada.
    """
    indices = _orden(
        nodos,
        list(range(len(nodos))),
        lambda n: (
            str(n.get("type") or ""),
            -int(n.get("degree") or 0),
            str(n.get("label") or ""),
        ),
    )
    total = len(indices) or 1
    radio = max(140.0, SEPARACION_ANILLO * total / (2 * math.pi))

    for puesto, i in enumerate(indices):
        angulo = (puesto / total) * 2 * math.pi - math.pi / 2
        pos[i] = (math.cos(angulo) * radio, math.sin(angulo) * radio)


def _espiral(cuantos: int, paso: float) -> list[tuple[float, float]]:
    """Reparte puntos dentro de un disco, en espiral áurea: sin huecos ni filas."""
    return [
        (
            math.cos(i * 2.399) * paso * math.sqrt(i + 0.5),
            math.sin(i * 2.399) * paso * math.sqrt(i + 0.5),
        )
        for i in range(cuantos)
    ]


def _por_tipos(nodos: list[dict], pos: np.ndarray) -> None:
    """Un disco por tipo de entidad, y los discos repartidos en corona.

    Es el equivalente del «circlepack» de LightRAG, pero agrupando por tipo en
    vez de empaquetar sin más: empaquetar por empaquetar da una forma bonita
    que no dice nada, y el tipo es la única agrupación que la memoria conoce.
    """
    grupos: dict[str, list[int]] = {}
    for i, n in enumerate(nodos):
        grupos.setdefault(str(n.get("type") or "—"), []).append(i)

    # De mayor a menor: los tipos numerosos primero, para que la corona no
    # empiece con un grupo de un solo nodo.
    ordenados = sorted(grupos.items(), key=lambda par: (-len(par[1]), par[0]))
    discos = [
        (miembros, max(SEPARACION, SEPARACION * math.sqrt(len(miembros)) / 1.5))
        for _tipo, miembros in ordenados
    ]

    def colocar(miembros: list[int], radio_disco: float, cx: float, cy: float) -> None:
        dentro = _orden(nodos, miembros, lambda n: -int(n.get("degree") or 0))
        puntos = _espiral(len(dentro), SEPARACION * 0.62)
        for (x, y), i in zip(puntos, dentro):
            pos[i] = (cx + x, cy + y)

    if len(discos) == 1:
        colocar(discos[0][0], discos[0][1], 0.0, 0.0)
        return

    hueco = SEPARACION
    perimetro = sum(2 * radio + hueco for _m, radio in discos) or 1.0
    corona = max(140.0, perimetro / (2 * math.pi))

    recorrido = 0.0
    for miembros, radio in discos:
        tramo = 2 * radio + hueco
        # El ángulo de cada disco es proporcional a su tamaño: así los grandes
        # no se pisan con los pequeños.
        angulo = ((recorrido + tramo / 2) / perimetro) * 2 * math.pi - math.pi / 2
        recorrido += tramo
        colocar(miembros, radio, math.cos(angulo) * corona, math.sin(angulo) * corona)


def _radial(nodos: list[dict], pos: np.ndarray) -> None:
    """Anillos concéntricos: cuantas más relaciones, más al centro.

    Responde de un vistazo a «qué sostiene esta memoria», que en un grafo de
    fuerzas hay que deducir mirando cuál tiene más líneas.
    """
    if not nodos:
        return
    indices = _orden(
        nodos,
        list(range(len(nodos))),
        lambda n: (-int(n.get("degree") or 0), str(n.get("label") or "")),
    )

    # La más conectada va sola en el centro.
    pos[indices[0]] = (0.0, 0.0)

    puesto = 1
    anillo = 1
    radio_anterior = 0.0

    while puesto < len(indices):
        # Se decide PRIMERO cuántas caben y DESPUÉS el radio, no al revés: con
        # el radio fijado de antemano, los anillos interiores salían con los
        # nodos pegados y los rótulos encima unos de otros.
        cabida = 6 * anillo
        restantes = len(indices) - puesto
        # Si lo que queda casi cabe, entra todo: un anillo exterior con un
        # solo nodo deja el grafo descentrado y desperdicia medio lienzo.
        cuantos = restantes if restantes <= cabida * 1.5 else cabida
        tanda = indices[puesto : puesto + cuantos]

        radio = max(
            radio_anterior + SEPARACION * 2.8,
            len(tanda) * SEPARACION_ANILLO / (2 * math.pi),
        )
        for k, i in enumerate(tanda):
            angulo = (k / len(tanda)) * 2 * math.pi - math.pi / 2
            pos[i] = (math.cos(angulo) * radio, math.sin(angulo) * radio)

        radio_anterior = radio
        puesto += len(tanda)
        anillo += 1


_FIJAS = {"circular": _circular, "tipos": _por_tipos, "radial": _radial}


def aplicar(clave: str, nodos: list[dict], pos: np.ndarray) -> bool:
    """Coloca los nodos según la disposición pedida.

    Devuelve `True` si ha movido algo. Para las de simulación devuelve
    `False`: ahí las posiciones las decide el lienzo, no este módulo.
    """
    fija = _FIJAS.get(clave)
    if fija is None or not nodos:
        return False
    fija(nodos, pos)
    return True


__all__ = ["DISPOSICIONES", "POR_DEFECTO", "aplicar", "es_simulacion"]
