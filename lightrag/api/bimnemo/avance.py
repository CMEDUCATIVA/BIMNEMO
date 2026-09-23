"""De los contadores del motor a una barra que se entiende.

El motor publica, por documento, en qué fase va y cuántos elementos lleva
(``lightrag/doc_progress.py``). Aquí eso se convierte en lo que enseña una
fila de Archivos: **una etiqueta en castellano y un porcentaje**.

## Por qué un porcentaje con pesos

Un documento pasa por cuatro fases y cada una tiene su propio contador. Si
cada fase pintara 0-100 %, la barra volvería atrás tres veces. Con un peso
por fase (:data:`PESOS`) el porcentaje **solo avanza**: leer termina en el
8 %, analizar en el 45 %, extraer en el 85 % y unir el grafo en el 100 %.

Los pesos salen de lo que se midió en documentos reales de normativa: las
tablas son la fase larga en un Word, y la extracción la que más se nota en
un PDF, que no tiene fase de tablas. No son exactos, y no pueden serlo: son
el reparto que hace que la barra no mienta demasiado en ningún momento.

## Lo que no se inventa

Una fase sin total conocido —leer un documento, por ejemplo— no da
porcentaje: devuelve el principio de su tramo y la vista enseña una barra
indeterminada. Es mejor que fingir un avance que nadie ha medido.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from lightrag import doc_progress

#: Cuánto del total ocupa cada fase de una indexación, en tanto por uno.
PESOS: dict[str, float] = {
    doc_progress.PARSE: 0.08,
    doc_progress.ANALYZE: 0.37,
    doc_progress.EXTRACT: 0.40,
    doc_progress.MERGE: 0.15,
}

#: Dónde empieza el tramo de cada fase (la suma de las anteriores).
COMIENZOS: dict[str, float] = {}
_acumulado = 0.0
for _fase in (
    doc_progress.PARSE,
    doc_progress.ANALYZE,
    doc_progress.EXTRACT,
    doc_progress.MERGE,
):
    COMIENZOS[_fase] = _acumulado
    _acumulado += PESOS[_fase]

#: Qué se está haciendo, dicho para quien mira. ``{hechos}`` y ``{total}``
#: solo aparecen cuando el motor sabe cuántos elementos hay.
ETIQUETAS: dict[str, tuple[str, str]] = {
    doc_progress.PARSE: ("Leyendo el documento…", "Leyendo el documento…"),
    doc_progress.ANALYZE: (
        "Analizando tablas e imágenes…",
        "Analizando tablas e imágenes {hechos}/{total}",
    ),
    doc_progress.EXTRACT: (
        "Extrayendo entidades…",
        "Extrayendo {hechos}/{total} fragmentos",
    ),
    doc_progress.MERGE: (
        "Uniendo el grafo…",
        "Uniendo el grafo {hechos}/{total}",
    ),
    doc_progress.DELETE: (
        "Borrando de la memoria…",
        "Borrando {hechos}/{total} entidades y relaciones",
    ),
}

#: Estados del motor que, sin contador todavía, ya dicen algo.
POR_ESTADO: dict[str, str] = {
    "pending": doc_progress.PARSE,
    "parsing": doc_progress.PARSE,
    "analyzing": doc_progress.ANALYZE,
    "processing": doc_progress.EXTRACT,
}


def _fraccion(hechos: int, total: int) -> Optional[float]:
    if total <= 0:
        return None
    return max(0.0, min(1.0, hechos / total))


def porcentaje(fase: str, hechos: int, total: int) -> Optional[int]:
    """0-100 dentro del documento, o ``None`` si esa fase no sabe cuánto queda."""
    if fase == doc_progress.DELETE:
        parte = _fraccion(hechos, total)
        return None if parte is None else round(parte * 100)
    if fase not in PESOS:
        return None
    parte = _fraccion(hechos, total)
    base = COMIENZOS[fase] * 100
    if parte is None:
        return round(base)
    return round((COMIENZOS[fase] + PESOS[fase] * parte) * 100)


def etiqueta(fase: str, hechos: int, total: int) -> str:
    """«Analizando tablas e imágenes 12/57», o la frase sin números."""
    sin_numeros, con_numeros = ETIQUETAS.get(fase, ("Trabajando…", "{hechos}/{total}"))
    if total <= 0:
        return sin_numeros
    return con_numeros.format(hechos=hechos, total=total)


def fila(doc_id: str, entrada: Mapping[str, Any]) -> dict[str, Any]:
    """Lo que la vista necesita de un documento en marcha."""
    fase = str(entrada.get("phase") or "")
    hechos = int(entrada.get("done") or 0)
    total = int(entrada.get("total") or 0)
    return {
        "doc_id": doc_id,
        "phase": fase,
        "done": hechos,
        "total": total,
        "label": etiqueta(fase, hechos, total),
        "percent": porcentaje(fase, hechos, total),
    }


def filas(
    pipeline_status: Any, activos: Optional[Mapping[str, str]] = None
) -> list[dict[str, Any]]:
    """Una fila por documento en marcha, con su fase y su porcentaje.

    ``activos`` es ``{doc_id: estado}`` de los documentos que el motor dice
    que están en marcha. Sirve para dos cosas:

    * **Descartar lo viejo.** Una entrada de progreso puede sobrevivir a su
      documento (dos documentos a la vez pueden pisarse la escritura); si el
      documento ya no está en marcha, su avance no se enseña.
    * **Decir algo cuando aún no hay contador.** Un documento recién
      encolado o en la fase de lectura no tiene números todavía, pero su
      estado ya dice en qué anda.
    """
    avances = doc_progress.snapshot(pipeline_status)
    activos = dict(activos or {})
    salida: list[dict[str, Any]] = []

    for doc_id, entrada in avances.items():
        fase = str(entrada.get("phase") or "")
        # El borrado no pasa por doc_status como «en marcha», así que se
        # enseña siempre que el motor lo esté publicando.
        if fase != doc_progress.DELETE and doc_id not in activos:
            continue
        salida.append(fila(doc_id, entrada))

    conocidos = {f["doc_id"] for f in salida}
    for doc_id, estado in activos.items():
        if doc_id in conocidos:
            continue
        fase = POR_ESTADO.get(str(estado), doc_progress.PARSE)
        salida.append(fila(doc_id, {"phase": fase}))

    salida.sort(key=lambda f: f["doc_id"])
    return salida


__all__ = [
    "COMIENZOS",
    "ETIQUETAS",
    "PESOS",
    "POR_ESTADO",
    "etiqueta",
    "fila",
    "filas",
    "porcentaje",
]
