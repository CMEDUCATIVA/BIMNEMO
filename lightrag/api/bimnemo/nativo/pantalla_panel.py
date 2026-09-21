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
from lightrag.api.bimnemo.nativo.grafo import Grafo
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Fluida, Tarjeta

#: Por debajo de esto, las dos columnas se apilan.
ANCHO_MINIMO_DOS_COLUMNAS = 1120

#: Proporción de la columna del grafo frente a la de datos.
PESO_GRAFO = 5
PESO_DATOS = 3

PROFUNDIDADES = ((1, "1 salto"), (2, "2 saltos"), (3, "3 saltos"),
                 (4, "4 saltos"), (5, "5 saltos"))
TOPES = (100, 250, 500, 1000)
TOPE_POR_DEFECTO = 250

#: Las cifras del panel: clave del dato, icono e rótulo.
CIFRAS = (
    ("archivos", "ficheros", "Archivos"),
    ("tamano", "disco", "Almacenado"),
    ("documentos", "documento", "Documentos"),
    ("trozos", "trozos", "Trozos"),
    ("entidades", "entidades", "Entidades"),
    ("relaciones", "relaciones", "Relaciones"),
)


def _numero(valor: Any) -> str:
    try:
        return f"{int(valor):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _tamano(octetos: Any) -> str:
    try:
        n = float(octetos)
    except (TypeError, ValueError):
        return "—"
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidad == "GB":
            return f"{n:.0f} {unidad}" if unidad == "B" else f"{n:.1f} {unidad}"
        n /= 1024
    return "—"


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
        else:
            self.rejilla.addWidget(self.columna_grafo, 0, 0)
            self.rejilla.addWidget(self.columna_datos, 0, 1)
            self.rejilla.setColumnStretch(0, PESO_GRAFO)
            self.rejilla.setColumnStretch(1, PESO_DATOS)

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

        self.leyenda = QWidget()
        self.leyenda.setObjectName("fila")
        # Envuelve: con nueve tipos y la ventana estrecha, una fila sola les
        # recorta el nombre y deja «conce 79» en vez de «concepto 79».
        self.caja_leyenda = Fluida(separacion=14, salto=4)
        self.leyenda.setLayout(self.caja_leyenda)
        tarjeta.anadir(self.leyenda)

        ayuda = QLabel(
            "Arrastra para mover el lienzo, rueda para acercar, y pulsa una "
            "entidad para ver su ficha y aislar sus relaciones."
        )
        ayuda.setObjectName("descripcion")
        ayuda.setWordWrap(True)
        tarjeta.anadir(ayuda)
        return tarjeta

    def _barra(self) -> QWidget:
        barra = QWidget()
        barra.setObjectName("fila")
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(0, 2, 0, 2)
        fila.setSpacing(10)

        self.entidad = QComboBox()
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
        fila.addWidget(_campo(" ", acciones))
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

        tarjeta = Tarjeta("Esta memoria")
        self.cifras: dict[str, Cifra] = {}
        for clave, icono_nombre, rotulo in CIFRAS:
            pieza = Cifra(icono_nombre, rotulo)
            self.cifras[clave] = pieza
            tarjeta.anadir(pieza)
        columna.addWidget(tarjeta)

        self.tarjeta_detalle = Tarjeta("Entidad")
        self.detalle_nombre = self.tarjeta_detalle.dato("Nombre", "—")
        self.detalle_tipo = self.tarjeta_detalle.dato("Tipo", "—")
        self.detalle_grado = self.tarjeta_detalle.dato("Relaciones", "—")
        self.detalle_origen = self.tarjeta_detalle.dato("Documento", "—")
        self.detalle_texto = self.tarjeta_detalle.dato("Descripción", "—")
        # Escondida hasta que se pulse algo: cinco guiones no informan de nada.
        self.tarjeta_detalle.hide()
        columna.addWidget(self.tarjeta_detalle)

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

        self.cifras["archivos"].poner(_numero(almacen.get("total_files")))
        self.cifras["tamano"].poner(_tamano(almacen.get("total_bytes")))
        self.cifras["documentos"].poner(_numero(memoria.get("total_documents")))
        self.cifras["trozos"].poner(_numero(memoria.get("total_chunks")))

        fallo = memoria.get("documents_error") or memoria.get("failed_reason")
        if fallo:
            self.aviso.fallar(str(fallo))

    def _pintar_grafo_cifras(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        self.cifras["entidades"].poner(_numero(datos.get("entities")))
        self.cifras["relaciones"].poner(_numero(datos.get("relations")))

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
            self.tarjeta_detalle.hide()
            return
        self.detalle_nombre.setText(str(nodo.get("label") or nodo.get("id") or "—"))
        self.detalle_tipo.setText(str(nodo.get("type") or "—"))
        self.detalle_grado.setText(_numero(nodo.get("degree")))
        self.detalle_origen.setText(str(nodo.get("file_path") or "—"))
        self.detalle_texto.setText(str(nodo.get("description") or "—"))
        self.tarjeta_detalle.show()

    def _fallo(self, motivo: str) -> None:
        self.aviso.fallar(motivo)
        self.resumen_grafo.setText("No se pudo cargar el grafo.")
