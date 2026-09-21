"""Pantalla «Panel»: el grafo a la izquierda y todo lo demás a la derecha.

## Por qué dos columnas

El grafo es lo que se viene a ver y necesita sitio; las cifras y la ficha de
la entidad elegida son texto y caben en una columna estrecha. En una sola
columna, la ficha aparecía **debajo del grafo**: al pulsar una entidad había
que bajar a leerla y se perdía de vista lo que se acababa de pulsar.

Es responsiva: por debajo de `ANCHO_MINIMO_DOS_COLUMNAS` se apilan, porque
dos columnas en una ventana estrecha son dos columnas ilegibles.

## La barra del grafo

Es la misma de la interfaz web y por los mismos motivos: entidad de partida,
profundidad, nodos máximos, disposición y búsqueda. Sin ella el grafo es una
foto fija; con ella se puede preguntar «¿qué hay alrededor de esto?», que es
para lo que sirve un grafo.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QEvent, Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo import iconos
from lightrag.api.bimnemo.nativo.disposicion import DISPOSICIONES, POR_DEFECTO
from lightrag.api.bimnemo.nativo import formato, panel_piezas
from lightrag.api.bimnemo.nativo.frescura import Frescura
from lightrag.api.bimnemo.nativo.grafo import Grafo
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Fluida, Tarjeta

#: Por debajo de esto, las dos columnas se apilan.
#: Medido, no elegido: la columna del grafo pide 1.008 px —su barra de
#: controles— y la de datos 296, más el espacio entre ellas y los márgenes.
#: Por debajo de esto las dos columnas no caben, y lo que sobra se recorta
#: por la derecha en vez de encogerse.
#: A partir de qué ancho caben las cuatro tarjetas de cifra en una fila, en
#: dos, o en una sola. Es lo único que cambia al encoger la ventana: el grafo
#: manda siempre en la primera sección, a todo lo ancho.
ANCHO_CUATRO_CIFRAS = 1000
ANCHO_DOS_CIFRAS = 560

#: Ancho de la columna de datos. Fijo y no proporcional: el grafo es lo que
#: se viene a ver, así que todo lo que sobra al ensanchar la ventana se lo
#: queda él. Con una proporción, la columna de texto crecía sin necesidad y
#: le robaba sitio al lienzo.
ANCHO_DATOS = 296

#: Alto de la banda de tarjetas cuando van apiladas debajo del grafo. Es su
#: alto natural más el aire: repartirse el alto con el grafo dejaría el
#: lienzo por la mitad, y apilado la primera sección **es** el grafo.
ALTO_CIFRAS_APILADAS = 116

#: Lo que se le reserva al grafo dentro del área con desplazamiento.
ALTO_MINIMO_GRAFO = 520

#: Cada cuánto late el grafo por su cuenta.
LATIDO_MS = 5000

#: Cada cuánto se pregunta si alguien ha usado la memoria.
#:
#: Dos segundos y no medio: es una petición más contra el motor, y lo que se
#: gana con ir más deprisa es que la sinapsis salga un segundo antes. La
#: propia consulta no cuenta como uso, así que no se muerde la cola.
SONDEO_PULSO_MS = 2000

PROFUNDIDADES = (
    (1, "1 salto"),
    (2, "2 saltos"),
    (3, "3 saltos"),
    (4, "4 saltos"),
    (5, "5 saltos"),
)
TOPES = (100, 250, 500, 1000)
TOPE_POR_DEFECTO = 250

#: Las cuatro tarjetas del panel, las mismas que la web y en su orden.
#: Cada una: clave, icono y rótulo.
#:
#: Las tres primeras suman **todas** las memorias, que es lo que se pide al
#: mirar «en general». La cuarta es la excepción y lo dice en su rótulo: los
#: documentos indexados son los de la memoria abierta, porque contar los de
#: una dormida obligaría a abrirla — seis grafos en RAM por pintar una cifra.
CIFRAS = (
    ("archivos", "ficheros", "Archivos"),
    ("almacenado", "disco", "Total almacenado"),
    ("categorias", "trozos", "Categorías"),
    ("memoria", "documento", "En esta memoria"),
)

#: Ancho de la ficha dentro del lienzo, y su separación del borde.
ANCHO_FICHA = 286
MARGEN_FICHA = 14

#: Con qué separa LightRAG los trozos que ha fundido en una sola entidad.
#:
#: Cuando la misma entidad aparece en varios documentos, el motor concatena
#: sus descripciones con esta marca. Enseñarla en crudo deja un «<SEP>» en
#: mitad de la frase que no significa nada para quien lo lee.
SEPARADOR = "<SEP>"


def _partes(texto: str) -> list[str]:
    """Los trozos que el motor fundió, cada uno por su lado."""
    return [t.strip() for t in str(texto or "").split(SEPARADOR) if t.strip()]


class Ficha(QFrame):
    """La ficha de una entidad, flotando sobre el lienzo del grafo.

    Es hija del widget del grafo y se coloca a mano sobre su lado derecho,
    no dentro de ninguna disposición: una ficha que empuja el lienzo lo
    encoge al abrirse y mueve de sitio lo que el usuario acaba de pulsar.
    """

    from PySide6.QtCore import Signal as _Signal

    cerrada = _Signal()

    def __init__(self, lienzo: QWidget) -> None:
        super().__init__(lienzo)
        self.setObjectName("ficha")
        self.setFixedWidth(ANCHO_FICHA)

        columna = QVBoxLayout(self)
        columna.setContentsMargins(14, 12, 14, 14)
        columna.setSpacing(8)

        cabecera = QWidget()
        cabecera.setObjectName("fila")
        fila = QHBoxLayout(cabecera)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(8)

        self.nombre = QLabel("—")
        self.nombre.setObjectName("ficha-nombre")
        self.nombre.setWordWrap(True)
        fila.addWidget(self.nombre, 1)

        cerrar = QPushButton("✕")
        cerrar.setObjectName("ficha-cerrar")
        cerrar.setCursor(Qt.PointingHandCursor)
        cerrar.setFixedSize(24, 24)
        cerrar.setToolTip("Cerrar la ficha")
        cerrar.clicked.connect(self.cerrada.emit)
        fila.addWidget(cerrar, 0, Qt.AlignTop)
        columna.addWidget(cabecera)

        self.insignia = QLabel("")
        self.insignia.setObjectName("ficha-tipo")
        columna.addWidget(self.insignia)

        self.relaciones = QLabel("")
        self.relaciones.setObjectName("descripcion")
        columna.addWidget(self.relaciones)

        self.descripcion = QLabel("")
        self.descripcion.setObjectName("ficha-texto")
        self.descripcion.setWordWrap(True)
        self.descripcion.setTextInteractionFlags(Qt.TextSelectableByMouse)
        columna.addWidget(self.descripcion)

        self.origen = QLabel("")
        self.origen.setObjectName("descripcion")
        self.origen.setWordWrap(True)
        columna.addWidget(self.origen)

        columna.addStretch(1)
        self.hide()

    def mostrar(self, nodo: dict) -> None:
        self.nombre.setText(str(nodo.get("label") or nodo.get("id") or "—"))

        tipo = str(nodo.get("type") or "")
        self.insignia.setText(tipo.upper() if tipo else "")
        self.insignia.setVisible(bool(tipo))

        grado = nodo.get("degree")
        self.relaciones.setText(
            f"{formato.numero(grado)} relaciones" if grado is not None else ""
        )

        # Una línea en blanco entre trozos, no un «<SEP>» a media frase.
        trozos = _partes(nodo.get("description"))
        self.descripcion.setText("\n\n".join(trozos))
        self.descripcion.setVisible(bool(trozos))

        documentos = _partes(nodo.get("file_path"))
        self.origen.setText("De: " + "\nY de: ".join(documentos) if documentos else "")
        self.origen.setVisible(bool(documentos))

        self.recolocar()
        self.show()
        self.raise_()

    def ocultar(self) -> None:
        self.hide()

    def recolocar(self) -> None:
        """Arriba a la derecha del lienzo, sin salirse ni taparlo entero."""
        padre = self.parentWidget()
        if padre is None:
            return

        # Se encoge con el lienzo: con la ventana estrecha, una ficha de 286
        # píxeles fijos tapaba casi la mitad del grafo, y la gracia de tenerla
        # dentro es poder mirar las dos cosas a la vez.
        ancho = max(200, min(ANCHO_FICHA, int(padre.width() * 0.42)))
        self.setFixedWidth(ancho)

        alto = min(
            max(self.sizeHint().height(), 120),
            max(padre.height() - 2 * MARGEN_FICHA, 120),
        )
        self.setFixedHeight(alto)
        self.move(padre.width() - ancho - MARGEN_FICHA, MARGEN_FICHA)


class Cifra(QFrame):
    """Una tarjeta de cifra, la misma que las del panel web.

    Icono y rótulo en mayúsculas arriba, el número grande en medio y una
    nota debajo. La nota no es adorno: «5,4 MB» a secas no dice si son los
    bytes en disco o lo indexado, y «2 / 8» sin «en uso sobre el catálogo»
    no se entiende en absoluto.
    """

    def __init__(self, icono_nombre: str, rotulo: str) -> None:
        super().__init__()
        self.setObjectName("cifra-tarjeta")

        columna = QVBoxLayout(self)
        columna.setContentsMargins(16, 14, 16, 14)
        columna.setSpacing(2)
        # Centrado vertical: las tarjetas se reparten el alto de la columna,
        # así que sin esto el rótulo se pega arriba y la nota abajo, con un
        # agujero de cien píxeles en medio.
        columna.addStretch(1)

        cabecera = QWidget()
        cabecera.setObjectName("fila")
        fila = QHBoxLayout(cabecera)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(7)

        marca = QLabel()
        iconos.poner(marca, icono_nombre, 14, "azul")
        fila.addWidget(marca)

        etiqueta = QLabel(rotulo.upper())
        etiqueta.setObjectName("cifra-rotulo")
        fila.addWidget(etiqueta, 1)
        columna.addWidget(cabecera)

        self.valor = QLabel("…")
        self.valor.setObjectName("cifra")
        columna.addWidget(self.valor)

        self.nota = QLabel("")
        self.nota.setObjectName("cifra-nota")
        self.nota.setWordWrap(True)
        columna.addWidget(self.nota)
        columna.addStretch(1)

    def poner(self, valor: str, nota: str = "") -> None:
        self.valor.setText(valor)
        self.nota.setText(nota)


def _boton_icono(nombre: str, pista: str) -> QPushButton:
    boton = QPushButton()
    boton.setObjectName("icono")
    iconos.poner(boton, nombre, 15, "texto_2")
    boton.setToolTip(pista)
    boton.setCursor(Qt.PointingHandCursor)
    boton.setFixedSize(32, 30)
    return boton


def _campo(rotulo: str, control: QWidget, ancho: int = 0) -> QWidget:
    """Un control con su rótulo encima, como en la barra de la web."""
    caja = QWidget()
    caja.setObjectName("fila")
    columna = QVBoxLayout(caja)
    columna.setContentsMargins(0, 0, 0, 0)
    columna.setSpacing(3)

    etiqueta = QLabel(rotulo)
    etiqueta.setObjectName("rotulo-campo")
    # Alto fijo: el grupo de botones lleva un rótulo vacío, y sin esto su
    # etiqueta medía distinto que las demás y los botones quedaban unos
    # píxeles más abajo — desde fuera, «en una segunda fila».
    etiqueta.setFixedHeight(14)
    columna.addWidget(etiqueta)
    columna.addWidget(control)
    if ancho:
        caja.setFixedWidth(ancho)
    return caja


class PantallaPanel(QWidget):
    #: Han pulsado una categoría: hay que ir a Archivos con ese filtro.
    categoria_elegida = Signal(str)
    #: Lo que ocupa la memoria abierta, recién leído. Lo escucha el carril
    #: para enseñarlo al pie sin pedirlo otra vez.
    almacenamiento = Signal(dict)

    def __init__(self, motor: Motor) -> None:
        super().__init__()
        self.motor = motor
        self._apilado: Optional[bool] = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        # Con desplazamiento: el panel ya no cabe en una pantalla —grafo,
        # cifras, reparto del disco, memorias, categorías y tipos—, y lo que
        # no cabe tiene que poder alcanzarse.
        self.area = QScrollArea()
        area = self.area
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        # La horizontal, solo si hace falta: en una ventana estrecha la barra
        # del grafo no se encoge más, y es mejor poder desplazarse hasta ella
        # que perderla recortada contra el borde.
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        raiz.addWidget(area)

        dentro = QWidget()
        columna = QVBoxLayout(dentro)
        columna.setContentsMargins(32, 28, 32, 24)
        columna.setSpacing(14)
        area.setWidget(dentro)
        # El alto de referencia es el del hueco visible, no el de la pantalla:
        # son distintos en cuanto aparece una barra de desplazamiento, y es
        # el visible el que decide dónde cae el pliegue.
        area.viewport().installEventFilter(self)

        self.titulo_pantalla = QLabel("Panel")
        self.titulo_pantalla.setObjectName("titulo")
        columna.addWidget(self.titulo_pantalla)

        self.aviso = Aviso()
        columna.addWidget(self.aviso)

        self.columna_contenido = columna

        # PRIMERA SECCIÓN: el grafo, solo y a todo lo ancho. Es a lo que se
        # viene al panel, así que no comparte pantalla con nada —tampoco con
        # la ventana grande—. Las cifras y el resto van debajo.
        self.primera_seccion = self._columna_grafo()
        self.primera_seccion.setMinimumHeight(ALTO_MINIMO_GRAFO)
        columna.addWidget(self.primera_seccion)

        # SEGUNDA SECCIÓN: los datos, uno detrás de otro.
        columna.addWidget(self._columna_datos())
        columna.addWidget(self._almacenamiento())
        columna.addWidget(self._categorias_y_tipos())
        columna.addStretch(1)

        # El grafo late solo cada cinco segundos, y además cada vez que
        # alguien usa la memoria por la API.
        self._pulso_visto: Optional[int] = None

        self._latido = QTimer(self)
        self._latido.setInterval(LATIDO_MS)
        self._latido.timeout.connect(self._latir)
        self._latido.start()

        self._sondeo_pulso = QTimer(self)
        self._sondeo_pulso.setInterval(SONDEO_PULSO_MS)
        self._sondeo_pulso.timeout.connect(self._mirar_pulso)
        self._sondeo_pulso.start()

        # Lo subido en Archivos aparece aquí sin tener que pulsar «Releer».
        self.frescura = Frescura(self.motor, self)
        self.frescura.cambiaron.connect(self._datos_nuevos)

        self.refrescar()

    # -- latido -------------------------------------------------------------

    def _latir(self) -> None:
        """El latido de fondo. Solo si la pantalla está a la vista.

        Un grafo animándose en una pestaña que nadie mira es un ventilador
        encendido para nada.
        """
        if self.isVisible():
            self.grafo.disparar_sinapsis()

    def _mirar_pulso(self) -> None:
        self.motor.get("/bimnemo/pulso", self._pulso, None)

    def _pulso(self, datos: Any) -> None:
        """Enciende el grafo cuando alguien ha usado la memoria.

        La primera respuesta solo se apunta: al abrir, el contador ya trae
        todo lo que se usó antes, y dispararlo sería un fogonazo por cosas
        que pasaron ayer.
        """
        if not isinstance(datos, dict):
            return
        total = datos.get("total")
        if not isinstance(total, int):
            return

        if self._pulso_visto is None:
            self._pulso_visto = total
            return

        cuantas = total - self._pulso_visto
        self._pulso_visto = total
        if cuantas <= 0 or not self.isVisible():
            return

        # Una sinapsis por llamada, hasta tres: con una ráfaga de veinte,
        # el grafo se enciende entero y no se distingue nada.
        for _ in range(min(cuantas, 3)):
            self.grafo.disparar_sinapsis()

    # -- columnas -----------------------------------------------------------

    def resizeEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        super().resizeEvent(evento)
        ancho = self.width()
        if ancho >= ANCHO_CUATRO_CIFRAS:
            self._repartir_cifras(4)
        elif ancho >= ANCHO_DOS_CIFRAS:
            self._repartir_cifras(2)
        else:
            self._repartir_cifras(1)

    def _primera_seccion_a_pantalla(self) -> None:
        """El grafo y sus cifras ocupan la pantalla entera; el resto, debajo.

        Es a lo que se viene al panel. Con todo apilado en la misma pantalla,
        cada bloque nuevo le robaba alto al grafo hasta dejarlo en una franja
        — y lo que se pierde ahí no se recupera desplazándose, porque el
        grafo se dibuja en el hueco que le quede.

        Lo demás empieza justo bajo el pliegue: la barra de desplazamiento
        dice que hay más, y se llega bajando.
        """
        margenes = self.columna_contenido.contentsMargins()
        separacion = self.columna_contenido.spacing()

        encabezado = margenes.top() + self.titulo_pantalla.height() + separacion
        if not self.aviso.isHidden():
            encabezado += self.aviso.height() + separacion

        alto = self.area.viewport().height() - encabezado - margenes.bottom()
        self.primera_seccion.setFixedHeight(max(ALTO_MINIMO_GRAFO, alto))

    # -- columna izquierda: el grafo ----------------------------------------

    # -- secciones de abajo -------------------------------------------------

    def _seccion(self, icono: str, titulo: str) -> tuple:
        """Una tarjeta con su encabezado y un rótulo suelto a la derecha."""
        tarjeta = Tarjeta()

        cabecera = QWidget()
        cabecera.setObjectName("fila")
        fila = QHBoxLayout(cabecera)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(8)

        marca = QLabel()
        iconos.poner(marca, icono, 15, "azul")
        fila.addWidget(marca)

        rotulo = QLabel(titulo)
        rotulo.setObjectName("subtitulo")
        fila.addWidget(rotulo)
        fila.addStretch(1)

        pista = QLabel("")
        pista.setObjectName("pista")
        fila.addWidget(pista)

        tarjeta.anadir(cabecera)
        return tarjeta, pista

    def _almacenamiento(self) -> QWidget:
        """El reparto del disco por categoría, sumando todas las memorias."""
        tarjeta, self.pista_almacenado = self._seccion(
            "disco", "Almacenamiento por categoría"
        )

        self.medidor = panel_piezas.Medidor()
        tarjeta.anadir(self.medidor)

        self.leyenda = panel_piezas.Leyenda()
        tarjeta.anadir(self.leyenda)
        return tarjeta

    def _categorias_y_tipos(self) -> QWidget:
        """Las dos juntas: el catálogo a la izquierda y los tipos a la derecha.

        Comparten fila porque contestan la misma pregunta a dos niveles —qué
        hay guardado—, y separadas dejaban media pantalla vacía.
        """
        caja_exterior = QWidget()
        caja_exterior.setObjectName("fila")
        fila = QHBoxLayout(caja_exterior)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(14)

        izquierda, self.pista_categorias = self._seccion("categorias", "Categorías")
        self.rejilla_categorias = panel_piezas.RejillaCategorias()
        self.rejilla_categorias.elegida.connect(self.categoria_elegida.emit)
        izquierda.anadir(self.rejilla_categorias)
        fila.addWidget(izquierda, 2)

        derecha, self.pista_tipos = self._seccion("tipos", "Tipos de archivo")
        self.lista_tipos = panel_piezas.ListaTipos()
        derecha.anadir(self.lista_tipos)
        derecha.columna.addStretch(1)
        fila.addWidget(derecha, 1)
        return caja_exterior

    def _columna_grafo(self) -> QWidget:
        # La tarjeta con su borde: el grafo es una sección de la pantalla y
        # tiene que verse como tal.
        #
        # Antes esto produjo una franja fea debajo del pie, y por eso la
        # quité entera — que fue pasarse. La franja no la causaba la
        # tarjeta, sino que el pie llevaba **fondo propio**: dejaba una
        # banda de otro color y, debajo, el margen de la tarjeta parecía una
        # segunda barra. Ahora el pie va sin fondo, solo con una línea
        # encima, dentro de la caja del lienzo.
        tarjeta = Tarjeta()

        cabecera = QWidget()
        cabecera.setObjectName("fila")
        fila = QHBoxLayout(cabecera)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(8)

        marca = QLabel()
        iconos.poner(marca, "entidades", 15, "azul")
        fila.addWidget(marca)

        titulo = QLabel("Grafo de conocimiento")
        titulo.setObjectName("subtitulo")
        fila.addWidget(titulo)
        fila.addStretch(1)

        self.resumen_grafo = QLabel("—")
        self.resumen_grafo.setObjectName("descripcion")
        fila.addWidget(self.resumen_grafo)
        tarjeta.anadir(cabecera)

        tarjeta.anadir(self._barra())

        # El lienzo y su pie van dentro de UN marco con esquinas
        # redondeadas. Sueltos en la tarjeta, el lienzo pintaba hasta el
        # borde recto y se salía de las esquinas de la tarjeta, y el pie
        # quedaba debajo como algo aparte.
        self.caja_lienzo = QFrame()
        self.caja_lienzo.setObjectName("caja-grafo")
        caja = QVBoxLayout(self.caja_lienzo)
        # Sin márgenes: el lienzo llega a los bordes del box, como debe ser
        # si son la misma cosa. Lo único que separa el dibujo de los datos
        # de abajo es la línea que va entre los dos.
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(0)

        self.grafo = Grafo()
        self.grafo.elegido.connect(self._pintar_detalle)
        self.grafo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        caja.addWidget(self.grafo, 1)

        # Una línea de un píxel, de borde a borde. No es un marco: es lo que
        # dice dónde acaba el dibujo. Sin ella, y con el mismo fondo, la
        # leyenda parecía escrita encima del grafo — y al estrechar la
        # ventana se juntaban del todo.
        separador = QFrame()
        separador.setObjectName("separador-grafo")
        separador.setFixedHeight(1)
        caja.addWidget(separador)

        caja.addWidget(self._pie())

        tarjeta.anadir(self.caja_lienzo)

        # La ficha vive **dentro** del lienzo, pegada a su lado derecho: es
        # hija del grafo, no una tarjeta más de la columna. Así se lee sin
        # apartar la vista de la entidad que se acaba de pulsar.
        self.ficha = Ficha(self.grafo)
        self.ficha.cerrada.connect(self._soltar_seleccion)
        self.grafo.installEventFilter(self)

        return tarjeta

    def _pie(self) -> QWidget:
        """Leyenda y ayuda, en el hueco de abajo de la caja del grafo.

        Sin fondo, sin línea y sin banda: nada encima de nada. El lienzo
        ocupa menos alto y en el espacio que deja, dentro de la misma caja,
        van la leyenda y la ayuda, centradas.
        """
        pie = QFrame()
        pie.setObjectName("pie-grafo")
        # Toma el alto que necesite y ni uno más: el que cede es el lienzo.
        pie.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        columna = QVBoxLayout(pie)
        columna.setContentsMargins(14, 12, 14, 12)
        columna.setSpacing(6)

        # `leyenda_tipos` y no `leyenda`: en esta pantalla hay **dos**
        # leyendas —la de tipos de entidad del grafo y la del reparto del
        # disco— y las dos se llamaban igual. La segunda en construirse
        # pisaba a la primera, y al pintar el reparto se llamaba a un
        # método que el widget del grafo no tiene.
        self.leyenda_tipos = QWidget()
        self.leyenda_tipos.setObjectName("fila")
        # Envuelve: con nueve tipos y la ventana estrecha, una fila sola les
        # recorta el nombre y deja «conce 79» en vez de «concepto 79».
        self.caja_leyenda = Fluida(separacion=14, salto=4, centrado=True)
        self.leyenda_tipos.setLayout(self.caja_leyenda)
        columna.addWidget(self.leyenda_tipos)

        ayuda = QLabel(
            "Arrastra para mover el lienzo, rueda para acercar, y pulsa una "
            "entidad para ver su ficha y aislar sus relaciones."
        )
        ayuda.setObjectName("descripcion")
        ayuda.setWordWrap(True)
        ayuda.setAlignment(Qt.AlignHCenter)
        columna.addWidget(ayuda)
        return pie

    def eventFilter(self, objeto, evento):  # noqa: N802 (nombre de Qt)
        """Dos vigilados, y solo puede haber un filtro por clase.

        El lienzo, para recolocar la ficha flotante cuando cambia de tamaño;
        y el hueco visible del desplazamiento, para que la primera sección
        siga ocupando exactamente una pantalla.
        """
        if evento.type() == QEvent.Resize:
            if objeto is self.grafo:
                self.ficha.recolocar()
            elif objeto is self.area.viewport():
                self._primera_seccion_a_pantalla()
        return super().eventFilter(objeto, evento)

    def _soltar_seleccion(self) -> None:
        """Cerrar la ficha también suelta la entidad elegida.

        Si no, la ficha desaparece pero el grafo sigue con las relaciones
        aisladas y el resto apagado, y no hay forma de entender por qué.
        """
        self.grafo.soltar()
        self.ficha.ocultar()

    def _barra(self) -> QWidget:
        """Los controles del grafo, en disposición fluida.

        Con una fila normal, sus seis controles pedían 1.008 píxeles y por
        debajo de eso la ventana sacaba barra de desplazamiento horizontal —
        justo lo que no quieres al encoger. Fluida los pasa a una segunda
        línea y el grafo sigue ocupando lo que haya.
        """
        barra = QWidget()
        barra.setObjectName("fila")
        fila = Fluida(separacion=10, salto=8)
        barra.setLayout(fila)

        self.entidad = QComboBox()
        self.entidad.setMinimumWidth(96)
        self.entidad.addItem("Todo el grafo", "*")
        self.entidad.currentIndexChanged.connect(self._cargar_grafo)
        fila.addWidget(_campo("Entidad de partida", self.entidad, 240))

        self.profundidad = QComboBox()
        for valor, rotulo in PROFUNDIDADES:
            self.profundidad.addItem(rotulo, valor)
        self.profundidad.setCurrentIndex(2)
        self.profundidad.currentIndexChanged.connect(self._cargar_grafo)
        fila.addWidget(_campo("Profundidad", self.profundidad, 112))

        self.tope = QComboBox()
        for valor in TOPES:
            self.tope.addItem(str(valor), valor)
        self.tope.setCurrentIndex(TOPES.index(TOPE_POR_DEFECTO))
        self.tope.currentIndexChanged.connect(self._cargar_grafo)
        fila.addWidget(_campo("Nodos máx.", self.tope, 96))

        self.disposicion = QComboBox()
        for clave, rotulo, _clase in DISPOSICIONES:
            self.disposicion.addItem(rotulo, clave)
        # El selector arranca en la misma que el lienzo: si no, enseñaría
        # «Fuerzas» mientras el grafo ya está dibujando el cerebro.
        self.disposicion.setCurrentIndex(
            [c for c, _r, _k in DISPOSICIONES].index(POR_DEFECTO)
        )
        self.disposicion.currentIndexChanged.connect(
            lambda: self.grafo.disponer(self.disposicion.currentData())
        )
        fila.addWidget(_campo("Disposición", self.disposicion, 168))

        self.busqueda = QLineEdit()
        self.busqueda.setMinimumWidth(96)
        self.busqueda.setPlaceholderText("Resaltar por nombre…")
        self.busqueda.textChanged.connect(self._buscar)
        self.campo_busqueda = _campo("Buscar entidad", self.busqueda, 220)
        fila.addWidget(self.campo_busqueda)

        acciones = QWidget()
        acciones.setObjectName("fila")
        caja = QHBoxLayout(acciones)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(4)
        for nombre, pista, accion in (
            ("alejar", "Alejar", lambda: self.grafo.alejar()),
            ("acercar", "Acercar", lambda: self.grafo.acercar()),
            ("encajar", "Encajar el grafo", lambda: self.grafo.encuadrar()),
            ("recargar", "Volver a leer el grafo", self.refrescar),
        ):
            boton = _boton_icono(nombre, pista)
            boton.clicked.connect(accion)
            caja.addWidget(boton)
        # El grupo de botones no se encoge ni se va de fila: ancho fijo y
        # al final. Lo que cede sitio al estrechar son los desplegables.
        caja_acciones = _campo("", acciones, 32 * 4 + 4 * 3)
        fila.addWidget(caja_acciones)
        return barra

    # -- columna derecha: los datos -----------------------------------------

    def _columna_datos(self) -> QWidget:
        """Las cuatro cifras, en fila debajo del grafo."""
        caja = QWidget()
        caja.setObjectName("fila")
        # Rejilla y no fila: al encoger la ventana las tarjetas pasan a dos
        # columnas y luego a una, en vez de estrecharse hasta no leerse.
        self.rejilla_cifras = QGridLayout(caja)
        self.rejilla_cifras.setContentsMargins(0, 0, 0, 0)
        self.rejilla_cifras.setHorizontalSpacing(12)
        self.rejilla_cifras.setVerticalSpacing(12)

        self.cifras: dict[str, Cifra] = {}
        for clave, icono_nombre, rotulo in CIFRAS:
            self.cifras[clave] = Cifra(icono_nombre, rotulo)

        self._columnas_cifras = 0
        self._repartir_cifras(4)
        return caja

    def _repartir_cifras(self, columnas: int) -> None:
        """Coloca las cuatro tarjetas en el número de columnas que se pida."""
        if columnas == self._columnas_cifras:
            return
        self._columnas_cifras = columnas

        for pieza in self.cifras.values():
            self.rejilla_cifras.removeWidget(pieza)

        for puesto, clave in enumerate(c for c, _i, _r in CIFRAS):
            self.rejilla_cifras.addWidget(
                self.cifras[clave], puesto // columnas, puesto % columnas
            )
            self.cifras[clave].show()

        for columna in range(4):
            self.rejilla_cifras.setColumnStretch(
                columna, 1 if columna < columnas else 0
            )

        # Sin estirar filas: aquí las tarjetas tienen el alto que piden. El
        # que sobra es del grafo, que está arriba.
        for fila in range(5):
            self.rejilla_cifras.setRowStretch(fila, 0)

    # -- datos --------------------------------------------------------------

    def otra_memoria(self) -> None:
        """Se ha abierto otra memoria: el panel empieza de cero.

        La entidad de partida y lo que hubiera escrito en «buscar» eran de la
        memoria anterior, **y una entidad de aquella no tiene por qué existir
        en esta**: dejar el selector puesto pide el grafo de algo que ya no
        está, y vuelve vacío. Es lo mismo que hace la web, que reinicia el
        grafo al cambiar de memoria.

        Las cifras se vacían a la vez. Abrir una memoria dormida tarda unos
        segundos, y dejar las de la anterior mientras tanto es enseñar datos
        de otra memoria como si fueran de esta.
        """
        self.entidad.blockSignals(True)
        self.entidad.clear()
        self.entidad.addItem("Todo el grafo", "*")
        self.entidad.blockSignals(False)

        self.busqueda.blockSignals(True)
        self.busqueda.clear()
        self.busqueda.blockSignals(False)

        for cifra in self.cifras.values():
            cifra.poner("…", "")
        self.grafo.poner([], [])
        self.resumen_grafo.setText("Cargando…")
        self.lista_tipos.poner([], 0)
        self.pista_tipos.setText("")
        self.medidor.poner([], 0)
        self.leyenda.poner([], 0)
        self.rejilla_categorias.poner([], 0)
        self.pista_almacenado.setText("")
        self.pista_categorias.setText("")

    def retematizar(self) -> None:
        """El lienzo del grafo se pinta a mano: hay que pedirle que repinte."""
        self.grafo.update()

    def refrescar(self) -> None:
        self.frescura.olvidar()
        self._releer_cifras()
        self._cargar_grafo()

    def _releer_cifras(self) -> None:
        self.motor.get("/bimnemo/stats", self._pintar_cifras, self._fallo)
        self.motor.get("/bimnemo/stats/graph", self._pintar_grafo_cifras, None)

    def _datos_nuevos(self, con_grafo: bool) -> None:
        """La memoria ha cambiado desde que se pintó el panel.

        Con el motor indexando y la pantalla a la vista, solo las cifras: el
        grafo se redibujaría con cada documento y desharía lo que se estuviera
        mirando. Al volver a la pantalla, o cuando el motor termina, todo.
        """
        if con_grafo:
            self.refrescar()
        else:
            self._releer_cifras()

    def _pintar_cifras(self, datos: Any) -> None:
        """Todo el panel, con lo que hay en la memoria abierta.

        Una sola lectura —`/bimnemo/stats` de esa memoria— alimenta las
        cuatro cifras, el reparto del disco, el catálogo de categorías y los
        tipos. Antes había otra que sumaba todas las memorias, y era la que
        hacía que el panel no se enterara de a cuál estabas mirando.
        """
        if not isinstance(datos, dict):
            return
        self.aviso.callar()
        memoria = datos.get("memory") or {}
        almacen = datos.get("storage") or {}
        octetos = almacen.get("total_bytes")

        en_uso = int(almacen.get("categories_in_use") or 0)
        del_catalogo = int(almacen.get("categories_available") or 0)

        self.cifras["archivos"].poner(
            formato.numero(almacen.get("total_files")), "En esta memoria"
        )
        self.cifras["almacenado"].poner(
            formato.tamano(octetos), "Bytes reales en disco"
        )
        self.cifras["categorias"].poner(
            f"{en_uso} / {del_catalogo}", "En uso sobre el catálogo"
        )
        self.cifras["memoria"].poner(
            formato.numero(memoria.get("total_documents")),
            f"{formato.numero(memoria.get('total_chunks'))} fragmentos indexados",
        )

        categorias = almacen.get("categories") or []
        self.pista_almacenado.setText(formato.tamano(octetos))
        self.medidor.poner(categorias, octetos)
        self.leyenda.poner(categorias, octetos)

        self.pista_categorias.setText(f"{en_uso} de {del_catalogo} en uso")
        self.rejilla_categorias.poner(categorias, octetos)

        self.almacenamiento.emit(almacen)

        tipos = almacen.get("types") or []
        self.pista_tipos.setText(
            f"{len(tipos)} tipo" + ("" if len(tipos) == 1 else "s")
        )
        self.lista_tipos.poner(tipos, octetos)

        fallo = memoria.get("documents_error") or memoria.get("failed_reason")
        if fallo and memoria.get("failed_kind") == "duplicate":
            # Una copia repetida no es un error: no falta nada. Se dice en el
            # tono de un aviso, con lo que hay que hacer, no en rojo.
            self.aviso.informar(str(fallo))
        elif fallo:
            self.aviso.fallar(str(fallo))

    def _pintar_grafo_cifras(self, datos: Any) -> None:
        """El total del grafo, al lado del título.

        No lleva tarjeta propia: lo que el grafo dibuja ya se dice en su
        cabecera, y una tarjeta con el total del grafo al lado de otra con
        lo que se está viendo invita a compararlas y a confundirse.
        """
        if not isinstance(datos, dict):
            return
        self._total_grafo = (datos.get("entities"), datos.get("relations"))

    def _cargar_grafo(self) -> None:
        etiqueta = self.entidad.currentData() or "*"
        salto = self.profundidad.currentData() or 3
        tope = self.tope.currentData() or TOPE_POR_DEFECTO
        self.resumen_grafo.setText("Cargando…")

        from urllib.parse import quote

        self.motor.get(
            f"/bimnemo/graph?label={quote(str(etiqueta))}"
            f"&max_depth={salto}&max_nodes={tope}",
            self._pintar_grafo,
            self._fallo,
        )

    def _pintar_grafo(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        nodos = datos.get("nodes") or []
        aristas = datos.get("edges") or []
        self.grafo.poner(nodos, aristas)
        self.grafo.disponer(self.disposicion.currentData())
        self.grafo.encuadrar()

        texto = f"{len(nodos)} entidades · {len(aristas)} relaciones"
        if datos.get("truncated"):
            # Decirlo importa: sin esto, quien mira cree que su memoria
            # entera es lo que ve, y no lo es.
            texto += " · hay más de las que caben"
        self.resumen_grafo.setText(texto)

        self._pintar_leyenda()
        self._llenar_entidades(nodos)

    def _pintar_leyenda(self) -> None:
        """Un punto de color, el tipo y cuántos hay, como en la web."""
        while self.caja_leyenda.count():
            viejo = self.caja_leyenda.takeAt(0)
            if viejo.widget():
                viejo.widget().deleteLater()

        for tipo, cuantos, color in self.grafo.tipos():
            pieza = QWidget()
            pieza.setObjectName("fila")
            caja = QHBoxLayout(pieza)
            caja.setContentsMargins(0, 0, 0, 0)
            caja.setSpacing(5)

            punto = QLabel("●")
            punto.setStyleSheet(f"color: {color.name()}; font-size: 13px;")
            caja.addWidget(punto)

            nombre = QLabel(tipo)
            nombre.setObjectName("dato-valor")
            caja.addWidget(nombre)

            cuenta = QLabel(str(cuantos))
            cuenta.setObjectName("descripcion")
            caja.addWidget(cuenta)

            self.caja_leyenda.addWidget(pieza)

    def _llenar_entidades(self, nodos: list[dict]) -> None:
        """El selector de entidad de partida, con las más conectadas primero.

        Solo se rellena cuando se está viendo el grafo entero: si ya se ha
        filtrado por una entidad, la lista que llega es la de su vecindario y
        reescribir el selector con ella perdería el resto del grafo.
        """
        if self.entidad.currentData() != "*" or self.entidad.count() > 1:
            return
        mejores = sorted(nodos, key=lambda n: -int(n.get("degree") or 0))[:120]
        self.entidad.blockSignals(True)
        for n in mejores:
            nombre = str(n.get("label") or n.get("id") or "")
            if nombre:
                self.entidad.addItem(nombre, nombre)
        self.entidad.blockSignals(False)

    def _buscar(self, texto: str) -> None:
        cuantas = self.grafo.resaltar(texto)
        etiqueta = self.campo_busqueda.findChild(QLabel)
        if etiqueta is None:
            return
        if not texto.strip():
            etiqueta.setText("Buscar entidad")
        else:
            etiqueta.setText(
                f"Buscar entidad · {cuantas} encontrada" + ("s" if cuantas != 1 else "")
            )

    def _pintar_detalle(self, nodo: Optional[dict]) -> None:
        if not nodo:
            self.ficha.ocultar()
            return
        self.ficha.mostrar(nodo)

    def _fallo(self, motivo: str) -> None:
        self.aviso.fallar(motivo)
        self.resumen_grafo.setText("No se pudo cargar el grafo.")
