"""Deja el BIMNEMO del repositorio llamándose «bimnemo» en Windows.

El instalado ya lo hace: `empaquetar.py` copia el intérprete a `bimnemo.exe`
y le pone el icono y la descripción. Pero al desarrollar se arranca desde el
entorno virtual, y entonces el Administrador de tareas dice «Python» con el
icono del intérprete: es verdad, y es lo peor que puede decir —que esto no
es un programa, es Python ejecutando algo—.

Esto hace lo mismo con el intérprete del `.venv`. Es una **copia**, no un
renombrado: `pythonw.exe` sigue haciendo falta para todo lo demás.

    .venv\\Scripts\\python.exe scripts/release/cara_local.py

Y a partir de ahí se abre así:

    .venv\\Scripts\\bimnemo.exe -m lightrag.api.bimnemo.desktop --nativo

La copia queda dentro de `Scripts/`, junto a `pyvenv.cfg`, que es lo que
Python busca al lado de su ejecutable para saber en qué entorno está. Fuera
de ahí perdería el entorno y no encontraría ni Qt ni LightRAG.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    import icono
    import sellar

    scripts = RAIZ / ".venv" / "Scripts"
    origen = scripts / "pythonw.exe"
    if not origen.is_file():
        raise SystemExit(f"No encuentro {origen}: ¿está creado el entorno?")

    version = (RAIZ / "VERSION").read_text(encoding="utf-8").strip()
    ico = icono.generar()

    destino = scripts / "bimnemo.exe"
    shutil.copy2(origen, destino)
    sellar.sellar(destino, ico, version, "bimnemo")

    print(f"Listo: {destino}")
    print("Ábrelo así:")
    print(r"    .venv\Scripts\bimnemo.exe -m lightrag.api.bimnemo.desktop --nativo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
