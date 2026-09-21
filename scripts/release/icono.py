"""Dibuja el icono de BIMNEMO y lo deja en ``installer/bimnemo.ico``.

El icono **no se inventa**: es exactamente la misma marca que lleva la
aplicación en su encabezado, pedida a la misma función. Antes este fichero
volvía a dibujar el glifo a mano con Pillow, y eso son dos dibujos que
deberían ser el mismo: el que se separa sin que nadie lo note es siempre el
de fuera del programa, porque dentro se ve todos los días y en la barra de
tareas no se mira.

    marca   `nativo/iconos.py`, `cuadrado()` — el cerebro de circuitos
            blanco sobre el cuadrado azul de la aplicación

Cada tamaño se renderiza del SVG a su resolución en vez de reducir uno
grande: el glifo es una silueta maciza, y a 16 píxeles sale más limpio
dibujado a 16 que encogido desde 1024.

El `.ico` resultante **sí** se versiona —el instalador lo necesita para
compilar y no puede depender de que alguien se acuerde de generarlo— pero se
genera desde aquí para que se pueda rehacer. El binario en git es el
resultado, no la fuente; la fuente es la marca de la aplicación.

Uso:

    .venv\\Scripts\\python.exe scripts/release/icono.py
"""

from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "installer" / "bimnemo.ico"

#: Los tamaños que Windows pide en cada sitio: 16 en la barra de título y el
#: Administrador de tareas, 32 en el escritorio, 256 en la vista de iconos
#: grandes del Explorador.
TAMANOS = (16, 24, 32, 48, 64, 128, 256)


def _capas(tamanos=TAMANOS):
    """La marca en cada tamaño, ya como imágenes de Pillow."""
    import io

    from PIL import Image
    from PySide6.QtCore import QBuffer
    from PySide6.QtGui import QGuiApplication

    # Sin pantalla: esto se lanza desde una consola y a veces desde un
    # servidor de integración continua.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QGuiApplication.instance() or QGuiApplication([])

    import sys

    sys.path.insert(0, str(RAIZ))
    from lightrag.api.bimnemo.nativo import iconos

    capas = []
    for lado in tamanos:
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        iconos.cuadrado(lado).save(buffer, "PNG")
        capas.append(Image.open(io.BytesIO(buffer.data().data())).convert("RGBA"))
    return capas


def generar(destino: Path = DESTINO) -> Path:
    """Escribe el `.ico` con todos los tamaños dentro."""
    capas = _capas()
    destino.parent.mkdir(parents=True, exist_ok=True)
    medidas = [(lado, lado) for lado in TAMANOS]

    # La imagen base tiene que ser **la mayor**. Pillow nunca amplía: si se
    # le da la de 16 como base, descarta en silencio todos los tamaños por
    # encima y escribe un `.ico` de un solo icono diminuto que en el
    # escritorio se ve borroso.
    try:
        capas[-1].save(
            destino, format="ICO", sizes=medidas, append_images=capas[:-1]
        )
    except (TypeError, ValueError):
        # Pillow antiguo: sin `append_images` reduce él solo desde el mayor.
        capas[-1].save(destino, format="ICO", sizes=medidas)
    return destino


def main() -> int:
    for modulo, consejo in (
        ("PIL", "pillow"),
        ("PySide6", "pyside6-essentials"),
    ):
        try:
            __import__(modulo)
        except ImportError:
            raise SystemExit(
                f"Hace falta {consejo} para dibujar el icono:\n"
                f"    .venv\\Scripts\\python.exe -m pip install {consejo}"
            )

    ruta = generar()
    print(f"Icono escrito en {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
