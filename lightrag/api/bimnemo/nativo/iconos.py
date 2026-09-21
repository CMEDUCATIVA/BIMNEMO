"""Los iconos de la ventana nativa.

Son **Bootstrap Icons** (https://icons.getbootstrap.com/), licencia MIT,
copiados a `nativo/iconos/` como ficheros `.svg` sueltos.

## Por qué van en el repositorio y no se descargan

Porque BIMNEMO tiene que arrancar sin internet. Un icono que se baja al
abrir la ventana es una ventana que, el día que el cliente esté sin red,
sale sin iconos y parece rota.

## Por qué SVG y no PNG

Porque se tiñen y se escalan. El mismo fichero sirve para el icono gris de
una fila y para el azul de un botón activo, y en un monitor de alta densidad
no se ve borroso. Los SVG de Bootstrap vienen con `fill="currentColor"`, que
Qt **no** resuelve solo: se sustituye por el color pedido antes de pintarlo.

## Se guardan en caché

Leer y rasterizar un SVG cuesta poco, pero la tabla de archivos lo pediría
una vez por fila en cada refresco. La caché es por (nombre, tamaño, color).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

CARPETA = Path(__file__).resolve().parent / "iconos"

#: Nombres propios para los de Bootstrap, para que el código diga qué es el
#: icono y no cómo se llama en la biblioteca de otro. El día que se cambie de
#: juego de iconos, se cambia esta tabla y nada más.
NOMBRES = {
    # Navegación
    "panel": "speedometer2",
    "archivos": "folder2-open",
    "chat": "chat-dots",
    "configuracion": "sliders2",
    "motor": "cpu",
    "api": "plug",
    # Cifras del panel
    "ficheros": "files",
    "disco": "hdd",
    "documento": "file-earmark-text",
    "trozos": "layers",
    "entidades": "diagram-3",
    "relaciones": "share",
    # Acciones
    "alejar": "dash-lg",
    "acercar": "plus-lg",
    "encajar": "arrows-fullscreen",
    "recargar": "arrow-clockwise",
    "buscar": "search",
    "borrar": "trash3",
    "subir": "cloud-arrow-up",
    "copiar": "clipboard",
    # Marca
    "marca": "diagram-3-fill",
}


def _fichero(nombre: str) -> Optional[Path]:
    archivo = NOMBRES.get(nombre, nombre)
    ruta = CARPETA / f"{archivo}.svg"
    return ruta if ruta.is_file() else None


@lru_cache(maxsize=256)
def pixmap(nombre: str, lado: int = 16, color: str = "#cbd5e1") -> QPixmap:
    """El icono, del tamaño y el color pedidos.

    Si no existe devuelve un pixmap vacío en vez de reventar: quedarse sin un
    icono es feo; quedarse sin ventana porque falta un fichero de 400 bytes,
    inaceptable.
    """
    ruta = _fichero(nombre)
    lienzo = QPixmap(lado, lado)
    lienzo.fill(Qt.transparent)
    if ruta is None:
        return lienzo

    texto = ruta.read_text(encoding="utf-8").replace("currentColor", color)
    renderizador = QSvgRenderer(QByteArray(texto.encode("utf-8")))

    pintor = QPainter(lienzo)
    pintor.setRenderHint(QPainter.Antialiasing)
    renderizador.render(pintor)
    pintor.end()
    return lienzo


@lru_cache(maxsize=256)
def icono(nombre: str, lado: int = 16, color: str = "#cbd5e1") -> QIcon:
    """El mismo icono, envuelto para un botón."""
    return QIcon(pixmap(nombre, lado, color))


__all__ = ["NOMBRES", "icono", "pixmap"]
