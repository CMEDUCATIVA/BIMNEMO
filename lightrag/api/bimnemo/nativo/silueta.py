"""La silueta de cerebro que contiene el grafo.

## Qué es y qué no es

**No coloca los nodos.** Las fuerzas siguen mandando: los nodos se agrupan
por sus relaciones, los concentradores siguen tirando de sus vecinos y el
grafo se asienta como siempre. Lo único que hace la silueta es **contener**:
al nodo que se sale del contorno se le empuja dentro.

Esa distinción es todo. Colocar los nodos en forma de cerebro sería
decoración: la figura no diría nada de la memoria y el grafo dejaría de
informar para quedar bonito. Conteniendo, la información se conserva entera
y la silueta es el recipiente, no el resultado.

## Cómo está hecha la forma

Una **unión de elipses**, no un contorno dibujado a mano punto por punto.
Dos motivos, y los dos importan:

- La prueba «¿está este punto dentro?» se hace 191 veces por fotograma. Con
  elipses es una cuenta de dos multiplicaciones que numpy resuelve de golpe
  para todos los nodos a la vez; con un polígono habría que lanzar rayos.
- Cuando un nodo se sale hay que saber **hacia dónde** devolverlo. Con una
  elipse, el punto del borde en la misma dirección sale de una división. Con
  un polígono habría que buscar el segmento más cercano.
"""

from __future__ import annotations

import math

import numpy as np

#: Las piezas del cerebro, en coordenadas normalizadas: centro y radios.
#:
#: Visto de perfil, mirando a la izquierda. El eje Y crece hacia abajo, como
#: en la pantalla. La unión de las cinco da el bulto grande del cerebro, el
#: lóbulo frontal, el temporal, el cerebelo y el tronco.
PIEZAS: tuple[tuple[float, float, float, float], ...] = (
    (-0.02, -0.22, 0.82, 0.54),  # cerebro, el bulto grande de arriba
    (-0.58, 0.02, 0.38, 0.38),  # lóbulo frontal, el morro de delante
    (-0.34, 0.34, 0.40, 0.23),  # lóbulo temporal, por debajo del frontal
    (0.60, 0.04, 0.34, 0.34),  # lóbulo occipital, la nuca
    (0.54, 0.50, 0.30, 0.21),  # cerebelo, el bulto de atrás abajo
    (0.16, 0.60, 0.13, 0.30),  # tronco, bajando
)

#: Cuánto tira el contorno del nodo que se ha salido.
#:
#: Es un muelle, no una pared: devuelve al nodo en unas décimas de segundo
#: sin que rebote. Con un valor alto el grafo tiembla en el borde; con uno
#: bajo, la silueta no llega a leerse — con 0,10 se quedaban cuarenta de
#: ciento noventa y uno fuera del contorno.
CONTENCION = 0.22


def escala_para(cuantos: int) -> float:
    """Cómo de grande tiene que ser el cerebro para tantos nodos.

    Crece con la raíz del número, igual que crece el área que ocupa un
    montón de puntos repartidos. Fijarlo daría un cerebro que aprieta con
    doscientas entidades y queda vacío con veinte.
    """
    return max(120.0, 26.0 * math.sqrt(max(cuantos, 1)))


def contener(pos: np.ndarray, escala: float) -> np.ndarray:
    """La fuerza que devuelve dentro a los nodos que se han salido.

    Devuelve un vector por nodo: cero para los que están dentro, y para los
    de fuera el empuje hacia el punto del borde que les queda en línea
    recta desde el centro de su pieza más cercana.
    """
    if not len(pos):
        return np.zeros_like(pos)

    centros = np.array([[cx, cy] for cx, cy, _rx, _ry in PIEZAS]) * escala
    radios = np.array([[rx, ry] for _cx, _cy, rx, ry in PIEZAS]) * escala

    # `q` vale 1 justo en el borde de cada elipse, menos dentro y más fuera.
    delta = pos[:, None, :] - centros[None, :, :]
    q = np.sum((delta / radios[None, :, :]) ** 2, axis=2)

    # La pieza más cercana en esa medida es la que devuelve al nodo: así
    # entra por donde se salió y no cruza el cerebro de lado a lado.
    cual = np.argmin(q, axis=1)
    mejor = q[np.arange(len(pos)), cual]

    fuera = mejor > 1.0
    fuerza = np.zeros_like(pos)
    if not fuera.any():
        return fuerza

    indices = np.where(fuera)[0]
    d = delta[indices, cual[indices], :]
    # El punto del borde en la misma dirección: dividir por la raíz de `q`
    # es exactamente eso, porque `q` es cuadrático en la distancia.
    destino = centros[cual[indices]] + d / np.sqrt(mejor[indices])[:, None]
    fuerza[indices] = (destino - pos[indices]) * CONTENCION
    return fuerza


__all__ = ["CONTENCION", "PIEZAS", "contener", "escala_para"]
