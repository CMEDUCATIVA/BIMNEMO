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
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
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
    "pausa": "pause-fill",
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
    "database": "database",
    "code": "code-slash",
    # Marca
    "marca": "cerebro-circuito",
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


#: El azul de la marca. Fijo, no el del tema: el icono de la barra de tareas
#: y el del instalador son el mismo y no cambian porque el usuario ponga el
#: tema claro.
AZUL_MARCA = "#2563eb"

#: Cuánto del cuadrado ocupa el cerebro. Por debajo se ve perdido; por encima
#: toca las esquinas redondeadas.
PROPORCION_MARCA = 0.66


def marca(lado: int) -> QPixmap:
    """El cerebro blanco de la marca, con su aire, sobre fondo transparente.

    El aire va **aquí dentro** y no en quien la coloca porque son dos sitios
    —el cuadrado azul del encabezado, que lo pone la hoja de estilo, y el
    icono de Windows, que lo pinta `cuadrado`— y la marca tiene que verse
    igual en los dos.

    Se dibuja en vez de cargar un `.png` para que siga al tamaño de la
    pantalla: en un monitor de alta densidad una imagen de 28 píxeles se ve
    borrosa y ésta no.
    """
    lienzo = QPixmap(lado, lado)
    lienzo.fill(Qt.transparent)

    dentro = max(1, int(lado * PROPORCION_MARCA))
    hueco = (lado - dentro) / 2.0

    pintor = QPainter(lienzo)
    pintor.setRenderHint(QPainter.Antialiasing)
    pintor.drawPixmap(int(hueco), int(hueco), pixmap("marca", dentro, "#ffffff"))
    pintor.end()
    return lienzo


def cuadrado(lado: int) -> QPixmap:
    """La marca **con su fondo**: el icono de la aplicación.

    Es lo que ve Windows —barra de tareas, Alt+Tab, Administrador de
    tareas— y lo que lleva el `.ico` del instalador. Sale de aquí y no de
    una imagen aparte para que no puedan separarse: dos marcas que deberían
    ser la misma acaban discrepando, y la que discrepa sin que nadie lo note
    es siempre la que solo se ve fuera del programa.
    """
    lienzo = QPixmap(lado, lado)
    lienzo.fill(Qt.transparent)

    pintor = QPainter(lienzo)
    pintor.setRenderHint(QPainter.Antialiasing)
    pintor.setPen(Qt.NoPen)
    pintor.setBrush(QColor(AZUL_MARCA))
    pintor.drawRoundedRect(0, 0, lado, lado, lado * 0.22, lado * 0.22)

    pintor.drawPixmap(0, 0, marca(lado))
    pintor.end()
    return lienzo


def de_la_aplicacion() -> QIcon:
    """El icono de la ventana, en todos los tamaños que Windows pide.

    Con fondo: la marca sola es un cerebro blanco sobre transparente, que en
    el encabezado va dentro de su cuadrado azul pero en la barra de tareas
    oscura quedaba como un borrón blanco sin marco. Se dan varios tamaños
    porque Windows pide 16 para la barra de título y 32 para Alt+Tab, y si
    solo hay uno lo escala él, mal.
    """
    icono_app = QIcon()
    for lado in (16, 24, 32, 48, 64, 128, 256):
        icono_app.addPixmap(cuadrado(lado))
    return icono_app


__all__ = [
    "AZUL_MARCA",
    "NOMBRES",
    "cuadrado",
    "de_la_aplicacion",
    "icono",
    "marca",
    "pixmap",
    "poner",
    "retenir",
    "ruta_pintada",
]
