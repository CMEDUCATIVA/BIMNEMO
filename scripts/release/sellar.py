"""Le pone cara e identidad a un ejecutable de Windows.

El paquete de BIMNEMO lleva un intérprete de Python, y un intérprete de
Python se presenta como lo que es: en el Administrador de tareas pone
`pythonw.exe`, con el icono de Python y la descripción «Python». Para quien
usa BIMNEMO eso no es nada — no puede reconocerlo, no sabe si es suyo, y si
algo se queda colgado no tiene ni qué cerrar.

Este guion coge una copia del intérprete y le cambia tres cosas:

    icono          el cuadrado azul de la marca, el mismo de la aplicación
    descripción    «BIMNEMO», que es la columna que se lee de un vistazo
    versión        la que se está publicando

Se hace con la API de recursos de Windows (`BeginUpdateResource`), sin
herramientas externas ni dependencias nuevas: solo `ctypes`.

## Por qué se borran los recursos y se vuelven a poner

`BeginUpdateResource` admite conservar lo que había. No se usa así: mezclar
iconos nuevos con los viejos deja grupos sueltos y Windows puede seguir
enseñando el de Python. Se borra todo y se reconstruye.

Pero borrar todo **se lleva también el manifiesto**, y el manifiesto no es
decorativo: dice que el programa es consciente de la densidad de píxeles y
que admite rutas largas. Sin él la ventana sale borrosa en pantallas 4K. Así
que se lee del original antes de borrar y se vuelve a escribir.
"""

from __future__ import annotations

import ctypes
import struct
import sys
from ctypes import wintypes
from pathlib import Path

RT_ICON = 3
RT_GROUP_ICON = 14
RT_VERSION = 16
RT_MANIFEST = 24

#: Español de España. Da igual cuál sea mientras haya **una**: Windows
#: recurre a la que encuentre si no hay coincidencia con su idioma.
IDIOMA = 0x0C0A
#: 1200 = Unicode. Es la única página de códigos sensata hoy.
PAGINA = 0x04B0

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _entero_como_nombre(valor: int) -> wintypes.LPCWSTR:
    """Un identificador numérico donde la API espera un nombre.

    Es el `MAKEINTRESOURCE` de la API de C: los recursos se nombran con una
    cadena o con un número, y el número viaja disfrazado de puntero.
    """
    return ctypes.cast(ctypes.c_void_p(valor), wintypes.LPCWSTR)


def _preparar_api() -> None:
    _kernel32.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    _kernel32.BeginUpdateResourceW.restype = wintypes.HANDLE
    _kernel32.UpdateResourceW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.WORD,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _kernel32.UpdateResourceW.restype = wintypes.BOOL
    _kernel32.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    _kernel32.EndUpdateResourceW.restype = wintypes.BOOL
    _kernel32.LoadLibraryExW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    _kernel32.LoadLibraryExW.restype = wintypes.HMODULE
    _kernel32.FindResourceW.argtypes = [
        wintypes.HMODULE,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
    ]
    _kernel32.FindResourceW.restype = wintypes.HANDLE
    _kernel32.SizeofResource.argtypes = [wintypes.HMODULE, wintypes.HANDLE]
    _kernel32.SizeofResource.restype = wintypes.DWORD
    _kernel32.LoadResource.argtypes = [wintypes.HMODULE, wintypes.HANDLE]
    _kernel32.LoadResource.restype = wintypes.HANDLE
    _kernel32.LockResource.argtypes = [wintypes.HANDLE]
    _kernel32.LockResource.restype = wintypes.LPVOID
    _kernel32.FreeLibrary.argtypes = [wintypes.HMODULE]
    _kernel32.FreeLibrary.restype = wintypes.BOOL


def leer_manifiesto(exe: Path) -> bytes | None:
    """El manifiesto que ya trae el ejecutable, para no perderlo."""
    LOAD_LIBRARY_AS_DATAFILE = 0x00000002
    modulo = _kernel32.LoadLibraryExW(str(exe), None, LOAD_LIBRARY_AS_DATAFILE)
    if not modulo:
        return None
    try:
        recurso = _kernel32.FindResourceW(
            modulo, _entero_como_nombre(1), _entero_como_nombre(RT_MANIFEST)
        )
        if not recurso:
            return None
        tamano = _kernel32.SizeofResource(modulo, recurso)
        cargado = _kernel32.LoadResource(modulo, recurso)
        puntero = _kernel32.LockResource(cargado)
        if not puntero or not tamano:
            return None
        return ctypes.string_at(puntero, tamano)
    finally:
        _kernel32.FreeLibrary(modulo)


# ---------------------------------------------------------------------------
# Icono
# ---------------------------------------------------------------------------


def _trocear_ico(ico: Path) -> list[tuple[bytes, bytes]]:
    """Parte un `.ico` en las imágenes que lleva dentro.

    Un `.ico` es un índice seguido de las imágenes. Dentro del ejecutable no
    van así: cada imagen es un recurso `RT_ICON` suelto y el índice es otro
    recurso, `RT_GROUP_ICON`, que las referencia por número. Traducir de un
    formato al otro es todo lo que hace esto.
    """
    datos = ico.read_bytes()
    reservado, tipo, cuantos = struct.unpack_from("<HHH", datos, 0)
    if reservado != 0 or tipo != 1 or cuantos == 0:
        raise SystemExit(f"{ico} no parece un icono de Windows.")

    imagenes: list[tuple[bytes, bytes]] = []
    for indice in range(cuantos):
        (
            ancho,
            alto,
            colores,
            _res,
            planos,
            bits,
            tamano,
            desplazamiento,
        ) = struct.unpack_from("<BBBBHHII", datos, 6 + indice * 16)
        imagen = datos[desplazamiento : desplazamiento + tamano]
        # La entrada del grupo es igual que la del fichero, salvo que en vez
        # del desplazamiento lleva el número del recurso.
        entrada = struct.pack(
            "<BBBBHHIH",
            ancho,
            alto,
            colores,
            0,
            planos,
            bits,
            tamano,
            indice + 1,
        )
        imagenes.append((entrada, imagen))
    return imagenes


# ---------------------------------------------------------------------------
# Información de versión
# ---------------------------------------------------------------------------


def _al_cuatro(datos: bytes) -> bytes:
    return datos + b"\x00" * ((4 - len(datos) % 4) % 4)


def _nodo(clave: str, valor: bytes, tipo: int, largo: int, hijos: bytes) -> bytes:
    """Un nodo del árbol de `VS_VERSIONINFO`.

    Todos tienen la misma forma: longitud, longitud del valor, si el valor es
    texto o binario, la clave, y después el valor y los hijos. Cada pieza
    empieza en múltiplo de cuatro.
    """
    cuerpo = struct.pack("<HHH", 0, largo, tipo)
    cuerpo += clave.encode("utf-16-le") + b"\x00\x00"
    cuerpo = _al_cuatro(cuerpo)
    if valor:
        cuerpo += _al_cuatro(valor)
    cuerpo += hijos
    return struct.pack("<H", len(cuerpo)) + cuerpo[2:]


def _texto(clave: str, valor: str) -> bytes:
    codificado = valor.encode("utf-16-le") + b"\x00\x00"
    # La longitud de un valor de texto se cuenta en caracteres, no en bytes,
    # y el nulo final cuenta.
    return _nodo(clave, codificado, 1, len(codificado) // 2, b"")


def _numeros(version: str) -> tuple[int, int, int, int]:
    partes = version.lstrip("vV").split(".")
    numeros = []
    for parte in partes[:4]:
        digitos = "".join(c for c in parte if c.isdigit())
        numeros.append(int(digitos) if digitos else 0)
    while len(numeros) < 4:
        numeros.append(0)
    return tuple(numeros)  # type: ignore[return-value]


def construir_version(version: str, descripcion: str, nombre: str) -> bytes:
    mayor, menor, parche, compilacion = _numeros(version)
    alto = (mayor << 16) | menor
    bajo = (parche << 16) | compilacion

    fijo = struct.pack(
        "<IIIIIIIIIIIII",
        0xFEEF04BD,  # firma
        0x00010000,  # versión de la estructura
        alto,
        bajo,  # versión del fichero
        alto,
        bajo,  # versión del producto
        0x3F,  # máscara de banderas
        0x00,  # banderas
        0x00040004,  # Windows NT de 32 bits
        0x00000001,  # es una aplicación
        0x00000000,
        0x00000000,
        0x00000000,
    )

    legible = ".".join(str(n) for n in (mayor, menor, parche, compilacion))
    campos = b"".join(
        _texto(clave, valor)
        for clave, valor in (
            ("CompanyName", "CM Educativa"),
            ("FileDescription", descripcion),
            ("FileVersion", legible),
            ("InternalName", nombre),
            ("LegalCopyright", "CM Educativa"),
            ("OriginalFilename", nombre + ".exe"),
            ("ProductName", "BIMNEMO"),
            ("ProductVersion", legible),
        )
    )

    tabla = _nodo(f"{IDIOMA:04X}{PAGINA:04X}", b"", 1, 0, campos)
    cadenas = _nodo("StringFileInfo", b"", 1, 0, tabla)
    traduccion = _nodo(
        "Translation", struct.pack("<HH", IDIOMA, PAGINA), 0, 4, b""
    )
    variables = _nodo("VarFileInfo", b"", 1, 0, traduccion)

    return _nodo("VS_VERSION_INFO", fijo, 0, len(fijo), cadenas + variables)


# ---------------------------------------------------------------------------
# Sellado
# ---------------------------------------------------------------------------


def sellar(exe: Path, ico: Path, version: str, descripcion: str) -> None:
    """Deja el ejecutable con el icono, la descripción y la versión."""
    if sys.platform != "win32":
        raise SystemExit("Sellar recursos solo tiene sentido en Windows.")

    _preparar_api()
    manifiesto = leer_manifiesto(exe)
    imagenes = _trocear_ico(ico)
    nombre = exe.stem

    # `True` = borrar lo que había. Ver la explicación de arriba.
    mango = _kernel32.BeginUpdateResourceW(str(exe), True)
    if not mango:
        raise SystemExit(
            f"No se pudo abrir {exe} para cambiarle los recursos "
            f"(error {ctypes.get_last_error()})."
        )

    def escribir(tipo: int, identificador: int, datos: bytes) -> None:
        bruto = ctypes.create_string_buffer(datos, len(datos))
        ok = _kernel32.UpdateResourceW(
            mango,
            _entero_como_nombre(tipo),
            _entero_como_nombre(identificador),
            IDIOMA,
            ctypes.cast(bruto, wintypes.LPVOID),
            len(datos),
        )
        if not ok:
            raise SystemExit(
                f"No se pudo escribir el recurso {tipo}/{identificador} "
                f"(error {ctypes.get_last_error()})."
            )

    if manifiesto:
        escribir(RT_MANIFEST, 1, manifiesto)

    for indice, (_entrada, imagen) in enumerate(imagenes, start=1):
        escribir(RT_ICON, indice, imagen)

    grupo = struct.pack("<HHH", 0, 1, len(imagenes))
    grupo += b"".join(entrada for entrada, _imagen in imagenes)
    escribir(RT_GROUP_ICON, 1, grupo)

    escribir(RT_VERSION, 1, construir_version(version, descripcion, nombre))

    if not _kernel32.EndUpdateResourceW(mango, False):
        raise SystemExit(
            f"No se pudieron guardar los recursos en {exe} "
            f"(error {ctypes.get_last_error()})."
        )


def main(argumentos: list[str]) -> int:
    if len(argumentos) < 3:
        raise SystemExit(
            "Uso: sellar.py <ejecutable> <icono.ico> <version> [descripción]"
        )
    exe = Path(argumentos[0])
    ico = Path(argumentos[1])
    version = argumentos[2]
    descripcion = argumentos[3] if len(argumentos) > 3 else "BIMNEMO"

    sellar(exe, ico, version, descripcion)
    print(f"Sellado {exe.name}: «{descripcion}», versión {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
