"""El grafo en «Cerebro» llena la silueta en vez de amontonarse en medio.

Con un grafo denso las fuerzas dejan una bola, y la silueta —que antes solo
contenía— se quedaba vacía alrededor con los rótulos pisándose.
"""

from __future__ import annotations

import numpy as np
import pytest

from lightrag.api.bimnemo.nativo import silueta
from lightrag.api.bimnemo.nativo.disposicion import SEPARACION_ANILLO

pytestmark = pytest.mark.offline


def test_el_cerebro_mide_lo_que_el_circulo():
    for cuantos in (50, 250):
        assert silueta.escala_para(cuantos) == pytest.approx(
            SEPARACION_ANILLO * cuantos / (2 * np.pi)
        )


def test_llenar_pone_cada_nodo_dentro_y_en_sitios_distintos():
    rng = np.random.default_rng(1)
    bola = rng.normal(size=(250, 2)) * 60.0
    escala = silueta.escala_para(250)

    destinos = silueta.llenar(bola, escala)

    assert silueta._dentro(destinos / escala).all()
    assert len({tuple(np.round(d, 6)) for d in destinos}) == 250


def test_llenar_conserva_el_orden():
    """Lo de la izquierda sigue a la izquierda y lo de arriba, arriba."""
    rng = np.random.default_rng(2)
    bola = rng.normal(size=(200, 2)) * 60.0
    destinos = silueta.llenar(bola, silueta.escala_para(200))

    izquierda = bola[:, 0] < np.percentile(bola[:, 0], 20)
    derecha = bola[:, 0] > np.percentile(bola[:, 0], 80)
    assert destinos[izquierda, 0].max() < destinos[derecha, 0].min()


def _denso(aplicacion):
    from lightrag.api.bimnemo.nativo.grafo import Grafo

    rng = np.random.default_rng(3)
    nodos = [
        {"id": f"n{i}", "label": f"n{i}", "type": "cosa", "degree": 8}
        for i in range(120)
    ]
    aristas = [
        {"source": f"n{a}", "target": f"n{b}"}
        for a, b in rng.integers(0, 120, size=(500, 2))
        if a != b
    ]
    lienzo = Grafo()
    lienzo.resize(900, 600)
    lienzo.poner(nodos, aristas)
    lienzo.disponer("cerebro")
    for _ in range(800):
        lienzo._paso()
    lienzo._reloj.stop()
    return lienzo


def test_un_grafo_denso_ocupa_casi_todo_el_cerebro(aplicacion):
    lienzo = _denso(aplicacion)
    bajo, alto = silueta.caja(silueta.escala_para(120))

    # Antes, la bola ocupaba menos de un tercio. No llega al 100 %: la caja
    # incluye la punta del tronco, que es muy estrecha.
    ocupado = lienzo._pos.max(axis=0) - lienzo._pos.min(axis=0)
    assert (ocupado / (alto - bajo) > 0.75).all()


def test_un_nodo_arrastrado_se_queda_donde_lo_sueltan(aplicacion):
    lienzo = _denso(aplicacion)
    lienzo._arrastrando = 0
    lienzo._pos[0] = (5.0, 5.0)
    lienzo.mouseReleaseEvent(None)
    for _ in range(200):
        lienzo._paso()

    assert np.allclose(lienzo._pos[0], (5.0, 5.0), atol=1.0)
