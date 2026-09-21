"""Prepara la carpeta que el instalador de Windows va a empaquetar.

Copia a ``installer/salida/app`` el programa y su entorno virtual, dejando
fuera lo que pertenece a **esta** máquina.

## Qué se lleva y qué no

| | |
|---|---|
| El programa | lo que git versiona (`git ls-files`) |
| El intérprete | Python portable con la biblioteca y las dependencias |
| **Fuera**: `.env` | la configuración y las claves de quien desarrolla |
| **Fuera**: `inputs/`, `rag_storage/` | sus documentos y sus memorias |
| **Fuera**: `.git/` | 16 MB de historia que un cliente no usa |
| **Fuera**: cachés y registros | `__pycache__`, `*.log` |

El programa se saca de `git ls-files` a propósito, no de un recorrido del
directorio: así la lista de lo que se publica es **la misma** que decide
`.gitignore`, y no hay dos criterios que puedan discrepar el día que alguien
añada una carpeta.

## No viaja el `venv`: viaja un Python portable

Un `venv` de Windows **no lleva Python dentro** — solo `site-packages` y un
`pyvenv.cfg` que apunta al intérprete del sistema. Copiarlo reparte esa
dependencia, y en un ordenador sin Python 3.14 en esa ruta exacta la
aplicación no arranca.

Así que se arma un intérprete completo y relocalizable: `python.exe`, sus DLL,
la biblioteca estándar y las 127 dependencias, con un `python._pth` de rutas
relativas. El cliente no instala nada.

Uso:

    python scripts/release/empaquetar.py           # usa el VERSION del repo
    python scripts/release/empaquetar.py v1.2.0    # fuerza una versión
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "installer" / "salida" / "app"

#: Nada de esto debe salir de la máquina de quien empaqueta.
EXCLUIDOS_SIEMPRE = {".env", "VERSION"}


def _git_ls_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"], cwd=str(RAIZ), capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise SystemExit(
            "No se pudo listar los ficheros del repositorio. "
            "Empaquetar se hace desde una copia con git."
        )
    return [linea for linea in proc.stdout.splitlines() if linea.strip()]


def _sobra_en_cliente(relativo: str) -> bool:
    """La lista vive en el programa, no aquí: la comparte el actualizador."""
    sys.path.insert(0, str(RAIZ))
    from lightrag.api.bimnemo.reparto import sobra_en_cliente

    return sobra_en_cliente(relativo)


def _copiar_programa() -> int:
    copiados = 0
    descartados = 0
    for relativo in _git_ls_files():
        if relativo in EXCLUIDOS_SIEMPRE:
            continue
        if _sobra_en_cliente(relativo):
            descartados += 1
            continue
        origen = RAIZ / relativo
        if not origen.is_file():
            continue
        destino = SALIDA / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino)
        copiados += 1
    if descartados:
        print(f"  de desarrollo     {descartados} ficheros fuera del paquete")
    return copiados


#: Lo que no hace falta llevarse de la biblioteca estándar.
#:
#: `test` son 34 MB de pruebas del propio Python; `idlelib`, `tkinter` y
#: `turtledemo` son el editor y la interfaz gráfica que BIMNEMO no usa;
#: `ensurepip` lleva copias de pip dentro. Nada de esto se importa nunca aquí.
SOBRA_DE_LA_BIBLIOTECA = (
    "test",
    "idlelib",
    "tkinter",
    "turtledemo",
    "ensurepip",
    "site-packages",
    "__pycache__",
)

#: Lo que se escribe junto a `python.exe` para que sea **relocalizable**.
#:
#: Con un `python._pth` al lado, Python entra en modo aislado y usa estas
#: rutas, **relativas al ejecutable**, en vez de las de una instalación del
#: sistema. Es lo que convierte una copia en un Python portable: se puede
#: mover de carpeta y sigue funcionando.
#:
#: `..` es la raíz de la instalación, que es donde vive `lightrag/`. Así hay
#: **una sola copia** del programa y `_repo_root()` sigue apuntando donde debe.
#:
#: `import site` hace falta para que se procesen los `.pth` de las
#: dependencias; sin él, paquetes que se registran así dejan de verse.
RUTAS_PORTABLES = """.
.\\DLLs
.\\Lib
.\\Lib\\site-packages
..
import site
"""

#: Con qué cara se presenta BIMNEMO en Windows.
#:
#: Un intérprete de Python se presenta como lo que es: `pythonw.exe`, icono
#: de Python, descripción «Python». Quien usa BIMNEMO no puede reconocer eso
#: como suyo, y si algo se queda colgado no sabe ni qué cerrar.
#:
#: Son **copias**, no renombrados, porque `python.exe` sigue haciendo falta:
#: es el que usa `pip` cuando una actualización trae dependencias nuevas
#: (ver `python_del_entorno` en `bimnemo/paquete.py`).
#: La descripción va en minúscula y a secas. Es lo que el Administrador de
#: tareas pone como nombre del proceso, junto a «Google Chrome» o «Visual
#: Studio Code»: ahí se busca una palabra, no un rótulo.
DESCRIPCION = "bimnemo"

CARAS = (
    ("pythonw.exe", "bimnemo.exe", DESCRIPCION),
    ("python.exe", "bimnemo-consola.exe", "bimnemo (diagnóstico)"),
)

#: Python busca su fichero de rutas por el **nombre del ejecutable**: para
#: `bimnemo.exe` busca `bimnemo._pth`. Sin él, el intérprete copiado pierde
#: el modo aislado, se va a buscar una instalación del sistema y el programa
#: no arranca en un ordenador que no tenga Python. Se escribe uno por cada
#: nombre y así no hay que acordarse.
NOMBRES_PTH = ("python", "pythonw", "bimnemo", "bimnemo-consola")


def _copiar_entorno(version: str) -> None:
    """Monta un **Python portable** dentro del paquete.

    El entorno de desarrollo es un `venv`, y un `venv` de Windows **no lleva
    Python dentro**: solo `site-packages`, más un `pyvenv.cfg` que apunta al
    intérprete del sistema (``home = C:\\Python314``).

    Copiarlo tal cual reparte esa dependencia: en el ordenador de un cliente
    sin Python 3.14 instalado en esa ruta exacta, la aplicación no arranca. Y
    no se notaba aquí porque este ordenador tiene las dos cosas.

    Así que en vez del `venv` se arma un Python completo y relocalizable:
    el intérprete, sus DLL, la biblioteca estándar y las dependencias, con
    rutas relativas. El cliente no instala nada.
    """
    venv_paquetes = RAIZ / ".venv" / "Lib" / "site-packages"
    if not venv_paquetes.is_dir():
        raise SystemExit(f"No encuentro las dependencias en {venv_paquetes}.")

    base = _python_base()
    destino = SALIDA / "python"
    destino.mkdir(parents=True, exist_ok=True)

    # 1. El intérprete y sus bibliotecas nativas.
    for nombre in ("python.exe", "pythonw.exe"):
        shutil.copy2(base / nombre, destino / nombre)
    for dll in base.glob("*.dll"):
        shutil.copy2(dll, destino / dll.name)
    shutil.copytree(
        base / "DLLs",
        destino / "DLLs",
        ignore=shutil.ignore_patterns("__pycache__"),
        dirs_exist_ok=True,
    )

    # 2. La biblioteca estándar, sin lo que nunca se importa.
    shutil.copytree(
        base / "Lib",
        destino / "Lib",
        ignore=shutil.ignore_patterns(*SOBRA_DE_LA_BIBLIOTECA),
        dirs_exist_ok=True,
    )

    # 3. Las dependencias, del entorno de desarrollo.
    shutil.copytree(
        venv_paquetes,
        destino / "Lib" / "site-packages",
        ignore=_ignorar_al_copiar,
        dirs_exist_ok=True,
    )
    _quitar_enlace_editable(destino / "Lib" / "site-packages")
    _podar_qt(destino / "Lib" / "site-packages" / "PySide6")

    # 4. Lo que lo hace portable.
    for nombre in NOMBRES_PTH:
        (destino / f"{nombre}._pth").write_text(RUTAS_PORTABLES, encoding="utf-8")

    print("  Python portable   intérprete, DLLs, biblioteca y dependencias")

    # 5. Y que no se presente como Python, sino como BIMNEMO.
    _poner_cara(destino, version)


#: Rutas del `._pth` cuando el ejecutable está en la **raíz** de la
#: instalación y el intérprete una carpeta más abajo.
RUTAS_DESDE_LA_RAIZ = """python
python\\DLLs
python\\Lib
python\\Lib\\site-packages
.
import site
"""

#: Lo que hay que copiar junto a un ejecutable de Python para que funcione
#: fuera de la carpeta del intérprete.
#:
#: Sin esto arranca **igual de bien en esta máquina y solo en esta**: Windows
#: no encuentra `python314.dll` al lado del ejecutable, se va a buscarla por
#: el PATH y da con la del Python del sistema. Comprobado: cargaba
#: `C:\\Python314\\python314.dll`. En un ordenador sin Python no arrancaría.
DLLS_DEL_INTERPRETE = (
    "python314.dll",
    "python3.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
)


def _poner_cara(destino: Path, version: str) -> None:
    """Deja el intérprete llamándose BIMNEMO, con su icono y su descripción."""
    import icono
    import sellar

    ico = icono.generar()

    for original, nuevo, descripcion in CARAS:
        shutil.copy2(destino / original, destino / nuevo)
        sellar.sellar(destino / nuevo, ico, version, descripcion)

    nombres = ", ".join(nuevo for _o, nuevo, _d in CARAS)
    print(f"  identidad         {nombres}, con icono y descripción")

    _puerta_de_entrada(destino, ico, version)


def _puerta_de_entrada(interprete: Path, ico: Path, version: str) -> None:
    """Saca `bimnemo.exe` a la raíz de la instalación.

    Enterrado en `python\\` no lo ve nadie: quien abre la carpeta de BIMNEMO
    se encuentra ficheros sueltos y carpetas, y ninguno se llama como el
    programa. El ejecutable tiene que estar en la puerta.

    Se copia el intérprete en vez de dejar un acceso directo porque un `.lnk`
    no es un programa: no se puede ejecutar desde una consola, no aparece
    igual en el Administrador de tareas y se rompe si alguien mueve la
    carpeta.
    """
    import sellar

    raiz = interprete.parent

    shutil.copy2(interprete / "pythonw.exe", raiz / "bimnemo.exe")
    (raiz / "bimnemo._pth").write_text(RUTAS_DESDE_LA_RAIZ, encoding="utf-8")
    sellar.sellar(raiz / "bimnemo.exe", ico, version, DESCRIPCION)

    for nombre in DLLS_DEL_INTERPRETE:
        origen = interprete / nombre
        if origen.is_file():
            shutil.copy2(origen, raiz / nombre)

    print("  puerta de entrada bimnemo.exe en la raíz, con su tiempo de ejecución")


#: Lo que no hace falta de Qt para una aplicación de ventanas.
#:
#: `PySide6-Essentials` son 205 MB, y la mayor parte es el **otro** juego de
#: interfaces de Qt —el declarativo, QML y Quick— más herramientas de
#: desarrollo. BIMNEMO usa Widgets, que es el otro camino: nada de esto se
#: importa nunca.
SOBRA_DE_QT_CARPETAS = (
    "qml",  # 19 MB del juego declarativo
    "metatypes",  # descriptores para compilar contra Qt
    "include",
    "typesystems",
    "scripts",
    "examples",
    "glue",
)

#: Módulos de Qt que no se usan, por el principio de su nombre. Se borran
#: tanto la DLL como el `.pyd` que la enlaza con Python.
SOBRA_DE_QT_MODULOS = (
    "Qt6Quick",
    "Qt6Qml",
    "Qt6Designer",
    "QtQuick",
    "QtQml",
    "QtDesigner",
    "qmlls",
    "qmlformat",
    "qmllint",
    "qmlsc",
)

#: Idiomas que se quedan. El resto de `translations/` son 13 MB de mensajes
#: de Qt en idiomas que esta aplicación no ofrece.
IDIOMAS_DE_QT = ("es", "en")

#: Los módulos de Qt que la ventana **sí** importa. El resto de enlaces con
#: Python (`.pyd`) se van: son el puente entre Python y una biblioteca que
#: nadie llama, y `QtOpenGL.pyd` solo son 8,3 MB.
#:
#: Se filtran los `.pyd`, no las DLL de Qt: una DLL puede hacer falta aunque
#: no se importe desde Python, porque otra DLL dependa de ella. El enlace con
#: Python, en cambio, solo lo usa un `import`.
MODULOS_DE_QT = (
    "QtCore",
    "QtGui",
    "QtWidgets",
    "QtNetwork",
    "QtSvg",
)

#: Bibliotecas de Qt que en Windows no pinta nada llevarse.
DLLS_DE_QT_QUE_SOBRAN = (
    "Qt6DBus.dll",  # comunicación entre procesos de Linux
    "Qt6LabsStyleKit.dll",  # del juego declarativo, ya podado
)

#: Complementos de Qt que no se usan. `sqldrivers` es el acceso a bases de
#: datos desde Qt; BIMNEMO habla con su motor por HTTP.
COMPLEMENTOS_QUE_SOBRAN = ("sqldrivers",)


def _ignorar_al_copiar(directorio: str, nombres: list[str]) -> set[str]:
    """Qué no se copia de `site-packages`, decidido **antes** de copiarlo.

    Podría copiarse todo y borrar después, y era lo que hacía. No funciona:
    dentro de `PySide6/qml` hay rutas que pasan del límite de 260 caracteres
    de Windows y la copia se interrumpe con un error que no dice de qué va.
    Además copia y borra 19 MB para nada.
    """
    fuera = {"__pycache__"}
    for nombre in nombres:
        if nombre.endswith((".pyc", ".pyo")):
            fuera.add(nombre)

    if "PySide6" in Path(directorio).parts:
        for nombre in nombres:
            if nombre in SOBRA_DE_QT_CARPETAS or nombre.startswith(
                SOBRA_DE_QT_MODULOS
            ):
                fuera.add(nombre)
    return fuera


def _podar_qt(qt: Path) -> None:
    """Quita de Qt lo que una aplicación de ventanas no usa.

    **Ojo**: quitar de más no falla aquí, falla al arrancar en el ordenador
    de un cliente. Por eso se poda por módulos enteros y separados —QML,
    Quick, Designer— y no por ficheros sueltos, y por eso la construcción
    termina comprobando que el paquete arranca fuera de su carpeta.

    `opengl32sw.dll` son 19,7 MB y **se queda a propósito**: es el dibujado
    por software, el que salva a las máquinas virtuales, los escritorios
    remotos y los equipos sin controlador de vídeo. Quitarlo ahorra 20 MB y
    deja la ventana en negro en el sitio menos oportuno.
    """
    if not qt.is_dir():
        return

    antes = sum(f.stat().st_size for f in qt.rglob("*") if f.is_file())

    for nombre in SOBRA_DE_QT_CARPETAS:
        carpeta = qt / nombre
        if carpeta.is_dir():
            shutil.rmtree(carpeta, ignore_errors=True)

    for fichero in qt.iterdir():
        if fichero.is_file() and fichero.name.startswith(SOBRA_DE_QT_MODULOS):
            fichero.unlink()

    # Anotaciones de tipo y herramientas de desarrollo: 11 MB que solo sirven
    # para programar contra Qt, nunca para ejecutar.
    for fichero in qt.rglob("*.pyi"):
        fichero.unlink()
    for fichero in qt.glob("*.exe"):
        fichero.unlink()

    for fichero in qt.glob("*.pyd"):
        if fichero.stem not in MODULOS_DE_QT:
            fichero.unlink()

    for nombre in DLLS_DE_QT_QUE_SOBRAN:
        fichero = qt / nombre
        if fichero.is_file():
            fichero.unlink()

    for nombre in COMPLEMENTOS_QUE_SOBRAN:
        carpeta = qt / "plugins" / nombre
        if carpeta.is_dir():
            shutil.rmtree(carpeta, ignore_errors=True)

    traducciones = qt / "translations"
    if traducciones.is_dir():
        for fichero in traducciones.iterdir():
            # `qtbase_es.qm` → el idioma va tras el primer guion bajo.
            if fichero.is_file() and "_" in fichero.stem:
                idioma = fichero.stem.split("_", 1)[1].split("_")[0]
                if idioma not in IDIOMAS_DE_QT:
                    fichero.unlink()

    despues = sum(f.stat().st_size for f in qt.rglob("*") if f.is_file())
    # Sin flechas ni adornos: la consola de Windows es cp1252 y un carácter
    # fuera de esa tabla revienta el empaquetado entero por un mensaje.
    print(
        f"  Qt podado         de {antes / 1_048_576:.0f} MB "
        f"a {despues / 1_048_576:.0f} MB"
    )


def _python_base() -> Path:
    """La instalación de Python de la que sale el entorno de desarrollo.

    Se lee del `pyvenv.cfg` en vez de suponerla: el día que se cambie de
    versión, el empaquetado la sigue sin que nadie tenga que acordarse.
    """
    cfg = RAIZ / ".venv" / "pyvenv.cfg"
    try:
        for linea in cfg.read_text(encoding="utf-8").splitlines():
            if linea.strip().startswith("home"):
                base = Path(linea.split("=", 1)[1].strip())
                if (base / "python.exe").is_file():
                    return base
    except OSError:
        pass
    raise SystemExit(
        f"No pude localizar el Python base desde {cfg}.\n"
        "Sin él no se puede empaquetar un intérprete."
    )


def _quitar_enlace_editable(paquetes: Path) -> None:
    """Borra el puntero que `pip install -e .` deja en lugar del paquete.

    El entorno de desarrollo se crea con ``pip install -e .``, que **no copia
    el paquete: deja un puntero** a la carpeta del repositorio. Se vio en el
    rastro de un error que mezclaba las dos rutas: la instalada y la del
    repositorio.

    Aquí no hace falta copiar nada en su lugar: `python._pth` incluye `..`,
    la raíz de la instalación, donde el programa ya viaja. Una sola copia.
    """
    borrados = []
    for patron in ("__editable__*.pth", "__editable___*_finder.py"):
        for fichero in paquetes.glob(patron):
            fichero.unlink()
            borrados.append(fichero.name)
    # `direct_url.json` guarda la ruta del repositorio; es metadato de pip y
    # no se usa para importar, pero delata la máquina de quien empaquetó.
    for meta in paquetes.glob("lightrag_hku-*.dist-info/direct_url.json"):
        meta.unlink()
        borrados.append(meta.name)
    print(f"  enlace editable   quitado ({', '.join(borrados) or 'no había'})")


def _comprobar_sin_rutas_de_desarrollo() -> None:
    """Que no quede ni una mención a la carpeta de quien empaqueta.

    Es **la** comprobación que importa: el instalador anterior arrancaba en
    esta máquina estando roto, porque encontraba el repositorio por su ruta
    absoluta. Buscarla es lo único que distingue un paquete que funciona en
    otro ordenador de uno que solo funciona aquí.
    """
    agujas = {str(RAIZ), str(RAIZ).replace("\\", "/")}
    mirar = {".pth", ".py", ".txt", ".cfg", ".json", ".bat", ".ini"}
    sospechosos = []

    for fichero in SALIDA.rglob("*"):
        if not fichero.is_file() or fichero.suffix.lower() not in mirar:
            continue
        try:
            texto = fichero.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(a in texto for a in agujas):
            sospechosos.append(str(fichero.relative_to(SALIDA)))

    if sospechosos:
        raise SystemExit(
            "El paquete menciona la carpeta de desarrollo, así que no "
            "funcionaría en otro ordenador:\n  " + "\n  ".join(sospechosos[:10])
        )
    print("  rutas de desarrollo  ninguna")


def _version(argumentos: list[str]) -> str:
    if argumentos:
        return argumentos[0].strip()
    try:
        return (RAIZ / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        raise SystemExit("No hay fichero VERSION y no se indicó una versión.")


def main(argumentos: list[str]) -> int:
    version = _version(argumentos)
    if not version:
        raise SystemExit("La versión está vacía.")

    print(f"Empaquetando BIMNEMO {version}")
    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    SALIDA.mkdir(parents=True)

    copiados = _copiar_programa()
    print(f"  programa          {copiados} ficheros")

    # El VERSION se escribe aquí, no se copia: es lo que el actualizador leerá
    # en el ordenador del cliente para saber qué tiene instalado.
    (SALIDA / "VERSION").write_text(version + "\n", encoding="utf-8")
    print(f"  VERSION           {version}")

    print("  entorno virtual   copiando (tarda)…")
    _copiar_entorno(version)
    _comprobar_sin_rutas_de_desarrollo()

    total = sum(f.stat().st_size for f in SALIDA.rglob("*") if f.is_file())
    print(f"  total             {total / 1_048_576:.0f} MB sin comprimir")
    print(f"\nListo en {SALIDA}")
    print("Ahora: scripts\\release\\construir_instalador.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
