"""Deja el BIMNEMO del repositorio llamándose «bimnemo» en Windows.

El instalado ya lo hace: `empaquetar.py` copia el intérprete a `bimnemo.exe`
y le pone el icono y la descripción. Pero al desarrollar se arranca desde el
entorno virtual, y entonces el Administrador de tareas dice «Python» con el
icono del intérprete.

## Por qué no vale copiar el `pythonw.exe` del `.venv`

Ese no es un intérprete: es un **redirector**. Lo único que hace es lanzar el
`pythonw.exe` de la instalación base —`C:\\Python314`— como proceso hijo, y
es en ese hijo donde vive la ventana. Una copia renombrada da un padre que se
llama «bimnemo» y un hijo que sigue diciendo «Python», que es justo lo que
se ve en el Administrador de tareas. Así lo hacía la primera versión de este
script, y estaba mal.

Aquí se copia el **intérprete de verdad**, el de la instalación base, con
las cuatro bibliotecas que necesita a su lado. Queda en `.venv\\Scripts\\`,
junto al `pyvenv.cfg` de la carpeta de encima, que es lo que le dice que está
dentro del entorno: encuentra Qt y LightRAG, y es **un solo proceso**.

    .venv\\Scripts\\python.exe scripts/release/cara_local.py

No hace falta cambiar cómo se abre: `desktop.py` ve que existe y se relanza
con él.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

#: Lo que el intérprete copiado necesita a su lado para arrancar. Sin la DLL,
#: Windows la busca por el PATH y puede cargar la de otra instalación.
DLLS = ("python314.dll", "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll")


def _base(entorno: Path) -> Path:
    """La instalación de Python de la que sale el entorno, según `pyvenv.cfg`."""
    for linea in (entorno / "pyvenv.cfg").read_text(encoding="utf-8").splitlines():
        clave, _, valor = linea.partition("=")
        if clave.strip() == "home":
            return Path(valor.strip())
    raise SystemExit("El pyvenv.cfg no dice de qué Python sale el entorno.")


def main() -> int:
    import icono
    import sellar

    entorno = RAIZ / ".venv"
    scripts = entorno / "Scripts"
    base = _base(entorno)
    if not (base / "pythonw.exe").is_file():
        raise SystemExit(f"No encuentro el intérprete base en {base}.")

    for nombre in DLLS:
        if (base / nombre).is_file():
            shutil.copy2(base / nombre, scripts / nombre)

    version = (RAIZ / "VERSION").read_text(encoding="utf-8").strip()
    ico = icono.generar()

    destino = scripts / "bimnemo.exe"
    shutil.copy2(base / "pythonw.exe", destino)
    sellar.sellar(destino, ico, version, "bimnemo")

    print(f"Listo: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
