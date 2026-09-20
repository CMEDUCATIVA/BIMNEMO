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


def _copiar_programa() -> int:
    copiados = 0
    for relativo in _git_ls_files():
        if relativo in EXCLUIDOS_SIEMPRE:
            continue
        origen = RAIZ / relativo
        if not origen.is_file():
            continue
        destino = SALIDA / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino)
        copiados += 1
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


def _copiar_entorno() -> None:
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
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        dirs_exist_ok=True,
    )
    _quitar_enlace_editable(destino / "Lib" / "site-packages")

    # 4. Lo que lo hace portable.
    (destino / "python._pth").write_text(RUTAS_PORTABLES, encoding="utf-8")

    print("  Python portable   intérprete, DLLs, biblioteca y dependencias")


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
    _copiar_entorno()
    _comprobar_sin_rutas_de_desarrollo()

    total = sum(f.stat().st_size for f in SALIDA.rglob("*") if f.is_file())
    print(f"  total             {total / 1_048_576:.0f} MB sin comprimir")
    print(f"\nListo en {SALIDA}")
    print("Ahora: scripts\\release\\construir_instalador.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
