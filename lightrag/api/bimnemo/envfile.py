"""Lectura y escritura del ``.env`` desde la configuración de BIMNEMO.

El ``.env`` es del usuario, no nuestro: puede tener decenas de ajustes que
BIMNEMO ni enseña, comentarios que explican por qué algo está puesto, y un
orden que significa algo para quien lo escribió. La regla es una sola:

    **Guardar solo cambia las claves que se piden. Todo lo demás se conserva
    byte a byte: comentarios, orden, líneas en blanco y claves desconocidas.**

Por eso esto no usa ``dotenv.set_key`` ni reescribe el fichero desde un
diccionario: recorre las líneas y sustituye en el sitio. Una clave que no
existía se añade al final, bajo una cabecera que dice quién la puso.

La escritura es atómica (fichero temporal + ``os.replace``) y deja una copia
de seguridad. Un ``.env`` a medio escribir deja el motor sin arrancar, y el
usuario sin forma evidente de arreglarlo.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

# Cabecera bajo la que se agrupan las claves que BIMNEMO añade por primera vez.
APPENDED_HEADER = "# --- Añadido por la configuración de BIMNEMO ---"

# `export FOO=bar`, `FOO = bar`, `FOO=bar  # comentario`
_ASSIGNMENT = re.compile(r"^(\s*)(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)(\s*)=(.*)$")

# Claves cuyo valor nunca se devuelve al navegador. Se informa de si están
# puestas, jamás de su contenido: la pantalla de configuración se puede abrir
# desde cualquier ventana y una clave de API no debe viajar sin necesidad.
SECRET_KEYS = frozenset(
    {
        "LLM_BINDING_API_KEY",
        "EMBEDDING_BINDING_API_KEY",
        "RERANK_BINDING_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_EMBEDDING_API_KEY",
        "LIGHTRAG_API_KEY",
        "TOKEN_SECRET",
        "AWS_SECRET_ACCESS_KEY",
        "POSTGRES_PASSWORD",
        "NEO4J_PASSWORD",
        "REDIS_URI",
        "MONGO_URI",
    }
)

# Valor centinela que la vista manda cuando el usuario NO tocó el campo de la
# clave. Sin esto, guardar la configuración con el campo enmascarado borraría
# la clave existente — el fallo clásico de este tipo de formularios.
UNCHANGED = "__BIMNEMO_SIN_CAMBIOS__"


def _strip_inline_comment(raw: str) -> tuple[str, str]:
    """Separa el valor de un comentario al final de la línea.

    Solo se considera comentario una almohadilla fuera de comillas. Un valor
    como ``clave#123`` o ``"a # b"`` no lleva comentario, y tratarlo como si
    lo llevara mutilaría el valor.
    """
    value = raw
    quote: str | None = None
    for index, char in enumerate(raw):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or raw[index - 1].isspace()):
            return raw[:index].rstrip(), raw[index:]
    return value.strip(), ""


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _quote_if_needed(value: str) -> str:
    """Entrecomilla solo cuando hace falta, para no ensuciar el fichero."""
    if value == "":
        return ""
    if any(ch.isspace() for ch in value) or any(ch in value for ch in "#\"'"):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def read_env(path: Path) -> dict[str, str]:
    """Todas las claves del ``.env``, sin resolver variables ni expandir nada.

    Ante una clave repetida gana **la última**, que es lo que hacen
    python-dotenv y el propio arranque de LightRAG. Devolver la primera daría
    una vista que no coincide con lo que el motor acaba usando.
    """
    values: dict[str, str] = {}
    if not path.is_file():
        return values

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGNMENT.match(line)
        if not match:
            continue
        key = match.group(2)
        raw_value, _ = _strip_inline_comment(match.group(4))
        values[key] = _unquote(raw_value)

    return values


def public_view(values: dict[str, str]) -> dict[str, object]:
    """La vista que se manda al navegador, con los secretos enmascarados."""
    public: dict[str, object] = {}
    for key, value in values.items():
        if key in SECRET_KEYS:
            public[key] = {"secret": True, "set": bool(value)}
        else:
            public[key] = value
    return public


def write_env(path: Path, updates: dict[str, str | None]) -> list[str]:
    """Aplica ``updates`` al ``.env`` conservando todo lo demás.

    * Un valor de texto reemplaza el de la clave, en su línea, manteniendo
      sangrado y comentario al final.
    * ``None`` **comenta** la línea en lugar de borrarla, para que el usuario
      vea qué había y pueda devolverlo a mano.
    * Una clave nueva se añade al final, bajo :data:`APPENDED_HEADER`.

    Devuelve la lista de claves realmente modificadas.
    """
    updates = {k: v for k, v in updates.items() if v != UNCHANGED}
    if not updates:
        return []

    original = (
        path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    )
    lines = original.splitlines()
    # Un fichero que no acaba en salto de línea no debe perder su última línea
    # ni pegarse con lo que añadamos después.
    trailing_newline = original.endswith("\n") or not original

    pending = dict(updates)
    changed: list[str] = []
    result: list[str] = []

    for line in lines:
        match = _ASSIGNMENT.match(line)
        if not match:
            result.append(line)
            continue

        key = match.group(2)
        if key not in pending:
            result.append(line)
            continue

        new_value = pending.pop(key)
        indent, spacing = match.group(1), match.group(3)
        _, comment = _strip_inline_comment(match.group(4))
        suffix = f"  {comment.strip()}" if comment else ""

        if new_value is None:
            result.append(f"{indent}# {line.lstrip()}")
        else:
            result.append(
                f"{indent}{key}{spacing}={_quote_if_needed(new_value)}{suffix}"
            )
        changed.append(key)

    additions = {k: v for k, v in pending.items() if v is not None}
    if additions:
        if result and result[-1].strip():
            result.append("")
        if APPENDED_HEADER not in original:
            result.append(APPENDED_HEADER)
        for key, value in additions.items():
            result.append(f"{key}={_quote_if_needed(value)}")
            changed.append(key)

    if not changed:
        return []

    content = "\n".join(result)
    if trailing_newline:
        content += "\n"

    _atomic_write(path, content)
    return changed


def _atomic_write(path: Path, content: str) -> None:
    """Escribe el fichero sin dejarlo nunca a medias, con copia previa.

    El temporal se crea en el MISMO directorio a propósito: ``os.replace`` solo
    es atómico dentro del mismo sistema de ficheros, y el temporal del sistema
    puede estar en otra unidad — en Windows, muy a menudo lo está.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_file():
        try:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bimnemo.bak"))
        except OSError:
            # Sin copia de seguridad se sigue: la escritura es atómica de todos
            # modos, y negarse a guardar por no poder copiar sería peor.
            pass

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


__all__ = [
    "APPENDED_HEADER",
    "SECRET_KEYS",
    "UNCHANGED",
    "public_view",
    "read_env",
    "write_env",
]
