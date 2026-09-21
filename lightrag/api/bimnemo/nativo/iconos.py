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

from PySide6.QtCore import QByteArray, QPointF, Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap
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
    "editar": "pencil",
    "claro": "brightness-high",
    "oscuro": "moon",
    "aviso": "exclamation-triangle",
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


def marca(lado: int) -> QPixmap:
    """El cuadrado azul de la marca, dibujado con el mismo glifo que la web.

    Se dibuja en vez de cargar una imagen para que siga el tamaño de la
    pantalla: en un monitor de alta densidad un `.png` de 28 píxeles se ve
    borroso y este no.
    """
    lienzo = QPixmap(lado, lado)
    lienzo.fill(Qt.transparent)

    pintor = QPainter(lienzo)
    pintor.setRenderHint(QPainter.Antialiasing)
    pintor.setBrush(Qt.NoBrush)

    grosor = max(1.0, lado / 12.0)
    pluma = QPen(Qt.white, grosor)
    pluma.setCapStyle(Qt.RoundCap)
    pluma.setJoinStyle(Qt.RoundJoin)
    pintor.setPen(pluma)

    # Rejilla de 24, la del `viewBox` del icono `network` de `icons.js`.
    escala = lado / 24.0 * 0.66
    margen = (lado - 24 * escala) / 2.0

    def p(x: float, y: float) -> tuple[float, float]:
        return (margen + x * escala, margen + y * escala)

    for x, y in ((16, 16), (2, 16), (9, 2)):
        ex, ey = p(x, y)
        pintor.drawRoundedRect(ex, ey, 6 * escala, 6 * escala, escala, escala)

    pintor.drawPolyline([_punto(p(5, 16)), _punto(p(5, 12)),
                         _punto(p(19, 12)), _punto(p(19, 16))])
    pintor.drawLine(*p(12, 12), *p(12, 8))
    pintor.end()
    return lienzo


def _punto(par: tuple[float, float]):
    from PySide6.QtCore import QPointF

    return QPointF(par[0], par[1])


__all__ = ["NOMBRES", "icono", "marca", "pixmap"]
