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

#: Las cifras del panel: icono y rótulo de cada dato.
CIFRAS = {
    "archivos": ("ficheros", "Archivos"),
    "tamano": ("disco", "Almacenado"),
    "documentos": ("documento", "Documentos"),
    "trozos": ("trozos", "Trozos"),
    "entidades": ("entidades", "Entidades"),
    "relaciones": ("relaciones", "Relaciones"),
}

#: Cómo se agrupan. Son tres preguntas distintas —qué ocupa, qué entendió el
#: motor y qué dibuja el grafo— y en una lista seguida de seis números nadie
#: distingue cuál responde a cuál.
BLOQUES_DE_CIFRAS = (
    ("Almacenamiento", ("archivos", "tamano")),
    ("En memoria", ("documentos", "trozos")),
    ("Grafo", ("entidades", "relaciones")),
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
        """Arriba a la derecha del lienzo, sin salirse nunca."""
        padre = self.parentWidget()
        if padre is None:
            return
        alto = min(
            max(self.sizeHint().height(), 120),
            max(padre.height() - 2 * MARGEN_FICHA, 120),
        )
        self.setFixedHeight(alto)
        self.move(padre.width() - ANCHO_FICHA - MARGEN_FICHA, MARGEN_FICHA)


class Cifra(QWidget):
    """Un icono, un número grande y su rótulo."""

    def __init__(self, icono_nombre: str, rotulo: str) -> None:
        super().__init__()
        self.setObjectName("fila")

        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)

        marca = QLabel()
        marca.setPixmap(iconos.pixmap(icono_nombre, 20, "#3b82f6"))
        marca.setFixedWidth(22)
        marca.setAlignment(Qt.AlignTop)
        fila.addWidget(marca)

        columna = QVBoxLayout()
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(0)

        self.valor = QLabel("…")
        self.valor.setObjectName("cifra")
        columna.addWidget(self.valor)

        etiqueta = QLabel(rotulo)
        etiqueta.setObjectName("descripcion")
        columna.addWidget(etiqueta)

        fila.addLayout(columna, 1)

    def poner(self, texto: str) -> None:
        self.valor.setText(texto)


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
        else:
            self.rejilla.addWidget(self.columna_grafo, 0, 0)
            self.rejilla.addWidget(self.columna_datos, 0, 1)
            self.rejilla.setColumnStretch(0, 1)
            self.rejilla.setColumnStretch(1, 0)
            self.columna_datos.setFixedWidth(ANCHO_DATOS)

        self.columna_grafo.show()
        self.columna_datos.show()

    def resizeEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        super().resizeEvent(evento)
        self._colocar_columnas(self.width() < ANCHO_MINIMO_DOS_COLUMNAS)

    # -- columna izquierda: el grafo ----------------------------------------

    def _columna_grafo(self) -> QWidget:
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

        self.grafo = Grafo()
        self.grafo.elegido.connect(self._pintar_detalle)
        self.grafo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tarjeta.anadir(self.grafo)

        # La ficha vive **dentro** del lienzo, pegada a su lado derecho: es
        # hija del grafo, no una tarjeta más de la columna. Así se lee sin
        # apartar la vista de la entidad que se acaba de pulsar.
        self.ficha = Ficha(self.grafo)
        self.ficha.cerrada.connect(self._soltar_seleccion)
        self.grafo.installEventFilter(self)

        tarjeta.anadir(self._pie())
        return tarjeta

    def _pie(self) -> QWidget:
        """Leyenda y ayuda, con su propio fondo.

        Sueltas sobre la tarjeta parecían flotar encima del lienzo. Puestas
        en su propia banda, con fondo y un borde arriba, se leen como lo que
        son: el pie del grafo, no parte del dibujo.
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
        self.caja_leyenda = Fluida(separacion=14, salto=4)
        self.leyenda.setLayout(self.caja_leyenda)
        columna.addWidget(self.leyenda)

        ayuda = QLabel(
            "Arrastra para mover el lienzo, rueda para acercar, y pulsa una "
            "entidad para ver su ficha y aislar sus relaciones."
        )
        ayuda.setObjectName("descripcion")
        ayuda.setWordWrap(True)
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

        dentro = QWidget()
        dentro.setObjectName("fila")
        columna = QVBoxLayout(dentro)
        columna.setContentsMargins(0, 0, 8, 0)
        columna.setSpacing(16)

        # Tres bloques y no uno: «lo que ocupa en disco», «lo que el motor
        # entendió» y «lo que dibuja el grafo» son tres cosas distintas, y en
        # una lista seguida de seis números nadie distingue cuál es cuál.
        self.cifras: dict[str, Cifra] = {}
        for titulo, claves in BLOQUES_DE_CIFRAS:
            tarjeta = Tarjeta(titulo)
            for clave in claves:
                icono_nombre, rotulo = CIFRAS[clave]
                pieza = Cifra(icono_nombre, rotulo)
                self.cifras[clave] = pieza
                tarjeta.anadir(pieza)
            columna.addWidget(tarjeta)

        columna.addStretch(1)
        envoltorio.setWidget(dentro)
        return envoltorio

    # -- datos --------------------------------------------------------------

    def refrescar(self) -> None:
        self.motor.get("/bimnemo/stats", self._pintar_cifras, self._fallo)
        self.motor.get("/bimnemo/stats/graph", self._pintar_grafo_cifras, None)
        self._cargar_grafo()

    def _pintar_cifras(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        self.aviso.callar()
        almacen = datos.get("storage") or {}
        memoria = datos.get("memory") or {}

        self.cifras["archivos"].poner(formato.numero(almacen.get("total_files")))
        self.cifras["tamano"].poner(formato.tamano(almacen.get("total_bytes")))
        self.cifras["documentos"].poner(formato.numero(memoria.get("total_documents")))
        self.cifras["trozos"].poner(formato.numero(memoria.get("total_chunks")))

        fallo = memoria.get("documents_error") or memoria.get("failed_reason")
        if fallo:
            self.aviso.fallar(str(fallo))

    def _pintar_grafo_cifras(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        self.cifras["entidades"].poner(formato.numero(datos.get("entities")))
        self.cifras["relaciones"].poner(formato.numero(datos.get("relations")))

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
