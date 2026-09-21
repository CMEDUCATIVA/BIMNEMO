"""El modelo de embeddings con el que se hicieron las memorias, y cómo volver a él.

Los vectores de una memoria solo sirven con el modelo que los calculó. Si en
Configuración IA se cambia el de embeddings —de OpenAI a Gemini, por
ejemplo— y se reinicia, el motor **se niega a arrancar**
(``VectorSpaceMismatchError``): consultar vectores de otro modelo daría
resultados vacíos o, peor, equivocados con toda seguridad.

Negarse es lo correcto, pero la ventana corre sin consola y el usuario solo
veía que BIMNEMO no abría. Este módulo es lo que falta para salir de ahí:

* Al guardar un modelo de embeddings distinto, se apunta aparte el que estaba
  funcionando (:func:`recordar`), porque la copia ``.env.bimnemo.bak`` se
  pisa en cada guardado y no sirve para volver atrás.
* Al fallar el arranque, :func:`desajuste` reconoce el error en el registro
  del motor y :func:`restaurar` devuelve el ``.env`` al modelo apuntado.

No importa nada pesado: lo usa el lanzador antes de que exista el motor.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from lightrag.api.bimnemo.envfile import read_env, write_env

#: Lo que define el espacio de los vectores, y con qué se llega a él.
CLAVES = (
    "EMBEDDING_BINDING",
    "EMBEDDING_BINDING_HOST",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "EMBEDDING_BINDING_API_KEY",
)

#: Si cambia alguna de éstas, los vectores guardados dejan de servir.
_DEFINEN_EL_ESPACIO = ("EMBEDDING_BINDING", "EMBEDDING_MODEL", "EMBEDDING_DIM")

#: Junto al ``.env``: lleva la clave de API igual que él, así que se queda en
#: la misma carpeta y con el mismo cuidado (fuera del repositorio y del zip).
NOMBRE = ".env.embedding-anterior"

#: Cómo lo dice el motor: «… (model 'text-embedding-3-large' ->
#: 'gemini-embedding-001') …».
_MODELOS = re.compile(r"model '([^']*)' -> '([^']*)'")


def ruta(env: Path) -> Path:
    return env.with_name(NOMBRE)


def cambia_el_espacio(actuales: dict[str, str], cambios: dict[str, Optional[str]]) -> bool:
    """¿Estos cambios dejan inservibles los vectores que ya hay?"""
    return any(
        clave in cambios and (cambios[clave] or "") != actuales.get(clave, "")
        for clave in _DEFINEN_EL_ESPACIO
    )


def recordar(env: Path, cambios: dict[str, Optional[str]]) -> bool:
    """Apunta el modelo de embeddings actual antes de cambiarlo por otro.

    Solo se apunta **el que el motor está usando de verdad**: si el ``.env``
    ya tiene guardado un cambio que no se ha aplicado, lo que hay en el
    fichero no ha calculado ningún vector, y apuntarlo borraría la única
    salida buena. Tampoco se apunta si no hay modelo que recordar.
    """
    actuales = read_env(env)
    if not cambia_el_espacio(actuales, cambios):
        return False
    if not actuales.get("EMBEDDING_MODEL"):
        return False
    if any(
        os.getenv(clave) is not None and os.getenv(clave) != actuales.get(clave, "")
        for clave in _DEFINEN_EL_ESPACIO
    ):
        return False
    write_env(ruta(env), {c: actuales[c] for c in CLAVES if actuales.get(c)})
    return True


def anterior(env: Path) -> dict[str, str]:
    """El modelo apuntado, o vacío si no hay ninguno."""
    fichero = ruta(env)
    if not fichero.is_file():
        return {}
    return {c: v for c, v in read_env(fichero).items() if c in CLAVES}


def desajuste(registro: str) -> Optional[tuple[str, str]]:
    """``(modelo de los vectores, modelo configurado)`` si el arranque falló por eso."""
    if "VectorSpaceMismatchError" not in registro:
        return None
    encontrado = _MODELOS.search(registro)
    return encontrado.groups() if encontrado else ("", "")


def puede_volver(env: Path, modelo_de_los_vectores: str) -> bool:
    """¿Hay apuntado un modelo, y es el de los vectores?"""
    guardado = anterior(env).get("EMBEDDING_MODEL", "")
    return bool(guardado) and (
        not modelo_de_los_vectores or guardado == modelo_de_los_vectores
    )


def restaurar(env: Path) -> list[str]:
    """Devuelve el ``.env`` al modelo apuntado. Lo demás no se toca.

    Lo que el apuntado no tenía —un host, por ejemplo— se comenta en vez de
    dejarse: un host de Gemini con un modelo de OpenAI tampoco arrancaría.
    """
    guardado = anterior(env)
    if not guardado:
        return []
    return write_env(env, {c: guardado.get(c) for c in CLAVES})


def hay_vectores(rag_storage: Path) -> bool:
    """¿Alguna memoria tiene ya vectores calculados?

    Mira el principio de cada ``vdb_*.json``: uno vacío es
    ``{"embedding_dim": N, "data": []…``. Leer el fichero entero sería
    cargar decenas de megas para contestar sí o no.
    """
    if not rag_storage.is_dir():
        return False
    for fichero in rag_storage.glob("**/vdb_*.json"):
        try:
            with fichero.open("r", encoding="utf-8", errors="replace") as f:
                inicio = f.read(512)
        except OSError:
            continue
        if re.search(r'"data":\s*\[\s*\{', inicio):
            return True
    return False
