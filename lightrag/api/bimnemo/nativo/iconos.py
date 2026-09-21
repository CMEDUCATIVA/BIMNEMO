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
    "enviar": "send",
    "conversacion": "chat-square-text",
    "desplegar": "chevron-down",
    # Secciones del panel
    "memorias": "bar-chart-steps",
    "categorias": "grid-3x3-gap",
    "tipos": "file-earmark-text",
    # Las categorías del catálogo. La clave es el nombre **que manda el
    # motor** —son iconos de Lucide, que es lo que usa la web—, y el valor su
    # equivalente en Bootstrap. Así el catálogo sigue mandando: una categoría
    # nueva solo necesita una línea aquí, y mientras no la tenga sale sin
    # icono en vez de reventar.
    "file-text": "file-earmark-text",
    "table": "file-earmark-spreadsheet",
    "presentation": "file-earmark-slides",
    "image": "image",
    "box": "box",
    "ruler": "rulers",
    "database": "database",
    "code": "code-slash",
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


@lru_cache(maxsize=32)
def ruta_pintada(nombre: str, lado: int, color: str) -> str:
    """El icono como PNG en disco, con su ruta para una hoja de estilo.

    Existe por una limitación de Qt: en `QSS` una imagen se pide con
    `url(...)` y eso es un **fichero**, no un `QPixmap`. Es lo que hace falta
    para la flecha del desplegable, que si no Qt no dibuja —y un selector sin
    flecha no se lee como un selector.

    Se guarda en la carpeta de datos del usuario y no junto al programa: el
    paquete instalado puede estar en un sitio sin permiso de escritura.
    """
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtGui import QGuiApplication

    # Sin aplicación no hay forma de rasterizar: Qt aborta el proceso al
    # construir un `QPixmap`. Se devuelve vacío —la hoja se queda sin esa
    # imagen— en vez de tumbar a quien solo quería leer los colores.
    if QGuiApplication.instance() is None:
        return ""

    carpeta = (
        Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "iconos"
    )
    carpeta.mkdir(parents=True, exist_ok=True)

    limpio = "".join(c for c in color if c.isalnum())
    destino = carpeta / f"{NOMBRES.get(nombre, nombre)}-{lado}-{limpio}.png"
    if not destino.exists():
        pixmap(nombre, lado, color).save(str(destino), "PNG")
    # Barras normales: en Windows, `url(C:\...)` no se interpreta.
    return destino.as_posix()


#: Propiedades con las que un widget recuerda qué icono lleva puesto. Sin
#: esto, cambiar de tema dejaría cada icono con el color del tema anterior:
#: la hoja de estilo no alcanza a un `QPixmap` ya pintado.
_QUE = "icono-nombre"
_LADO = "icono-lado"
_TONO = "icono-tono"


def poner(widget, nombre: str, lado: int = 16, tono: str = "texto_2") -> None:
    """Pone un icono en un botón o una etiqueta, y recuerda cuál.

    El tono es el **nombre** de un color de la paleta —`texto_2`, `azul`,
    `sobre_azul`—, no un color: así `retenir` puede volver a pintarlo cuando
    la paleta cambia, sin que quien lo puso tenga que acordarse de nada.
    """
    widget.setProperty(_QUE, nombre)
    widget.setProperty(_LADO, lado)
    widget.setProperty(_TONO, tono)
    _aplicar(widget)


def _aplicar(widget) -> None:
    from lightrag.api.bimnemo.nativo import tema

    nombre = widget.property(_QUE)
    if not nombre:
        return
    lado = int(widget.property(_LADO) or 16)
    color = getattr(tema.ACTUAL, str(widget.property(_TONO) or "texto_2"))
    if hasattr(widget, "setIcon"):
        widget.setIcon(icono(str(nombre), lado, color))
    elif hasattr(widget, "setPixmap"):
        widget.setPixmap(pixmap(str(nombre), lado, color))


def retenir(raiz) -> None:
    """Vuelve a teñir, con la paleta de ahora, todo lo que puso `poner`."""
    from PySide6.QtWidgets import QWidget

    for widget in raiz.findChildren(QWidget):
        if widget.property(_QUE):
            _aplicar(widget)


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

    pintor.drawPolyline(
        [_punto(p(5, 16)), _punto(p(5, 12)), _punto(p(19, 12)), _punto(p(19, 16))]
    )
    pintor.drawLine(*p(12, 12), *p(12, 8))
    pintor.end()
    return lienzo


def _punto(par: tuple[float, float]) -> QPointF:
    return QPointF(par[0], par[1])


__all__ = [
    "NOMBRES",
    "icono",
    "marca",
    "pixmap",
    "poner",
    "retenir",
    "ruta_pintada",
]
