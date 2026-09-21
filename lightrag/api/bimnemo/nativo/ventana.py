"""El armazón de la ventana: barra superior, navegación y contenido.

Etapa 1 de `docs/BIMNEMO_INTERFAZ_NATIVA.md`. Aquí está la estructura y el
tema; las pantallas llegan en las etapas siguientes y se enchufan en
`registrar_pantalla`, que es el único sitio que hay que tocar para añadir una.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
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

from lightrag.api.bimnemo.nativo import formato, iconos, tema
from lightrag.api.bimnemo.nativo.motor import Motor

#: Las pantallas, en el orden en que salen. El segundo valor es la etapa del
#: plan en que se construye cada una; mientras no llegue, sale un hueco que
#: dice qué falta en vez de una pantalla en blanco que parece rota.
PANTALLAS = (
    ("Panel", "panel"),
    ("Archivos", "archivos"),
    ("Chat", "chat"),
    ("Configuración IA", "configuracion"),
    ("Motor", "motor"),
    ("API", "api"),
)


class Hueco(QWidget):
    """Lo que se ve donde todavía no hay pantalla.

    Ya no queda ninguna, pero se conserva: una pantalla vacía sin explicación
    se interpreta siempre como un programa roto, y si mañana se añade una
    entrada de navegación antes que su pantalla, esto es lo que evita que el
    usuario crea que algo se ha estropeado.
    """

    def __init__(self, nombre: str) -> None:
        super().__init__()
        caja = QVBoxLayout(self)
        caja.setContentsMargins(32, 28, 32, 28)
        caja.setSpacing(6)

        titulo = QLabel(nombre)
        titulo.setObjectName("titulo")
        caja.addWidget(titulo)

        aviso = QLabel(
            "Esta pantalla todavía no está en la ventana nativa.\n"
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
        # Antes de montar nada: hay piezas que eligen su color en caliente
        # —las insignias de estado de la tabla de archivos— y lo leen de ahí.
        tema.usar(self.paleta)

        self.setWindowTitle("BIMNEMO — Memoria de conocimiento")
        self.setWindowIcon(QIcon(iconos.marca(64)))
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

        for nombre, _icono in PANTALLAS:
            self.registrar_pantalla(nombre, Hueco(nombre))
        self._pantallas_construidas()
        self._botones[0].setChecked(True)

    def _pantallas_construidas(self) -> None:
        """Sustituye los huecos por las pantallas que ya existen.

        Se importan aquí dentro y no arriba porque cada pantalla arrastra sus
        propios widgets de Qt: importarlas todas al cargar el módulo alarga
        el arranque por pantallas que quizá no se abran nunca.
        """
        from lightrag.api.bimnemo.nativo.pantalla_api import PantallaApi
        from lightrag.api.bimnemo.nativo.pantalla_archivos import PantallaArchivos
        from lightrag.api.bimnemo.nativo.pantalla_chat import PantallaChat
        from lightrag.api.bimnemo.nativo.pantalla_configuracion import (
            PantallaConfiguracion,
        )
        from lightrag.api.bimnemo.nativo.pantalla_motor import PantallaMotor
        from lightrag.api.bimnemo.nativo.pantalla_panel import PantallaPanel

        self.registrar_pantalla("Panel", PantallaPanel(self.motor))

        archivos = PantallaArchivos(self.motor)
        # Una raya hasta que el motor conteste: un cero mientras se carga se
        # lee como «esta memoria está vacía», que es otra cosa.
        self.poner_cuenta("Archivos", "—")
        archivos.cuenta.connect(
            lambda cuantos: self.poner_cuenta("Archivos", formato.numero(cuantos))
        )
        self.registrar_pantalla("Archivos", archivos)
        self.registrar_pantalla("Chat", PantallaChat(self.motor))
        self.registrar_pantalla("Motor", PantallaMotor(self.motor))
        self.registrar_pantalla(
            "Configuración IA", PantallaConfiguracion(self.motor)
        )
        self.registrar_pantalla("API", PantallaApi(self.motor))

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
        marca.setPixmap(_marca(28, self.paleta.azul))  # cuadrado azul de marca
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
        #: Los contadores del carril, por pantalla. Solo los rellena quien
        #: tiene algo que contar.
        self._cuentas: dict[str, QLabel] = {}

        for indice, (nombre, icono_nombre) in enumerate(PANTALLAS):
            boton = QPushButton(nombre)
            boton.setObjectName("nav")
            boton.setIcon(iconos.icono(icono_nombre, 15, "#94a3b8"))
            boton.setCheckable(True)
            boton.setCursor(Qt.PointingHandCursor)
            boton.clicked.connect(
                lambda _marcado=False, i=indice: self.contenido.setCurrentIndex(i)
            )
            self._grupo.addButton(boton, indice)
            self._botones.append(boton)
            self._cuentas[nombre] = self._contador(boton)

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

    @staticmethod
    def _contador(boton: QPushButton) -> QLabel:
        """El número que va a la derecha del rótulo, dentro del botón.

        Dentro y no al lado: fuera del botón, la mitad derecha del carril
        dejaría de encenderse al pasar el ratón y de responder al clic. La
        etiqueta deja pasar el ratón para que el botón siga siendo uno solo.
        """
        etiqueta = QLabel("")
        etiqueta.setObjectName("nav-cuenta")
        etiqueta.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        caja = QHBoxLayout(boton)
        caja.setContentsMargins(0, 0, 12, 0)
        caja.addStretch(1)
        caja.addWidget(etiqueta)
        return etiqueta

    def poner_cuenta(self, nombre: str, texto: str) -> None:
        """Escribe el contador de una pantalla en el carril."""
        etiqueta = self._cuentas.get(nombre)
        if etiqueta is not None:
            etiqueta.setText(texto)

    def registrar_pantalla(self, nombre: str, widget: QWidget) -> None:
        """Mete una pantalla en su sitio.

        Al llegar cada etapa se sustituye el `Hueco` por la pantalla de
        verdad **aquí y en ningún otro sitio**.
        """
        indice = [n for n, _i in PANTALLAS].index(nombre)
        anterior = self.contenido.widget(indice)
        if anterior is not None:
            self.contenido.removeWidget(anterior)
            anterior.deleteLater()
        self.contenido.insertWidget(indice, widget)
