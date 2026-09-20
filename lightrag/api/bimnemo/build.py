"""Huella de la versión de la interfaz que el servidor está sirviendo.

Existe por un fallo que se repitió tres veces y siempre parecía otra cosa: se
actualiza BIMNEMO, el servidor sirve los ficheros nuevos, y una ventana ya
abierta sigue ejecutando el JavaScript anterior. No es caché —los ficheros se
sirven con ``Cache-Control: no-cache``— sino algo más simple: **una página que
no se recarga no vuelve a pedir sus módulos**. Quedan en memoria hasta que
alguien pulsa recargar.

Desde fuera es indistinguible de un fallo del programa: el usuario ve una
lista desactualizada, o un botón que «no aparece», y no tiene forma de saber
que está mirando código viejo.

La huella resuelve eso: la página se queda con la que había al cargar y la
compara cada cierto tiempo. Si cambia, es que hay una versión nueva en disco y
lo dice, con un botón para recargar.

Se calcula sobre la fecha de modificación y el tamaño de cada fichero de la
interfaz. No es criptográfico ni le hace falta: solo tiene que cambiar cuando
cambie algo, y eso lo cumple.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from functools import lru_cache
from pathlib import Path

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

#: Extensiones que componen la interfaz. Una imagen nueva no justifica pedirle
#: al usuario que recargue; un módulo o una hoja de estilos, sí.
TRACKED_SUFFIXES = frozenset({".html", ".js", ".css"})


def _ui_dir() -> Path:
    return Path(__file__).parent / "ui"


def compute_fingerprint(directory: Path | None = None) -> str:
    """Huella corta de los ficheros de interfaz que hay en disco.

    Se recalcula en cada llamada a propósito: el objetivo es detectar cambios
    en caliente, y una huella cacheada al arrancar nunca los vería. El coste
    es recorrer unas veinte entradas de directorio.
    """
    root = directory or _ui_dir()
    if not root.is_dir():
        return "sin-interfaz"

    digest = hashlib.sha256()
    try:
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in TRACKED_SUFFIXES:
                continue
            try:
                stat = path.stat()
            except OSError:
                # Un fichero que desaparece a mitad del recorrido no debe
                # tumbar la comprobación; simplemente no cuenta.
                continue
            digest.update(path.name.encode("utf-8", "replace"))
            digest.update(f"{stat.st_mtime_ns}:{stat.st_size}".encode("ascii"))
    except OSError:
        return "sin-interfaz"

    return digest.hexdigest()[:16]


@lru_cache(maxsize=1)
def startup_fingerprint() -> str:
    """La huella que había al arrancar el proceso.

    Sirve para distinguir «el usuario tiene código viejo» de «el servidor
    tiene código viejo»: si esta difiere de la actual, los ficheros cambiaron
    desde que arrancó el motor.
    """
    return compute_fingerprint()


__all__ = ["TRACKED_SUFFIXES", "compute_fingerprint", "startup_fingerprint"]
