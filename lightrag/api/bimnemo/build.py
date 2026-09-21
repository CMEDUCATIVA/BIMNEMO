"""Identidad del proceso del motor.

Queda de lo que fue la «huella de la interfaz web»: la web detectaba así que
había ficheros nuevos en disco. Sin web no hay ficheros que vigilar, pero la
otra mitad sigue haciendo falta: saber **qué proceso** está contestando, que
es como la ventana sabe que el motor ha vuelto tras un reinicio.
"""

from __future__ import annotations

import time
import uuid

#: Identidad de **este** proceso, fijada al importar el módulo.
#:
#: Existe para una pregunta que la huella de ficheros no puede contestar:
#: «¿el motor que me está respondiendo es el de antes o ya es el nuevo?».
#: Reiniciar sin tocar ficheros deja la huella igual, así que no distingue un
#: proceso de otro.
#:
#: Importa porque al reiniciar **el proceso moribundo todavía responde**: la
#: ruta de reinicio espera medio segundo antes de matarse para que la
#: respuesta salga por el socket. Quien espere a que `/health` conteste vuelve
#: demasiado pronto y recarga contra un motor que se está cerrando.
_BOOT_ID = uuid.uuid4().hex[:12]
_BOOT_AT = time.time()


def boot_id() -> str:
    """Identificador de este arranque. Cambia con cada proceso nuevo."""
    return _BOOT_ID


def boot_at() -> float:
    """Momento en que arrancó este proceso, en segundos desde la época."""
    return _BOOT_AT


__all__ = ["boot_at", "boot_id"]
