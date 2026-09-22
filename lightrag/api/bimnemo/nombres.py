"""¿Cabe este nombre de archivo? Y si no, uno que sí quepa.

Existe por diez bases estándar que fallaron al indexar con «el nombre del
archivo es demasiado largo». Windows no admite rutas de más de 260
caracteres, y al leer un documento el motor crea::

    <entrada>\\__parsed__\\NOMBRE.docx.parsed\\NOMBRE.blocks.assets\\<imagen>

El nombre va **dos veces**. Con la carpeta de entrada de una instalación
normal (87 caracteres) caben unos 57: el de 57 se indexó y el de 61 no.

## El límite no es un número fijo

Depende de la carpeta del usuario de Windows y del nombre de la memoria. Por
eso :func:`maximo` recibe la longitud de la ruta real, que da el motor, en vez
de fijar «50» para todos: fallaría en unos equipos y sobraría en otros.

Sin importaciones de LightRAG a propósito: lo usan el motor y la ventana.
"""

from __future__ import annotations

import re

#: Lo que Windows cuenta como ruta máxima, sin el terminador.
RUTA_MAXIMA = 259
#: Lo que el lector añade alrededor de las dos copias del nombre:
#: «.parsed\\» y «.blocks.assets\\».
ENVOLTORIO = len(".parsed\\") + len(".blocks.assets\\")
#: Lo que se reserva para el archivo de más adentro (una imagen del documento).
#: Calibrado con el caso real: 57 caracteres entraron, 61 no.
MARGEN_INTERIOR = 40

#: Caracteres que Windows no admite en un nombre de archivo.
PROHIBIDOS = '\\/:*?"<>|'
#: Nombres que Windows reserva para dispositivos, con cualquier extensión.
RESERVADOS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

#: Palabras que se pueden quitar sin perder qué documento es.
_VACIAS = frozenset(
    "a al con de del el en la las lo los para por que un una uno unos unas y o".split()
)


def extension(nombre: str) -> str:
    """«.docx», o «» si no tiene."""
    punto = nombre.rfind(".")
    return nombre[punto:] if punto > 0 else ""


def maximo(raiz_leidos: int, ext: str) -> int:
    """Cuántos caracteres puede tener el nombre, extensión incluida.

    ``raiz_leidos`` es la longitud de ``<entrada>\\__parsed__\\`` en ese
    equipo y esa memoria. La segunda copia del nombre va sin extensión, por
    eso se suma una vez la de ``ext``.
    """
    return max(
        (RUTA_MAXIMA - raiz_leidos - ENVOLTORIO - MARGEN_INTERIOR + len(ext)) // 2, 0
    )


def problemas(
    nombre: str, limite: int, existentes: frozenset[str] = frozenset()
) -> list[str]:
    """Por qué ``nombre`` no sirve, en castellano. Vacía si sirve.

    ``existentes`` son los nombres que ya hay en la memoria: subir uno igual
    pisaría el otro. Se comparan sin mayúsculas, como hace Windows.
    """
    fallos: list[str] = []
    if nombre.lower() in {e.lower() for e in existentes}:
        fallos.append("Ya hay un archivo con ese nombre en esta memoria.")
    base = nombre[: -len(extension(nombre))] if extension(nombre) else nombre
    if not base.strip():
        fallos.append("El nombre no puede estar vacío.")
    if len(nombre) > limite:
        fallos.append(
            f"Tiene {len(nombre)} caracteres y en esta memoria caben {limite}."
        )
    malos = sorted({c for c in nombre if c in PROHIBIDOS})
    if malos:
        fallos.append(f"Windows no admite: {' '.join(malos)}")
    if nombre != nombre.rstrip(" ."):
        fallos.append("No puede terminar en espacio ni en punto.")
    if base.strip().upper() in RESERVADOS:
        fallos.append(f"«{base}» es un nombre reservado de Windows.")
    return fallos


def sugerir(nombre: str, limite: int, existentes: frozenset[str] = frozenset()) -> str:
    """Un nombre que quepa, parecido al original. Solo una propuesta.

    1. Se quitan los caracteres prohibidos y las palabras vacías («de»,
       «para», «la»…).
    2. Si aún no cabe, se conserva el **código del principio** (lo que lleva
       cifras: «7614342-16») y se llena con las palabras **del final**. En una
       familia de documentos el principio se repite —«bases estándar concurso
       público…»— y lo que distingue a cada uno va al final: «…expertos y
       gerentes», «…mantenimiento vial».
    3. Si choca con uno que ya existe, se numera: «… 2.docx».
    """
    ext = extension(nombre)
    base = nombre[: -len(ext)] if ext else nombre
    base = "".join(c for c in base if c not in PROHIBIDOS).strip(" .")
    cabe = max(limite - len(ext), 1)

    if len(base) > cabe:
        trozos = re.split(r"([-_ ]+)", base)
        palabras = [t for t in trozos[::2] if t and t.lower() not in _VACIAS]
        separador = next((s for s in trozos[1::2] if s), "-")[0]
        base = separador.join(palabras)

    if len(base) > cabe:
        codigo = []
        for palabra in palabras:
            if not any(c.isdigit() for c in palabra):
                break
            codigo.append(palabra)
        resto = palabras[len(codigo) :]
        cola: list[str] = []
        for palabra in reversed(resto):
            candidato = separador.join([*codigo, palabra, *cola])
            if len(candidato) > cabe:
                break
            cola.insert(0, palabra)
        base = separador.join([*codigo, *cola]) or base[:cabe]

    base = base[:cabe].strip(" .-_")
    propuesta = base + ext
    usados = {e.lower() for e in existentes}
    numero = 2
    while propuesta.lower() in usados:
        sufijo = f" {numero}"
        propuesta = base[: cabe - len(sufijo)].rstrip(" .-_") + sufijo + ext
        numero += 1
    return propuesta


__all__ = ["PROHIBIDOS", "extension", "maximo", "problemas", "sugerir"]
