"""Prepara la carpeta que el instalador de Windows va a empaquetar.

Copia a ``installer/salida/app`` el programa y su entorno virtual, dejando
fuera lo que pertenece a **esta** máquina.

## Qué se lleva y qué no

| | |
|---|---|
| El programa | lo que git versiona (`git ls-files`) |
| El entorno virtual | `.venv/`, ~450 MB con las dependencias |
| **Fuera**: `.env` | la configuración y las claves de quien desarrolla |
| **Fuera**: `inputs/`, `rag_storage/` | sus documentos y sus memorias |
| **Fuera**: `.git/` | 16 MB de historia que un cliente no usa |
| **Fuera**: cachés y registros | `__pycache__`, `*.log` |

El programa se saca de `git ls-files` a propósito, no de un recorrido del
directorio: así la lista de lo que se publica es **la misma** que decide
`.gitignore`, y no hay dos criterios que puedan discrepar el día que alguien
añada una carpeta.

## El entorno virtual viaja tal cual

Pesa, pero evita que el cliente tenga que instalar Python y 127 paquetes. Se
comprueba que tiene su intérprete antes de empaquetar nada: un instalador sin
`python.exe` produce un programa que no arranca y un cliente que no sabe por
qué.

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


def _copiar_entorno() -> None:
    venv = RAIZ / ".venv"
    interprete = venv / "Scripts" / "python.exe"
    if not interprete.is_file():
        raise SystemExit(
            f"No hay intérprete en {interprete}.\n"
            "Sin él el instalador produce un programa que no arranca."
        )
    # Las cachés no aportan nada y engordan el instalador; se regeneran solas.
    shutil.copytree(
        venv,
        SALIDA / ".venv",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        dirs_exist_ok=True,
    )


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

    total = sum(f.stat().st_size for f in SALIDA.rglob("*") if f.is_file())
    print(f"  total             {total / 1_048_576:.0f} MB sin comprimir")
    print(f"\nListo en {SALIDA}")
    print("Ahora: scripts\\release\\construir_instalador.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
