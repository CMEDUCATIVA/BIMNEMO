"""El armazón de la ventana: barra superior, navegación y contenido.

Etapa 1 de `docs/BIMNEMO_INTERFAZ_NATIVA.md`. Aquí está la estructura y el
tema; las pantallas llegan en las etapas siguientes y se enchufan en
`registrar_pantalla`, que es el único sitio que hay que tocar para añadir una.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo import actualizar, formato, iconos, tema
from lightrag.api.bimnemo.nativo.barra import BarraSuperior
from lightrag.api.bimnemo.nativo.bienvenida import Bienvenida
from lightrag.api.bimnemo.nativo.memorias import Memorias, ajustes
from lightrag.api.bimnemo.nativo.panel_piezas import ResumenCarril
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
            "Esta pantalla todavía no está disponible."
        )
        aviso.setObjectName("descripcion")
        aviso.setWordWrap(True)
        caja.addWidget(aviso)
        caja.addStretch(1)


class Ventana(QMainWindow):
    def __init__(
        self, motor: Motor, version: str, oscuro: Optional[bool] = None
    ) -> None:
        super().__init__()
        self.motor = motor
        self.version = version
        # Sin indicación, el tema que se eligió la última vez. Cambiarlo es
        # una preferencia, no una opción de arranque: volver a oscuro en cada
        # apertura convierte el botón en un juguete.
        if oscuro is None:
            oscuro = str(ajustes().value("tema", "oscuro")) != "claro"
        self.paleta = tema.OSCURO if oscuro else tema.CLARO
        # Antes de montar nada: hay piezas que eligen su color en caliente
        # —las insignias de estado de la tabla de archivos— y lo leen de ahí.
        tema.usar(self.paleta)

        self.memorias = Memorias(motor, self)

        self.setWindowTitle("BIMNEMO — Memoria de conocimiento")
        self.setWindowIcon(iconos.de_la_aplicacion())
        self.resize(1280, 820)
        self.setMinimumSize(980, 620)
        self.setStyleSheet(tema.hoja(self.paleta))

        raiz = QWidget()
        columna = QVBoxLayout(raiz)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(0)

        self.barra = BarraSuperior(motor, self.memorias, self)
        self.barra.refrescar.connect(self.refrescar_todo)
        self.barra.tema_alternado.connect(self.alternar_tema)
        columna.addWidget(self.barra)

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
        # La primera, y dicho en los dos sitios: `registrar_pantalla` quita y
        # vuelve a meter widgets, y al quitar el que estaba visible Qt deja
        # delante el que le parece. Sin esto la ventana abría en Motor con
        # «Panel» marcado en el carril.
        self._botones[0].setChecked(True)
        self.contenido.setCurrentIndex(0)

        # Cambiar de memoria es cambiar de datos en TODAS las pantallas: el
        # motor ya enruta a la nueva, así que basta con pedirles que relean.
        self.memorias.cambiada.connect(self._otra_memoria)
        # Y el nombre de la abierta, a quien lo enseñe. Va del registro a la
        # pantalla y no al revés: preguntarlo por su cuenta significaría dos
        # fuentes que se contradicen mientras una se entera antes que otra.
        self.memorias.listado.connect(self._repartir_memoria)
        self.barra.retematizar()
        self.memorias.cargar()

        # La primera vez: nombre de la memoria y modelo, antes que nada.
        self.bienvenida = Bienvenida(self, motor, self.memorias)
        self.bienvenida.terminada.connect(self.refrescar_todo)
        self.bienvenida.comprobar()

        # Y siempre: si hay una versión nueva en GitHub, se dice arriba.
        self.vigia = actualizar.Vigia(motor, self)
        self.vigia.disponible.connect(self.barra.boton_actualizar.mostrar)
        self.barra.boton_actualizar.clicked.connect(self._actualizar)
        self.vigia.arrancar()

    # -- lo que vale para toda la ventana -----------------------------------

    def refrescar_todo(self) -> None:
        """Relee lo que enseña cada pantalla, y si el motor sigue vivo.

        Se pregunta pantalla por pantalla en vez de mantener una lista: la
        que tenga algo que releer expone `refrescar`, y la que no —Chat, que
        es una conversación, o API, que es un catálogo fijo— no tiene por qué
        inventarse el método.
        """
        for indice in range(self.contenido.count()):
            pantalla = self.contenido.widget(indice)
            releer = getattr(pantalla, "refrescar", None)
            if callable(releer):
                releer()
        self.barra.comprobar_motor()

    def _actualizar(self) -> None:
        actualizar.DialogoActualizar(self.motor, self.vigia.estado, self).exec()

    def _otra_memoria(self, _identificador: str) -> None:
        """Se ha abierto otra memoria.

        Primero se avisa a quien guarde estado de la anterior —el panel
        recuerda una entidad de partida que en esta puede no existir— y
        después se relee todo. Al revés, la relectura llegaría con los
        filtros viejos puestos.
        """
        for indice in range(self.contenido.count()):
            pantalla = self.contenido.widget(indice)
            empezar = getattr(pantalla, "otra_memoria", None)
            if callable(empezar):
                empezar()
        self.refrescar_todo()

    def ir_a_archivos(self, categoria: str) -> None:
        """Abre Archivos ya filtrado. Lo pide una tarjeta de categoría."""
        archivos = self.contenido.widget(1)
        filtrar = getattr(archivos, "filtrar", None)
        if callable(filtrar):
            filtrar(categoria)
        self.contenido.setCurrentIndex(1)
        self._botones[1].setChecked(True)

    def _repartir_memoria(self) -> None:
        nombre = self.memorias.nombre()
        for indice in range(self.contenido.count()):
            pantalla = self.contenido.widget(indice)
            poner = getattr(pantalla, "poner_memoria", None)
            if callable(poner):
                poner(nombre)

    def alternar_tema(self) -> None:
        self.aplicar_tema(self.paleta is not tema.OSCURO)

    def aplicar_tema(self, oscuro: bool) -> None:
        """Cambia de tema en caliente, sin rehacer la ventana.

        Rehacerla sería más fácil de escribir y perdería la conversación del
        chat, el grafo colocado y la pantalla en la que estabas. La hoja de
        estilo cubre casi todo; lo que se pinta a mano —iconos teñidos,
        insignias, el lienzo del grafo— lo repasa cada `retematizar`.
        """
        self.paleta = tema.OSCURO if oscuro else tema.CLARO
        tema.usar(self.paleta)
        ajustes().setValue("tema", "oscuro" if oscuro else "claro")

        self.setStyleSheet(tema.hoja(self.paleta))
        iconos.retenir(self)
        self.barra.retematizar()
        for indice in range(self.contenido.count()):
            pantalla = self.contenido.widget(indice)
            repasar = getattr(pantalla, "retematizar", None)
            if callable(repasar):
                repasar()
        self.update()

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

        panel = PantallaPanel(self.motor)
        panel.categoria_elegida.connect(self.ir_a_archivos)
        panel.almacenamiento.connect(self.resumen.poner)
        self.registrar_pantalla("Panel", panel)

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
        self.registrar_pantalla("Configuración IA", PantallaConfiguracion(self.motor))
        self.registrar_pantalla("API", PantallaApi(self.motor))

    # -- estructura ---------------------------------------------------------

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
        #: La caja de cada contador, para reajustar su margen al encoger.
        self._cajas_cuenta: dict[QPushButton, QHBoxLayout] = {}

        #: Los rótulos, para poder quitarlos y devolverlos al encoger.
        self._rotulos_nav: dict[QPushButton, str] = {}

        for indice, (nombre, icono_nombre) in enumerate(PANTALLAS):
            boton = QPushButton(nombre)
            self._rotulos_nav[boton] = nombre
            boton.setToolTip(nombre)
            boton.setObjectName("nav")
            iconos.poner(boton, icono_nombre, 15, "texto_3")
            boton.setCheckable(True)
            boton.setCursor(Qt.PointingHandCursor)
            boton.clicked.connect(
                lambda _marcado=False, i=indice: self.contenido.setCurrentIndex(i)
            )
            self._grupo.addButton(boton, indice)
            self._botones.append(boton)
            self._cuentas[nombre], self._cajas_cuenta[boton] = self._contador(boton)

            envoltorio = QHBoxLayout()
            envoltorio.setContentsMargins(8, 0, 8, 0)
            envoltorio.addWidget(boton)
            columna.addLayout(envoltorio)

        # Justo debajo de la última entrada, no al fondo: las categorías
        # crecen hacia abajo según se llenan, y con el resumen pegado al pie
        # tendrían que empujar hacia arriba. El hueco sobrante queda después.
        self.resumen = ResumenCarril()
        self.resumen.elegida.connect(self.ir_a_archivos)
        columna.addWidget(self.resumen)

        columna.addStretch(1)

        # La versión abajo a la izquierda, como en la interfaz web.
        self.etiqueta_version = QLabel(f"BIMNEMO {self.version}")
        self.etiqueta_version.setObjectName("version")
        columna.addWidget(self.etiqueta_version)

        self._carril_estrecho: Optional[bool] = None
        self._lateral_widget = lateral
        self._rotulo_navegacion = rotulo
        return lateral

    def _encoger_carril(self, estrecho: bool) -> None:
        """Deja el carril en iconos, o lo devuelve entero.

        Se quita el texto pero **no el contador**: saber que hay dos
        archivos esperando importa igual con la ventana estrecha, y es lo
        único que se movería sin avisar. El nombre queda en la ayuda
        emergente.
        """
        if self._carril_estrecho == estrecho:
            return
        self._carril_estrecho = estrecho

        self._lateral_widget.setFixedWidth(
            tema.ANCHO_LATERAL_ESTRECHO if estrecho else tema.ANCHO_LATERAL
        )
        self._rotulo_navegacion.setVisible(not estrecho)
        self.etiqueta_version.setVisible(not estrecho)
        # En sesenta píxeles no cabe ni la cifra ni un chip: se esconde
        # entero en vez de dejar un muñón ilegible.
        self.resumen.setVisible(not estrecho)

        for boton, nombre in self._rotulos_nav.items():
            boton.setText("" if estrecho else nombre)
            boton.setProperty("estrecho", "si" if estrecho else "no")
            boton.style().unpolish(boton)
            boton.style().polish(boton)

        for etiqueta in self._cuentas.values():
            etiqueta.setProperty("estrecho", "si" if estrecho else "no")
            etiqueta.style().unpolish(etiqueta)
            etiqueta.style().polish(etiqueta)

        for caja in self._cajas_cuenta.values():
            # En el carril ancho el número va pegado al borde derecho, a doce
            # píxeles del texto. En el estrecho el botón mide cuarenta y
            # cuatro: con ese mismo margen, el número se salía del botón y no
            # se veía. Se arrima al borde y se sube a la esquina.
            if estrecho:
                caja.setContentsMargins(0, 2, 3, 0)
                caja.setAlignment(Qt.AlignTop | Qt.AlignRight)
            else:
                caja.setContentsMargins(0, 0, 12, 0)
                caja.setAlignment(Qt.Alignment())

    def resizeEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        super().resizeEvent(evento)
        self._encoger_carril(self.width() < tema.ANCHO_VENTANA_CARRIL_ESTRECHO)

    @staticmethod
    def _contador(boton: QPushButton) -> tuple[QLabel, QHBoxLayout]:
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
        return etiqueta, caja

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
