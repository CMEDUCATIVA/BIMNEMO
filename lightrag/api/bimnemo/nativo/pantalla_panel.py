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

from PySide6.QtCore import Qt
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
from lightrag.api.bimnemo.nativo.disposicion import DISPOSICIONES
from lightrag.api.bimnemo.nativo import formato
from lightrag.api.bimnemo.nativo.grafo import Grafo
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Fluida, Tarjeta

#: Por debajo de esto, las dos columnas se apilan.
ANCHO_MINIMO_DOS_COLUMNAS = 1120

#: Ancho de la columna de datos. Fijo y no proporcional: el grafo es lo que
#: se viene a ver, así que todo lo que sobra al ensanchar la ventana se lo
#: queda él. Con una proporción, la columna de texto crecía sin necesidad y
#: le robaba sitio al lienzo.
ANCHO_DATOS = 296

PROFUNDIDADES = ((1, "1 salto"), (2, "2 saltos"), (3, "3 saltos"),
                 (4, "4 saltos"), (5, "5 saltos"))
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
        self.origen.setText(
            "De: " + "\nY de: ".join(documentos) if documentos else ""
        )
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
        marca.setPixmap(iconos.pixmap(icono_nombre, 14, "#3b82f6"))
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
    boton.setIcon(iconos.icono(nombre, 15, "#cbd5e1"))
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
    def __init__(self, motor: Motor) -> None:
        super().__init__()
        self.motor = motor
        self._apilado: Optional[bool] = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(32, 28, 32, 24)
        raiz.setSpacing(14)

        titulo = QLabel("Panel")
        titulo.setObjectName("titulo")
        raiz.addWidget(titulo)

        self.aviso = Aviso()
        raiz.addWidget(self.aviso)

        self.rejilla = QGridLayout()
        self.rejilla.setContentsMargins(0, 0, 0, 0)
        self.rejilla.setHorizontalSpacing(16)
        self.rejilla.setVerticalSpacing(16)
        raiz.addLayout(self.rejilla, 1)

        self.columna_grafo = self._columna_grafo()
        self.columna_datos = self._columna_datos()
        self._colocar_columnas(apilado=False)

        self.refrescar()

    # -- columnas -----------------------------------------------------------

    def _colocar_columnas(self, apilado: bool) -> None:
        """Pone las dos columnas al lado o una encima de otra."""
        if self._apilado == apilado:
            return
        self._apilado = apilado

        self.rejilla.removeWidget(self.columna_grafo)
        self.rejilla.removeWidget(self.columna_datos)

        if apilado:
            self.rejilla.addWidget(self.columna_grafo, 0, 0)
            self.rejilla.addWidget(self.columna_datos, 1, 0)
            self.rejilla.setColumnStretch(0, 1)
            self.rejilla.setColumnStretch(1, 0)
            self.columna_datos.setMaximumWidth(16777215)
            # Apiladas, las tarjetas se reparten a lo ancho en vez de
            # estirarse una debajo de otra.
            self._repartir_cifras(4)
        else:
            self.rejilla.addWidget(self.columna_grafo, 0, 0)
            self.rejilla.addWidget(self.columna_datos, 0, 1)
            self.rejilla.setColumnStretch(0, 1)
            self.rejilla.setColumnStretch(1, 0)
            self.columna_datos.setFixedWidth(ANCHO_DATOS)
            self._repartir_cifras(1)

        self.columna_grafo.show()
        self.columna_datos.show()

    def resizeEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        super().resizeEvent(evento)
        self._colocar_columnas(self.width() < ANCHO_MINIMO_DOS_COLUMNAS)

    # -- columna izquierda: el grafo ----------------------------------------

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
        marca.setPixmap(iconos.pixmap("entidades", 15, "#3b82f6"))
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
        caja.setContentsMargins(1, 1, 1, 1)
        caja.setSpacing(0)

        self.grafo = Grafo()
        self.grafo.elegido.connect(self._pintar_detalle)
        self.grafo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        caja.addWidget(self.grafo, 1)
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
        columna = QVBoxLayout(pie)
        columna.setContentsMargins(12, 10, 12, 10)
        columna.setSpacing(6)

        self.leyenda = QWidget()
        self.leyenda.setObjectName("fila")
        # Envuelve: con nueve tipos y la ventana estrecha, una fila sola les
        # recorta el nombre y deja «conce 79» en vez de «concepto 79».
        self.caja_leyenda = Fluida(separacion=14, salto=4, centrado=True)
        self.leyenda.setLayout(self.caja_leyenda)
        columna.addWidget(self.leyenda)

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
        """Recoloca la ficha cuando el lienzo cambia de tamaño."""
        from PySide6.QtCore import QEvent

        if objeto is self.grafo and evento.type() == QEvent.Resize:
            self.ficha.recolocar()
        return super().eventFilter(objeto, evento)

    def _soltar_seleccion(self) -> None:
        """Cerrar la ficha también suelta la entidad elegida.

        Si no, la ficha desaparece pero el grafo sigue con las relaciones
        aisladas y el resto apagado, y no hay forma de entender por qué.
        """
        self.grafo.soltar()
        self.ficha.ocultar()

    def _barra(self) -> QWidget:
        barra = QWidget()
        barra.setObjectName("fila")
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(0, 2, 0, 2)
        fila.setSpacing(10)

        self.entidad = QComboBox()
        self.entidad.setMinimumWidth(96)
        self.entidad.addItem("Todo el grafo", "*")
        self.entidad.currentIndexChanged.connect(self._cargar_grafo)
        fila.addWidget(_campo("Entidad de partida", self.entidad), 2)

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
        self.disposicion.currentIndexChanged.connect(
            lambda: self.grafo.disponer(self.disposicion.currentData())
        )
        fila.addWidget(_campo("Disposición", self.disposicion, 168))

        self.busqueda = QLineEdit()
        self.busqueda.setMinimumWidth(96)
        self.busqueda.setPlaceholderText("Resaltar por nombre…")
        self.busqueda.textChanged.connect(self._buscar)
        self.campo_busqueda = _campo("Buscar entidad", self.busqueda)
        fila.addWidget(self.campo_busqueda, 2)

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
        fila.addWidget(caja_acciones, 0)
        return barra

    # -- columna derecha: los datos -----------------------------------------

    def _columna_datos(self) -> QWidget:
        envoltorio = QScrollArea()
        envoltorio.setWidgetResizable(True)
        envoltorio.setFrameShape(QFrame.NoFrame)
        envoltorio.setObjectName("conversacion")
        envoltorio.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Sin barra vertical: las cuatro tarjetas caben siempre porque se
        # reparten el alto. Con ella, aparecía y desaparecía al redimensionar
        # y movía el contenido de sitio.
        envoltorio.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        dentro = QWidget()
        dentro.setObjectName("fila")
        # Rejilla y no columna: apiladas, las cuatro tarjetas en una sola
        # columna salían larguísimas y sin forma. En rejilla se reparten en
        # las columnas que quepan y conservan su proporción.
        self.rejilla_cifras = QGridLayout(dentro)
        self.rejilla_cifras.setContentsMargins(0, 0, 8, 0)
        self.rejilla_cifras.setHorizontalSpacing(12)
        self.rejilla_cifras.setVerticalSpacing(12)

        self.cifras: dict[str, Cifra] = {}
        for clave, icono_nombre, rotulo in CIFRAS:
            self.cifras[clave] = Cifra(icono_nombre, rotulo)

        self._columnas_cifras = 0
        self._repartir_cifras(1)

        envoltorio.setWidget(dentro)
        return envoltorio

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

        filas = (len(CIFRAS) - 1) // columnas + 1
        for fila in range(5):
            # Todas las filas con el mismo peso: las tarjetas salen del mismo
            # alto y reparten entre ellas toda la columna, en vez de quedarse
            # arriba con un hueco debajo.
            self.rejilla_cifras.setRowStretch(fila, 1 if fila < filas else 0)

    # -- datos --------------------------------------------------------------

    def refrescar(self) -> None:
        self.motor.get("/bimnemo/stats", self._pintar_cifras, self._fallo)
        self.motor.get("/bimnemo/nemos/stats", self._pintar_agregado, None)
        self.motor.get("/bimnemo/stats/graph", self._pintar_grafo_cifras, None)
        self._cargar_grafo()

    def _pintar_cifras(self, datos: Any) -> None:
        """Lo de ESTA memoria: la cuarta tarjeta."""
        if not isinstance(datos, dict):
            return
        self.aviso.callar()
        memoria = datos.get("memory") or {}

        self.cifras["memoria"].poner(
            formato.numero(memoria.get("total_documents")),
            f"{formato.numero(memoria.get('total_chunks'))} fragmentos "
            "indexados",
        )

        fallo = memoria.get("documents_error") or memoria.get("failed_reason")
        if fallo:
            self.aviso.fallar(str(fallo))

    def _pintar_agregado(self, datos: Any) -> None:
        """Lo de TODAS las memorias: las tres primeras tarjetas.

        Se suman todas porque es lo que se busca al mirar «en general». La
        cuarta no puede sumarse y por eso va aparte: contar los documentos
        indexados de una memoria dormida obligaría a abrirla.
        """
        if not isinstance(datos, dict):
            return
        total = datos.get("total") or {}
        cuantas = int(total.get("nemos") or 0)

        self.cifras["archivos"].poner(
            formato.numero(total.get("total_files")),
            f"En {cuantas} memoria" + ("" if cuantas == 1 else "s"),
        )
        self.cifras["almacenado"].poner(
            formato.tamano(total.get("total_bytes")), "Bytes reales en disco"
        )

        categorias = total.get("categories") or []
        en_uso = sum(1 for c in categorias if (c.get("files") or 0) > 0)
        self.cifras["categorias"].poner(
            f"{en_uso} / {len(categorias)}", "En uso sobre el catálogo"
        )

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
        mejores = sorted(
            nodos, key=lambda n: -int(n.get("degree") or 0)
        )[:120]
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
                f"Buscar entidad · {cuantas} encontrada"
                + ("s" if cuantas != 1 else "")
            )

    def _pintar_detalle(self, nodo: Optional[dict]) -> None:
        if not nodo:
            self.ficha.ocultar()
            return
        self.ficha.mostrar(nodo)

    def _fallo(self, motivo: str) -> None:
        self.aviso.fallar(motivo)
        self.resumen_grafo.setText("No se pudo cargar el grafo.")
