"""Poner números, fechas y estados en palabras.

Es el equivalente de `ui/js/format.js`, y existe por lo mismo: **las dos
interfaces tienen que decir lo mismo**. Un fichero que en la web sale como
«4.9 MB · En memoria» y en la ventana nativa como «5013504 · processed» son
dos productos, no uno.

Las tablas de aquí se corresponden una a una con las de `format.js`. Al
cambiar una hay que cambiar la otra; no hay forma de compartirlas, porque una
vive en el navegador y la otra en Python.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

#: Cómo se dice en castellano cada estado del motor. Son los mismos rótulos
#: que `STATUS_LABELS` en `format.js`.
ESTADOS: dict[str, str] = {
    "pending": "En cola",
    "parsing": "Extrayendo",
    "analyzing": "Analizando",
    "processing": "Indexando",
    "preprocessed": "Preprocesado",
    "processed": "En memoria",
    "failed": "Fallido",
    # Tampoco es un estado del motor: es un «fallido» que en realidad es una
    # copia de otro archivo que ya está en la memoria. No falta nada.
    "duplicado": "Copia repetida",
    # Otro «fallido» que no lo es: lo paró quien usa BIMNEMO, con el botón de
    # pausa, y se reanuda con ⟳.
    "pausado": "En pausa",
    # No es un estado del motor: lo pone la pantalla mientras espera a que el
    # borrado termine, para que la fila no finja que no está pasando nada.
    "deleting": "Borrando…",
}

#: Estados en los que el motor todavía tiene trabajo con ese documento. Es lo
#: que decide si se sigue sondeando y si la fila lleva barra de avance.
EN_CURSO = ("pending", "parsing", "analyzing", "processing", "deleting")

#: Los que el botón de pausa puede parar: todo lo que la tubería tiene entre
#: manos. Un borrado no, que no es una indexación.
PAUSABLES = ("pending", "parsing", "analyzing", "processing")


def estado(bruto: Any) -> str:
    """El estado en palabras. Sin estado, «Sin indexar».

    Lo que no esté en la tabla se devuelve **tal cual**: si el motor añade un
    estado nuevo, es mejor enseñar su nombre en crudo que inventarse uno o
    dejar la celda vacía.
    """
    if not bruto:
        return "Sin indexar"
    return ESTADOS.get(str(bruto), str(bruto))


def tamano(octetos: Any) -> str:
    """Bytes en la unidad que se lea de un vistazo."""
    try:
        n = float(octetos)
    except (TypeError, ValueError):
        return "—"
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidad == "GB":
            return f"{n:.0f} {unidad}" if unidad == "B" else f"{n:.1f} {unidad}"
        n /= 1024
    return "—"


def numero(valor: Any) -> str:
    """Un entero con los miles separados por puntos, como se escribe aquí."""
    try:
        return f"{int(valor):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def fecha(segundos: Any) -> str:
    """Una marca de tiempo de Unix en fecha y hora local.

    El motor manda `st_mtime`, que son segundos desde 1970 en coma flotante.
    Un cero o un negativo no son una fecha: son «no se sabe», y eso se dice
    con una raya, no con el 1 de enero de 1970.
    """
    try:
        n = float(segundos)
    except (TypeError, ValueError):
        return "—"
    if n <= 0:
        return "—"
    try:
        return datetime.fromtimestamp(n).strftime("%d/%m/%Y, %H:%M")
    except (OverflowError, OSError, ValueError):
        return "—"


__all__ = ["EN_CURSO", "ESTADOS", "PAUSABLES", "estado", "fecha", "numero", "tamano"]
