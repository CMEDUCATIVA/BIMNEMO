"""Catálogo BIMNEMO: de una extensión de fichero a su categoría y su tipo.

Esta clasificación es un concepto **de BIMNEMO**, no del motor. No decide qué
parser trata el fichero — eso lo sigue resolviendo ``lightrag.parser.routing``
a partir de ``LIGHTRAG_PARSER`` — solo decide bajo qué tarjeta se cuenta en el
panel. Por eso una extensión puede estar aquí y no ser todavía ingerible por el
motor: el panel lo muestra, y ``supported_extensions`` (vivo, del registro de
parsers) es quien dice si se puede subir.

## La regla: una categoría existe si BIMNEMO, tal y como se instala, puede leer alguno de sus formatos

Comprobable, no opinable: los motores que funcionan **sin nada más**
—``legacy`` y ``native``— y lo que aceptan. Los otros dos, ``mineru`` y
``docling``, piden un servicio HTTP aparte (``MINERU_LOCAL_ENDPOINT``,
``DOCLING_ENDPOINT``) que no viaja en el paquete: contar con ellos sería
fiar una tarjeta del panel a algo que el usuario no tiene.

Por eso no hay «Modelo BIM» ni «Plano CAD» —**ningún motor acepta IFC, RVT,
DWG ni DXF, en ninguna configuración**— y tampoco «Imagen»: leerlas es
justamente lo que hacen MinerU y Docling, y sin su servicio no entra ninguna.
La subida las rechaza igual que a un DWG.

Una tarjeta para algo que el programa no admite promete lo que no puede
cumplir, y era una contradicción con la zona de arrastre, que a dos dedos de
ahí enumera lo que sí entra. Un fichero de esos, copiado a mano en la
carpeta, se cuenta en «Otros», que es la verdad: está guardado y no se puede
indexar.

Si algún día el paquete lleva MinerU o Docling dentro, «Imagen» vuelve: es
añadir la categoría y sus extensiones aquí, y la prueba de `tests/bimnemo/
test_catalog.py` cambia con ella.

El panel enseña «N / <cuántas categorías>», tomando el denominador del propio
catálogo; añadir o quitar una no rompe la vista. El color de cada una sale de
la paleta del Lookbook y se declara aquí para que exista una sola fuente: el
nombre del token viaja a la ventana y ``nativo/tema.py`` lo resuelve.
"""

from __future__ import annotations

from typing import NamedTuple


class Category(NamedTuple):
    """Una categoría del catálogo, tal y como la consume el panel."""

    key: str
    label: str
    icon: str  # nombre del icono; ``nativo/iconos.py`` lo traduce a Bootstrap
    color: str  # token de color; ``nativo/tema.py`` lo resuelve a un valor


# Orden de declaración = orden de presentación en el panel.
CATEGORIES: tuple[Category, ...] = (
    Category("document", "Documento", "file-text", "sky"),
    Category("spreadsheet", "Hoja de cálculo", "table", "teal"),
    Category("presentation", "Presentación", "presentation", "rose"),
    Category("data", "Datos", "database", "amber"),
    Category("text", "Texto y código", "code", "slate"),
)

CATEGORIES_BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}

# Categoría de descarte. No está en CATEGORIES a propósito: no ocupa una de las
# ocho ranuras del panel y no debe inflar el contador de categorías en uso.
UNKNOWN = Category("other", "Otros", "file", "slate")


# Extensión (sin punto, en minúsculas) -> clave de categoría.
#
# Un fichero sin extensión, o con una que no está aquí, cae en UNKNOWN. No se
# adivina por contenido: un panel que miente sobre lo que hay almacenado es
# peor que uno que admite no saberlo.
_EXTENSION_MAP: dict[str, str] = {}


def _register(category_key: str, *extensions: str) -> None:
    """Asocia extensiones a una categoría, rechazando duplicados.

    Un duplicado es siempre un error de edición del catálogo — dos categorías
    reclamando la misma extensión — y el reparto resultante dependería del
    orden de las llamadas. Falla al importar, que es cuando se puede arreglar.
    """
    for extension in extensions:
        normalized = extension.lower().lstrip(".")
        if normalized in _EXTENSION_MAP:
            raise ValueError(
                f"BIMNEMO: la extensión {normalized!r} ya está asignada a "
                f"{_EXTENSION_MAP[normalized]!r}; no puede pertenecer también a "
                f"{category_key!r}"
            )
        _EXTENSION_MAP[normalized] = category_key


_register(
    "document",
    # Lee el motor: pdf, docx, odt, rtf y epub. Los demás son de la misma
    # familia y se clasifican igual si aparecen en la carpeta.
    "pdf",
    "doc",
    "docx",
    "dotx",
    "odt",
    "rtf",
    "pages",
    "epub",
)
_register(
    "spreadsheet",
    "xlsx",
    "xls",
    "xlsm",
    "xltx",
    "ods",
    "numbers",
    "csv",
    "tsv",
)
_register(
    "presentation",
    "pptx",
    "ppt",
    "potx",
    "odp",
    "key",
)
_register(
    "data",
    "json",
    "jsonl",
    "xml",
    "yaml",
    "yml",
    "sql",
    "db",
    "sqlite",
    "parquet",
    "toml",
    "ini",
    "cfg",
    "conf",
    "properties",
)
_register(
    "text",
    # Texto plano y marcado.
    "txt",
    "md",
    "mdx",
    "markdown",
    "rst",
    "log",
    "tex",
    "textpack",
    "html",
    "htm",
    "xhtml",
    # Y código, que el motor lee como texto.
    "py",
    "js",
    "ts",
    "tsx",
    "jsx",
    "java",
    "c",
    "h",
    "cpp",
    "hpp",
    "cs",
    "go",
    "rb",
    "rs",
    "php",
    "sh",
    "bat",
    "ps1",
    "swift",
    "css",
    "scss",
    "less",
)


def normalize_extension(filename: str) -> str:
    """Extensión en minúsculas y sin punto, o cadena vacía si no tiene.

    Trabaja sobre el nombre, no sobre el sistema de ficheros, para que sirva
    igual con una ruta que con el nombre que llega en una subida.

    LightRAG admite pistas de parser en el propio nombre (``img.[mineru].png``),
    así que la extensión útil es siempre el ÚLTIMO segmento: tomar el primero
    clasificaría ese fichero como categoría ``[mineru]``.
    """
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower().strip()


def categorize(filename: str) -> Category:
    """Categoría a la que pertenece un fichero por su nombre."""
    extension = normalize_extension(filename)
    if not extension:
        return UNKNOWN
    key = _EXTENSION_MAP.get(extension)
    return CATEGORIES_BY_KEY[key] if key is not None else UNKNOWN


def file_type_label(filename: str) -> str:
    """Etiqueta corta del tipo, la que se enseña en la columna «Tipo».

    Es la extensión en mayúsculas — ``PDF``, ``IFC``, ``DWG`` — porque es como
    la nombra quien trabaja con estos ficheros. Sin extensión, «Sin tipo».
    """
    extension = normalize_extension(filename)
    return extension.upper() if extension else "Sin tipo"


def known_extensions() -> tuple[str, ...]:
    """Todas las extensiones que el catálogo sabe clasificar, ordenadas."""
    return tuple(sorted(_EXTENSION_MAP))


def categories_payload() -> list[dict[str, str]]:
    """El catálogo tal y como lo consume el panel."""
    return [
        {
            "key": category.key,
            "label": category.label,
            "icon": category.icon,
            "color": category.color,
        }
        for category in CATEGORIES
    ]


__all__ = [
    "CATEGORIES",
    "CATEGORIES_BY_KEY",
    "UNKNOWN",
    "Category",
    "categories_payload",
    "categorize",
    "file_type_label",
    "known_extensions",
    "normalize_extension",
]
