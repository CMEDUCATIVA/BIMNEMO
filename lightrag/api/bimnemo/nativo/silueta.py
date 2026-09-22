"""La silueta de cerebro que llena el grafo.

## Qué es y qué no es

**No decide quién va junto a quién.** Eso lo siguen decidiendo las fuerzas:
primero el grafo se asienta como en «Fuerzas» y los nodos se agrupan por sus
relaciones. Después, esa disposición se lleva al cerebro entero conservando
el orden (:func:`llenar`): lo que estaba junto sigue junto, lo de la
izquierda sigue a la izquierda.

Antes la silueta solo **contenía**: empujaba dentro al que se salía. Con un
grafo denso —casi todas las memorias lo son— las fuerzas lo dejan hecho una
bola, y el cerebro se quedaba vacío alrededor de un montón en el centro con
los rótulos pisándose. Llenándolo, la información se conserva y la forma se
ve entera.

## Cómo está hecha la forma

Una **unión de elipses**, no un contorno dibujado a mano punto por punto.
Dos motivos, y los dos importan:

- La prueba «¿está este punto dentro?» se hace para cada nodo. Con
  elipses es una cuenta de dos multiplicaciones que numpy resuelve de golpe
  para todos los nodos a la vez; con un polígono habría que lanzar rayos.
- Cuando un nodo se sale hay que saber **hacia dónde** devolverlo. Con una
  elipse, el punto del borde en la misma dirección sale de una división. Con
  un polígono habría que buscar el segmento más cercano.
"""

from __future__ import annotations

import math

import numpy as np

from lightrag.api.bimnemo.nativo.disposicion import SEPARACION_ANILLO

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

def escala_para(cuantos: int) -> float:
    """Cómo de grande tiene que ser el cerebro para tantos nodos.

    **Del tamaño del círculo** de la disposición circular: el mismo radio
    para los mismos nodos. Antes crecía con la raíz del número y con
    doscientas cincuenta entidades el cerebro medía la sexta parte que el
    círculo: todo se amontonaba en el centro y los rótulos se pisaban.
    """
    return max(140.0, SEPARACION_ANILLO * max(cuantos, 1) / (2 * math.pi))


def caja(escala: float) -> tuple[np.ndarray, np.ndarray]:
    """Las esquinas del rectángulo que contiene el cerebro."""
    piezas = np.array(PIEZAS)
    bajo = (piezas[:, :2] - piezas[:, 2:]).min(axis=0) * escala
    alto = (piezas[:, :2] + piezas[:, 2:]).max(axis=0) * escala
    return bajo, alto


def _dentro(puntos: np.ndarray) -> np.ndarray:
    """¿Qué puntos (en coordenadas normalizadas) caen dentro del cerebro?"""
    centros = np.array([[cx, cy] for cx, cy, _rx, _ry in PIEZAS])
    radios = np.array([[rx, ry] for _cx, _cy, rx, ry in PIEZAS])
    delta = puntos[:, None, :] - centros[None, :, :]
    q = np.sum((delta / radios[None, :, :]) ** 2, axis=2)
    return np.min(q, axis=1) <= 1.0


def _puntos_dentro(cuantos: int) -> np.ndarray:
    """``cuantos`` puntos repartidos parejo por el cerebro, en normalizadas.

    Espiral áurea —pareja y sin alinear— de la que se quedan los que caen
    dentro. Determinista: el mismo grafo sale siempre igual.
    """
    elegidos = np.zeros((0, 2))
    muestras = cuantos * 2
    while len(elegidos) < cuantos:
        i = np.arange(muestras) + 0.5
        radio = np.sqrt(i / muestras) * 1.05
        angulo = i * 2.399963
        puntos = np.stack([np.cos(angulo) * radio, np.sin(angulo) * radio], axis=1)
        puntos[:, 1] = puntos[:, 1] * 0.9 - 0.05
        elegidos = puntos[_dentro(puntos)]
        muestras *= 2
    # Repartidos por toda la espiral y no los primeros, que están en el centro.
    cuales = np.linspace(0, len(elegidos) - 1, cuantos).astype(int)
    return elegidos[cuales]


def llenar(pos: np.ndarray, escala: float) -> np.ndarray:
    """A dónde va cada nodo para llenar el cerebro **sin perder su sitio**.

    Las fuerzas dejan un grafo denso hecho una bola, y agrandar el
    contorno no lo cambia: los muelles vuelven a juntarlo en medio. Así que
    la bola se lleva al cerebro entero conservando el orden: el que estaba
    más a la izquierda sigue a la izquierda, el de arriba sigue arriba, y
    los que estaban juntos —que es lo que dicen las relaciones— siguen
    juntos.

    Se hace por columnas: los nodos, ordenados de izquierda a derecha, se
    parten en columnas iguales, y lo mismo los puntos del cerebro; dentro
    de cada columna se emparejan de arriba abajo.
    """
    cuantos = len(pos)
    if not cuantos:
        return np.zeros((0, 2))
    destinos = _puntos_dentro(cuantos)
    bajo, alto = caja(1.0)
    ancho, largo = alto - bajo
    columnas = max(1, round(math.sqrt(cuantos * ancho / largo)))

    resultado = np.zeros_like(pos, dtype=float)
    nodos_x = np.array_split(np.argsort(pos[:, 0], kind="stable"), columnas)
    puntos_x = np.array_split(np.argsort(destinos[:, 0], kind="stable"), columnas)
    for nodos, puntos in zip(nodos_x, puntos_x):
        nodos = nodos[np.argsort(pos[nodos, 1], kind="stable")]
        puntos = puntos[np.argsort(destinos[puntos, 1], kind="stable")]
        resultado[nodos] = destinos[puntos]
    return resultado * escala


__all__ = [
    "PIEZAS",
    "caja",
    "escala_para",
    "llenar",
]
