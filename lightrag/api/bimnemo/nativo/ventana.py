"""El armazón de la ventana: barra superior, navegación y contenido.

Etapa 1 de `docs/BIMNEMO_INTERFAZ_NATIVA.md`. Aquí está la estructura y el
tema; las pantallas llegan en las etapas siguientes y se enchufan en
`registrar_pantalla`, que es el único sitio que hay que tocar para añadir una.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo import tema
from lightrag.api.bimnemo.nativo.motor import Motor

#: Las pantallas, en el orden en que salen. El segundo valor es la etapa del
#: plan en que se construye cada una; mientras no llegue, sale un hueco que
#: dice qué falta en vez de una pantalla en blanco que parece rota.
PANTALLAS = (
    ("Panel", 4),
    ("Archivos", 3),
    ("Chat", 5),
    ("Configuración IA", 2),
    ("Motor", 2),
    ("API", 6),
)


def _marca(lado: int, color: str) -> QPixmap:
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


class Hueco(QWidget):
    """Lo que se ve donde todavía no hay pantalla.

    Dice **qué falta y cuándo llega**. Una pantalla vacía sin explicación se
    interpreta siempre como un programa roto.
    """

    def __init__(self, nombre: str, etapa: int) -> None:
        super().__init__()
        caja = QVBoxLayout(self)
        caja.setContentsMargins(32, 28, 32, 28)
        caja.setSpacing(6)

        titulo = QLabel(nombre)
        titulo.setObjectName("titulo")
        caja.addWidget(titulo)

        aviso = QLabel(
            f"Esta pantalla llega en la etapa {etapa} de la interfaz nativa.\n"
            "Mientras tanto está disponible en la interfaz web, que sigue "
            "funcionando igual."
        )
        aviso.setObjectName("descripcion")
        aviso.setWordWrap(True)
        caja.addWidget(aviso)
        caja.addStretch(1)


class Ventana(QMainWindow):
    def __init__(self, motor: Motor, version: str, oscuro: bool = True) -> None:
        super().__init__()
        self.motor = motor
        self.version = version
        self.paleta = tema.OSCURO if oscuro else tema.CLARO

        self.setWindowTitle("BIMNEMO — Memoria de conocimiento")
        self.setWindowIcon(QIcon(_marca(64, self.paleta.azul)))
        self.resize(1280, 820)
        self.setMinimumSize(980, 620)
        self.setStyleSheet(tema.hoja(self.paleta))

        raiz = QWidget()
        columna = QVBoxLayout(raiz)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(0)
        columna.addWidget(self._barra())

        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        cuerpo.addWidget(self._lateral())

        self.contenido = QStackedWidget()
        cuerpo.addWidget(self.contenido, 1)
        columna.addLayout(cuerpo, 1)

        self.setCentralWidget(raiz)

        for nombre, etapa in PANTALLAS:
            self.registrar_pantalla(nombre, Hueco(nombre, etapa))
        self._botones[0].setChecked(True)

    # -- estructura ---------------------------------------------------------

    def _barra(self) -> QWidget:
        barra = QFrame()
        barra.setObjectName("barra")
        barra.setFixedHeight(tema.ALTO_BARRA)

        fila = QHBoxLayout(barra)
        fila.setContentsMargins(16, 0, 16, 0)
        fila.setSpacing(10)

        marca = QLabel()
        marca.setObjectName("marca")
        marca.setFixedSize(28, 28)
        marca.setPixmap(_marca(28, self.paleta.azul))
        marca.setAlignment(Qt.AlignCenter)
        fila.addWidget(marca)

        nombre = QLabel("BIMNEMO")
        nombre.setObjectName("nombre")
        fila.addWidget(nombre)

        lema = QLabel("Memoria de conocimiento")
        lema.setObjectName("lema")
        fila.addWidget(lema)

        fila.addStretch(1)

        self.selector = QComboBox()
        self.selector.setMinimumWidth(220)
        self.selector.addItem("General")
        fila.addWidget(self.selector)

        self.boton_actualizar = QPushButton("Actualizado")
        fila.addWidget(self.boton_actualizar)
        return barra

    def _lateral(self) -> QWidget:
        lateral = QFrame()
        lateral.setObjectName("lateral")
        lateral.setFixedWidth(tema.ANCHO_LATERAL)

        columna = QVBoxLayout(lateral)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(2)

        rotulo = QLabel("Navegación")
        rotulo.setObjectName("rotulo")
        columna.addWidget(rotulo)

        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self._botones: list[QPushButton] = []

        for indice, (nombre, _etapa) in enumerate(PANTALLAS):
            boton = QPushButton(nombre)
            boton.setObjectName("nav")
            boton.setCheckable(True)
            boton.setCursor(Qt.PointingHandCursor)
            boton.clicked.connect(
                lambda _marcado=False, i=indice: self.contenido.setCurrentIndex(i)
            )
            self._grupo.addButton(boton, indice)
            self._botones.append(boton)

            envoltorio = QHBoxLayout()
            envoltorio.setContentsMargins(8, 0, 8, 0)
            envoltorio.addWidget(boton)
            columna.addLayout(envoltorio)

        columna.addStretch(1)

        # La versión abajo a la izquierda, como en la interfaz web.
        etiqueta = QLabel(f"BIMNEMO {self.version}")
        etiqueta.setObjectName("version")
        columna.addWidget(etiqueta)
        return lateral

    def registrar_pantalla(self, nombre: str, widget: QWidget) -> None:
        """Mete una pantalla en su sitio.

        Al llegar cada etapa se sustituye el `Hueco` por la pantalla de
        verdad **aquí y en ningún otro sitio**.
        """
        indice = [n for n, _e in PANTALLAS].index(nombre)
        anterior = self.contenido.widget(indice)
        if anterior is not None:
            self.contenido.removeWidget(anterior)
            anterior.deleteLater()
        self.contenido.insertWidget(indice, widget)
