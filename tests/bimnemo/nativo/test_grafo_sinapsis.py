"""El temblor que deja cada sinapsis al recorrer el grafo.

Lo que se prueba es que el impulso **mueve** lo que toca y que no deshace las
disposiciones fijas, que es donde este efecto podía hacer daño: en un círculo
o en los anillos por tipo los nodos están puestos a propósito, y encender las
fuerzas los desordena en dos segundos.
"""

from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.offline


def _grafo(aplicacion, clave: str):
    """Un grafo pequeño, ya asentado y quieto."""
    from lightrag.api.bimnemo.nativo.grafo import Grafo

    nodos = [
        {"id": f"n{i}", "label": f"n{i}", "type": "cosa", "degree": 2}
        for i in range(6)
    ]
    aristas = [{"source": f"n{i}", "target": f"n{i + 1}"} for i in range(5)]

    lienzo = Grafo()
    lienzo.resize(600, 400)
    lienzo.poner(nodos, aristas)
    lienzo.disponer(clave)
    for _ in range(600):
        lienzo._paso()
    lienzo._reloj.stop()
    return lienzo


def test_el_impulso_empuja_en_la_direccion_en_que_viajaba(aplicacion):
    lienzo = _grafo(aplicacion, "cerebro")
    origen, destino = lienzo._aristas[0]

    direccion = lienzo._pos[destino] - lienzo._pos[origen]
    direccion = direccion / np.hypot(*direccion)
    antes = lienzo._vel[destino].copy()

    lienzo._ondular(origen, destino)

    ganado = lienzo._vel[destino] - antes
    # Lo ganado apunta hacia donde iba el impulso, no a cualquier sitio.
    assert float(np.dot(ganado, direccion)) > 0
    assert np.hypot(*ganado) == pytest.approx(90.0, rel=0.01)


def test_la_sinapsis_despierta_la_simulacion_lo_justo(aplicacion):
    """Lo justo: al pulsar un nodo `alpha` sube a 0,35; aquí, a 0,01."""
    from lightrag.api.bimnemo.nativo import grafo as modulo

    lienzo = _grafo(aplicacion, "cerebro")
    assert lienzo._alpha < modulo.ALPHA_MIN or not lienzo._reloj.isActive()

    lienzo._ondular(*lienzo._aristas[0])

    assert lienzo._alpha == pytest.approx(modulo.SINAPSIS_ALPHA)
    assert lienzo._reloj.isActive()
    assert modulo.SINAPSIS_ALPHA < 0.05, "esto ya no sería un temblor"


def test_y_mueve_de_verdad_lo_que_toca(aplicacion):
    lienzo = _grafo(aplicacion, "cerebro")
    antes = lienzo._pos.copy()
    origen, destino = lienzo._aristas[0]

    lienzo._ondular(origen, destino)
    for _ in range(60):
        lienzo._paso()

    recorrido = float(np.hypot(*(lienzo._pos[destino] - antes[destino])))
    assert recorrido > 0.5, "el impulso no ha movido el nodo al que llega"


def test_en_las_disposiciones_fijas_no_pasa_nada(aplicacion):
    """El círculo se pide para verlo en círculo."""
    for clave in ("circular", "tipos", "radial"):
        lienzo = _grafo(aplicacion, clave)
        antes = lienzo._pos.copy()
        alpha = lienzo._alpha

        lienzo._ondular(*lienzo._aristas[0])

        assert lienzo._alpha == alpha
        assert not lienzo._reloj.isActive()
        assert np.array_equal(lienzo._pos, antes)
