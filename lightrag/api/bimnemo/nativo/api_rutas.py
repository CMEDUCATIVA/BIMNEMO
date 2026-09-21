"""De una plantilla del manifiesto a la ruta que de verdad funciona.

Traducción de `ui/js/apiview-rutas.js`, con su mismo criterio.

El manifiesto describe **la API**: dice que existe `/bimnemo/memory/search`
—sobre la memoria activa— y `/nemo/{nemo}/memory/search` —sobre una
concreta—. Eso es correcto como descriptor y **inservible para copiar**.

Quien copia tendría que saber que `{nemo}` es un identificador y no el
nombre, averiguar cuál es —«Obra Sur» es `Obra_Sur`— y sustituirlo a mano en
cada línea.

## Y con la memoria por defecto no hay sustitución que valga

Su identificador es **la cadena vacía**: `/nemo//memory/search` responde 404.
Hay que usar `/bimnemo/…` sin parámetro. Una plantilla genérica no puede
expresar eso, así que lo que se copiaría no funcionaría al pegarlo para la
memoria que casi todo el mundo tiene abierta.

Este módulo resuelve las dos cosas: elige la forma correcta y la rellena.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote

#: Pares que son **la misma operación** vista desde dos sitios.
#:
#: Elegida una memoria concreta, enseñar las dos es enseñar la misma fila dos
#: veces. La clave es la operación; el valor, qué ruta usar según la memoria
#: tenga identificador o sea la de por defecto.
GEMELOS = (
    ("/nemo/{nemo}/memory/search", "/bimnemo/memory/search"),
    ("/nemo/{nemo}/memory/remember", "/bimnemo/memory/remember"),
)

#: Rutas que para la memoria por defecto son **otra ruta distinta**.
#:
#: Subir a la memoria por defecto no es `/nemo//documents/upload`: es la ruta
#: oficial de LightRAG, que es justo la que usa la propia aplicación.
EQUIVALENTES_POR_DEFECTO = {
    "/nemo/{nemo}/documents/upload": "/documents/upload",
}

#: El orden en que salen los paneles. Primero la memoria abierta, que es lo
#: que casi siempre se busca.
ORDEN_AMBITOS = ("esta", "todas", "motor")


def _acepta_parametro(ruta: str) -> bool:
    """¿Esta ruta admite `?nemo=` para elegir memoria?"""
    return (
        ruta.startswith("/bimnemo/")
        and not ruta.startswith("/bimnemo/nemos")
        and "memory/search-all" not in ruta
        and "memory/ask-all" not in ruta
    )


def ruta_para(endpoint: dict[str, Any], nemo: str) -> Optional[str]:
    """La ruta concreta de un endpoint para una memoria.

    Devuelve `None` si ese endpoint **no aplica** a esta memoria: es el
    gemelo que sobra, y enseñarlo sería ofrecer para copiar una línea que
    devuelve 404.
    """
    ruta = str(endpoint.get("path") or "")
    por_defecto = not nemo

    for con_nombre, sin_nombre in GEMELOS:
        if ruta == con_nombre:
            return None if por_defecto else _rellenar(ruta, nemo)
        if ruta == sin_nombre:
            return ruta if por_defecto else None

    if por_defecto and ruta in EQUIVALENTES_POR_DEFECTO:
        return EQUIVALENTES_POR_DEFECTO[ruta]

    if "{nemo}" in ruta:
        return None if por_defecto else _rellenar(ruta, nemo)

    # `?nemo=` solo cuando hay identificador: omitirlo **es** decir «la de por
    # defecto», y ponerlo vacío no significa lo mismo.
    if not por_defecto and _acepta_parametro(ruta):
        return f"{ruta}?nemo={quote(nemo, safe='')}"

    return ruta


def _rellenar(ruta: str, nemo: str) -> str:
    return ruta.replace("{nemo}", quote(nemo, safe=""))


def por_ambito(
    endpoints: tuple[dict[str, Any], ...], nemo: str, ambitos: dict[str, str]
) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """Los endpoints que aplican a una memoria, resueltos y agrupados.

    Devuelve `(clave, título, filas)` por ámbito, sin los vacíos.
    """
    cajas: dict[str, list[dict[str, Any]]] = {k: [] for k in ORDEN_AMBITOS}

    for endpoint in endpoints:
        ruta = ruta_para(endpoint, nemo)
        if ruta is None:
            continue
        ambito = str(endpoint.get("scope") or "esta")
        cajas.setdefault(ambito, []).append({**endpoint, "ruta": ruta})

    return [
        (clave, ambitos.get(clave, clave), filas)
        for clave, filas in cajas.items()
        if filas
    ]


def de_memoria(endpoints: tuple[dict[str, Any], ...], nemo: str) -> dict[str, str]:
    """Las rutas que los ejemplos necesitan, ya resueltas.

    Los ejemplos enseñaban `/bimnemo/memory/search` fijo. Con «Obra Sur»
    abierta, eso lee **otra memoria** —la de por defecto—, así que el ejemplo
    funcionaba al pegarlo y devolvía lo que no era. Peor que fallar.
    """

    def dame(candidatas: tuple[str, ...]) -> str:
        for ruta in candidatas:
            for endpoint in endpoints:
                if endpoint.get("path") != ruta:
                    continue
                resuelta = ruta_para(endpoint, nemo)
                if resuelta:
                    return resuelta
        return candidatas[-1]

    return {
        "buscar": dame(("/nemo/{nemo}/memory/search", "/bimnemo/memory/search")),
        "recordar": dame(("/nemo/{nemo}/memory/remember", "/bimnemo/memory/remember")),
    }


__all__ = [
    "EQUIVALENTES_POR_DEFECTO",
    "GEMELOS",
    "de_memoria",
    "por_ambito",
    "ruta_para",
]
