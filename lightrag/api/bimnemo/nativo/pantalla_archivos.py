"""Pantalla «Archivos»: subir documentos, ver por dónde van y borrarlos.

Las mismas ocho columnas y los mismos rótulos que la interfaz web, porque son
el mismo producto: un fichero que allí sale como «4.9 MB · En memoria» y aquí
como «5013504 · processed» convierte una aplicación en dos.

## El estado va en su columna, no en una barra aparte

Cada fichero tiene su propio estado —uno subiendo, otro en cola, otro ya en
memoria— y una barra global no puede contar eso. La columna **Estado** de
cada fila es la que cambia, y la barra de avance vive dentro de esa celda: es
donde el usuario ya está mirando cuando se pregunta si aquello sigue vivo.

## Por qué se sondea, y qué se sondea

El motor no empuja nada: hay que preguntarle. Se pregunta por `/bimnemo/
progress`, que es barato y trae un sello (`revision`); **la lista completa
solo se vuelve a pedir cuando ese sello cambia**. Repintar la tabla entera
cada dos segundos le quitaría el ratón de encima a quien está a punto de
pulsar un botón, y pedir el listado en cada latido es recorrer el disco para
enterarse de que no ha pasado nada.
"""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any, Optional
from urllib.parse import quote

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo import formato, iconos, tema
from lightrag.api.bimnemo.nativo.archivos_piezas import (
    Filtros,
    ZonaSoltar,
    categoria_de,
    icono_categoria,
)
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Pantalla, Tarjeta, insignia

#: Las columnas, en el orden de la web.
COLUMNAS = (
    "Archivo",
    "Categoría",
    "Tipo",
    "Tamaño",
    "Estado",
    "Fragmentos",
    "Modificado",
    "Acciones",
)
ARCHIVO, CATEGORIA, TIPO, TAMANO, ESTADO, FRAGMENTOS, MODIFICADO, ACCIONES = range(8)

#: Cada cuánto se mira el avance: mientras hay trabajo, y en reposo.
CADENCIA_ACTIVA = 2000
CADENCIA_REPOSO = 6000

#: Cuánto se espera sin que nadie trabaje antes de decir que algo va mal.
#: Documentos en cola y la tubería parada es normal un instante —acaban de
#: encolarse— y sospechoso a los veinte segundos.
PACIENCIA = 20.0


class PantallaArchivos(Pantalla):
    #: Cuántos ficheros hay en esta memoria. Lo escucha la ventana para el
    #: contador del carril; se emite solo cuando el número cambia, que es
    #: mucho menos que cada repintado.
    cuenta = Signal(int)

    def __init__(self, motor: Motor) -> None:
        super().__init__(
            "Archivos",
            "Sube documentos y míralos entrar en la memoria.",
        )
        self.motor = motor

        #: Lo que se está subiendo ahora, por nombre: el porcentaje manda
        #: sobre el estado que diga el motor, porque el motor todavía no
        #: sabe que ese fichero existe.
        self._subiendo: dict[str, int] = {}
        #: Los que están borrándose. El servidor responde en cuanto lanza el
        #: trabajo, no cuando termina: sin esta marca la fila se quedaría
        #: intacta fingiendo que no pasa nada.
        self._borrandose: set[str] = set()

        self._catalogo: list[dict[str, Any]] = []
        self._extensiones: list[str] = []
        self._memoria = ""
        self._filas: list[dict[str, Any]] = []

        #: Lo último que contestó `/bimnemo/progress`, y desde cuándo está
        #: parado. Las barras de las filas se pintan con esto.
        self._avance: dict[str, Any] = {}
        self._parado_desde: Optional[float] = None
        self._sello: Optional[str] = None
        self._ultima_cuenta: Optional[int] = None
        #: Si el motor ya ha contestado alguna vez. Hasta entonces no hay
        #: «cero archivos»: hay «todavía no se sabe», y son cosas distintas.
        self._recibido = False
        #: Las barras vivas, por nombre de fichero, para poder moverlas sin
        #: repintar la tabla entera.
        self._barras: dict[str, tuple[QProgressBar, QLabel]] = {}

        self.aviso = Aviso()
        self.anadir(self.aviso)
        self.anadir(self._acciones())
        self.anadir(self._zona())
        self.anadir(self._almacenados())
        self.cerrar_con_espacio()

        # Soltar vale en cualquier parte de la pantalla, no solo dentro del
        # recuadro: quien arrastra un fichero apunta a la ventana.
        self.setAcceptDrops(True)

        self._vigilante = QTimer(self)
        self._vigilante.setInterval(CADENCIA_REPOSO)
        self._vigilante.timeout.connect(self._mirar)
        self._vigilante.start()

        self._cargar_catalogo()
        self.refrescar()
        self._mirar()

    # -- estructura ---------------------------------------------------------

    def _acciones(self) -> QWidget:
        """Los dos botones de la cabecera.

        No hay «Actualizar»: el vigilante mira cada dos o seis segundos y
        vuelve a pedir la lista en cuanto el sello del motor cambia. Un botón
        que solo puede adelantar unos segundos lo que va a pasar solo invita
        a pulsarlo cuando algo parece atascado —y ahí no arregla nada.
        """
        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)
        caja.addStretch(1)

        self.boton_reindexar = QPushButton("Reindexar pendientes")
        iconos.poner(self.boton_reindexar, "recargar", 14)
        self.boton_reindexar.setCursor(Qt.PointingHandCursor)
        self.boton_reindexar.setToolTip(
            "Busca en la carpeta de entrada lo que todavía no está en la "
            "memoria y lo encola."
        )
        self.boton_reindexar.clicked.connect(self._reindexar)
        caja.addWidget(self.boton_reindexar)

        subir = QPushButton("Subir archivos")
        subir.setObjectName("principal")
        iconos.poner(subir, "subir", 15, "sobre_azul")
        subir.setCursor(Qt.PointingHandCursor)
        subir.clicked.connect(self._elegir)
        caja.addWidget(subir)
        return fila

    def _zona(self) -> QWidget:
        self.zona = ZonaSoltar()
        self.zona.soltados.connect(self._subir_varios)
        self.zona.pulsada.connect(self._elegir)
        return self.zona

    def _almacenados(self) -> QWidget:
        tarjeta = Tarjeta()

        cabecera = QWidget()
        cabecera.setObjectName("fila")
        caja = QHBoxLayout(cabecera)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)

        titulo = QLabel("Almacenados")
        titulo.setObjectName("subtitulo")
        caja.addWidget(titulo)
        caja.addStretch(1)

        self.pista = QLabel("…")
        self.pista.setObjectName("pista")
        caja.addWidget(self.pista)
        tarjeta.anadir(cabecera)

        self.filtros = Filtros()
        self.filtros.elegida.connect(lambda _clave: self._repintar())
        tarjeta.anadir(self.filtros)

        tarjeta.anadir(self._tabla())

        # El hueco. Una tabla vacía sin explicación se lee como un fallo de
        # carga; esto dice si es que no hay nada o si es el filtro.
        self.vacio = QLabel("")
        self.vacio.setObjectName("descripcion")
        self.vacio.setAlignment(Qt.AlignCenter)
        self.vacio.setWordWrap(True)
        self.vacio.hide()
        tarjeta.anadir(self.vacio)
        return tarjeta

    def _tabla(self) -> QWidget:
        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setObjectName("tabla")
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        # El alto de fila manda sobre el relleno de la hoja de estilo: es lo
        # que decide si la barra de avance y los botones caben.
        self.tabla.verticalHeader().setDefaultSectionSize(46)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setShowGrid(False)
        # Sin envolver: un nombre largo parte en dos líneas y aprieta la fila
        # hasta que no cabe la barra de avance. Se recorta con puntos
        # suspensivos, y el nombre entero está en el rótulo emergente.
        self.tabla.setWordWrap(False)

        cabecera = self.tabla.horizontalHeader()
        # Alineado desde el código y no desde la hoja de estilo: Qt ignora
        # `text-align` en las secciones de cabecera.
        cabecera.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        cabecera.setSectionResizeMode(ARCHIVO, QHeaderView.Stretch)
        cabecera.setMinimumSectionSize(60)
        # Anchos de salida y a mano, no `ResizeToContents`: ese modo mide la
        # cabecera y el relleno de la hoja de estilo, y con ocho columnas
        # inflaba «Modificado» a 239 píxeles para una fecha de 110, dejando
        # el nombre del fichero —lo único que de verdad hay que leer— en 183
        # y con barra de desplazamiento horizontal. Quedan ajustables: en una
        # ventana ancha cada uno estira la que le interesa.
        for columna, ancho in (
            (CATEGORIA, 122),
            (TIPO, 66),
            (TAMANO, 84),
            (ESTADO, 182),
            (FRAGMENTOS, 88),
            (MODIFICADO, 128),
        ):
            cabecera.setSectionResizeMode(columna, QHeaderView.Interactive)
            self.tabla.setColumnWidth(columna, ancho)
        # La de acciones no: lleva botones de tamaño fijo y estirarla solo
        # deja hueco vacío.
        cabecera.setSectionResizeMode(ACCIONES, QHeaderView.Fixed)
        self.tabla.setColumnWidth(ACCIONES, 96)

        # Las dos columnas de números se alinean a la derecha, cabecera
        # incluida: es como se comparan cifras de un vistazo.
        for columna in (TAMANO, FRAGMENTOS):
            item = self.tabla.horizontalHeaderItem(columna)
            if item is not None:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return self.tabla

    # -- datos --------------------------------------------------------------

    def _cargar_catalogo(self) -> None:
        """Qué categorías hay y qué formatos admite el motor ahora mismo."""

        def llego(datos: Any) -> None:
            if not isinstance(datos, dict):
                return
            self._catalogo = list(datos.get("categories") or [])
            self._extensiones = [
                str(e) for e in (datos.get("ingestible_extensions") or [])
            ]
            self.zona.formatos(self._extensiones)
            self._repintar()

        def no_pudo(motivo: str) -> None:
            self.zona.no_se_pudo(
                f"No se pudo preguntar al motor qué formatos admite: {motivo}"
            )

        self.motor.get("/bimnemo/catalog", llego, no_pudo)

    def retematizar(self) -> None:
        """Las insignias de la tabla llevan su color escrito en el widget.

        Los iconos los repasa la ventana; esto es para lo que se pinta con
        un estilo propio por fila, que no lo alcanza ninguna hoja.
        """
        self._repintar()

    def filtrar(self, categoria: str) -> None:
        """Deja la tabla en una categoría. La pulsa alguien en el panel."""
        self.filtros.elegir(categoria)

    def poner_memoria(self, nombre: str) -> None:
        """El nombre de la memoria abierta, para la pista de la cabecera.

        Lo inyecta la ventana en vez de pedirlo aquí: quién está abierta lo
        sabe la barra superior, y dos sitios preguntándolo se contradicen en
        cuanto uno se entera del cambio antes que el otro.
        """
        self._memoria = nombre
        self._repintar()

    def refrescar(self) -> None:
        self.motor.get("/bimnemo/files", self._recibir, self._fallo)

    def _recibir(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        self.aviso.callar()
        self._recibido = True
        self._filas = list(datos.get("files") or [])

        # Un borrado termina con la fila desapareciendo, así que la marca
        # deja de tener a quién describir. Sin esto, subir otro archivo con
        # el mismo nombre lo pintaría «Borrando…» nada más llegar.
        vivos = {str(f.get("name") or "") for f in self._filas}
        self._borrandose &= vivos

        if datos.get("scan_error"):
            self.aviso.fallar(str(datos["scan_error"]))
        self._repintar()

    def _fallo(self, motivo: str) -> None:
        self.aviso.fallar(motivo)

    # -- pintado ------------------------------------------------------------

    def _subiendo_fuera(self) -> list[dict[str, Any]]:
        """Los que se están subiendo y el motor todavía no conoce.

        Se pintan delante de todo y **no se filtran**: su categoría aún no
        se sabe, y esconder un fichero justo mientras sube es lo contrario
        de lo que hace falta.
        """
        return [
            {"name": nombre, "type": "", "size_bytes": None, "status": ""}
            for nombre in self._subiendo
            if not any(f.get("name") == nombre for f in self._filas)
        ]

    def _filas_visibles(self) -> list[dict[str, Any]]:
        activa = self.filtros.activa
        del_motor = (
            self._filas
            if not activa
            else [f for f in self._filas if f.get("category") == activa]
        )
        return self._subiendo_fuera() + del_motor

    def _repintar(self) -> None:
        self.filtros.poner(self._filas, self._catalogo)
        visibles = self._filas_visibles()
        total = len(self._filas) + len(self._subiendo_fuera())

        pista = f"{formato.numero(len(visibles))} de {formato.numero(total)}"
        self.pista.setText(f"{self._memoria} · {pista}" if self._memoria else pista)

        if self._recibido and total != self._ultima_cuenta:
            self._ultima_cuenta = total
            self.cuenta.emit(total)

        self._barras.clear()
        self.tabla.setRowCount(len(visibles))
        for indice, archivo in enumerate(visibles):
            self._pintar_fila(indice, archivo)

        self._decir_si_esta_vacio(len(visibles), total)
        self._ajustar_alto(len(visibles))

    def _decir_si_esta_vacio(self, visibles: int, total: int) -> None:
        if visibles:
            self.vacio.hide()
            self.tabla.show()
            return
        self.tabla.hide()
        self.vacio.setText(
            "Nada en esta categoría. Prueba con otro filtro."
            if total
            else "Todavía no hay archivos. Arrastra documentos a la zona de "
            "arriba y entrarán en la memoria."
        )
        self.vacio.show()

    def _ajustar_alto(self, filas: int) -> None:
        """La tabla ocupa lo que ocupan sus filas, ni más ni menos.

        Con un alto fijo, seis ficheros dejaban media tarjeta en blanco —que
        se lee como «aquí falta algo»— y cincuenta no cabían igual. El tope
        existe para que la tarjeta no crezca sin fin: pasado ese punto, la
        que se desplaza es la tabla.
        """
        alto = self.tabla.horizontalHeader().height() + filas * 46 + 4
        self.tabla.setFixedHeight(max(120, min(alto, 620)))

    def _pintar_fila(self, indice: int, archivo: dict[str, Any]) -> None:
        nombre = str(archivo.get("name") or "")
        categoria = categoria_de(self._catalogo, archivo.get("category"))
        color, fondo = tema.color_categoria(str(categoria.get("color") or "slate"))

        celda = QTableWidgetItem(nombre)
        celda.setIcon(icono_categoria(str(categoria.get("color") or "slate")))
        # El nombre completo al pasar el ratón: la columna lo recorta cuando
        # la ventana es estrecha, y estos nombres se parecen entre sí justo
        # en el final.
        celda.setToolTip(nombre)
        self.tabla.setItem(indice, ARCHIVO, celda)

        self.tabla.setCellWidget(
            indice,
            CATEGORIA,
            self._envolver(insignia(str(categoria["label"]), color, fondo)),
        )
        self.tabla.setItem(
            indice, TIPO, QTableWidgetItem(str(archivo.get("type") or "—"))
        )
        self.tabla.setItem(
            indice, TAMANO, self._numero(formato.tamano(archivo.get("size_bytes")))
        )

        estado = self._estado_de(archivo, nombre)
        self.tabla.setCellWidget(indice, ESTADO, self._celda_estado(nombre, estado))

        trozos = archivo.get("chunks_count")
        self.tabla.setItem(
            indice,
            FRAGMENTOS,
            self._numero("—" if trozos is None else formato.numero(trozos)),
        )
        self.tabla.setItem(
            indice,
            MODIFICADO,
            QTableWidgetItem(formato.fecha(archivo.get("modified_at"))),
        )
        self.tabla.setCellWidget(indice, ACCIONES, self._acciones_de(archivo, estado))

    @staticmethod
    def _numero(texto: str) -> QTableWidgetItem:
        item = QTableWidgetItem(texto)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    @staticmethod
    def _envolver(widget: QWidget, derecha: int = 8) -> QWidget:
        """Mete un widget en la celda con margen.

        Pegado al borde de la celda queda tocando la línea de la fila de al
        lado, que es justo lo que hace que una tabla parezca mal dibujada.
        """
        caja_exterior = QWidget()
        caja_exterior.setObjectName("fila")
        caja = QHBoxLayout(caja_exterior)
        caja.setContentsMargins(4, 2, derecha, 2)
        caja.setSpacing(6)
        caja.addWidget(widget)
        caja.addStretch(1)
        return caja_exterior

    def _estado_de(self, archivo: dict[str, Any], nombre: str) -> str:
        """El estado que manda en esa fila, en crudo.

        El orden importa: lo que se está subiendo gana —el motor aún no sabe
        que existe— y «borrándose» gana a lo que diga el motor, que es lo
        último que se pidió sobre esa fila y lo único que explica por qué
        sigue ahí.
        """
        if nombre in self._subiendo:
            return "subiendo"
        if nombre in self._borrandose:
            return "deleting"
        return str(archivo.get("status") or "")

    def _celda_estado(self, nombre: str, estado: str) -> QWidget:
        """La insignia del estado y, si hay trabajo, su barra debajo."""
        caja_exterior = QWidget()
        caja_exterior.setObjectName("fila")
        columna = QVBoxLayout(caja_exterior)
        columna.setContentsMargins(4, 4, 8, 4)
        columna.setSpacing(3)

        if estado == "subiendo":
            # Subir no es un estado del motor: va del azul de «trabajando»,
            # que es lo que está pasando de verdad.
            rotulo = f"Subiendo {self._subiendo.get(nombre, 0)} %"
            color, fondo = tema.color_estado("processing")
        else:
            rotulo = formato.estado(estado)
            color, fondo = tema.color_estado(estado)

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.addWidget(insignia(rotulo, color, fondo, punto=True))
        caja.addStretch(1)
        columna.addWidget(fila)

        if estado == "subiendo" or estado in formato.EN_CURSO:
            barra = QProgressBar()
            barra.setObjectName("avance")
            barra.setTextVisible(False)
            texto = QLabel("")
            texto.setObjectName("avance-texto")

            debajo = QWidget()
            debajo.setObjectName("fila")
            caja2 = QHBoxLayout(debajo)
            caja2.setContentsMargins(0, 0, 0, 0)
            caja2.setSpacing(6)
            caja2.addWidget(barra, 1)
            caja2.addWidget(texto)
            columna.addWidget(debajo)

            self._barras[nombre] = (barra, texto)
            self._poner_avance(nombre, estado)

        return caja_exterior

    def _poner_avance(self, nombre: str, estado: str) -> None:
        """Pone la barra de una fila con lo último que se sabe.

        El motor publica **un** recuento de fragmentos para toda la tubería,
        así que el número se le pone a la fila que de verdad está
        `processing`. Las demás se quedan indeterminadas: enseñarles un
        porcentaje ajeno sería peor que no enseñar ninguno.
        """
        pareja = self._barras.get(nombre)
        if pareja is None:
            return
        barra, texto = pareja

        if estado == "subiendo":
            barra.setRange(0, 100)
            barra.setValue(self._subiendo.get(nombre, 0))
            texto.setText("")
            return

        parado = (
            bool(self._avance.get("stalled"))
            and self._parado_desde is not None
            and monotonic() - self._parado_desde > PACIENCIA
        )
        self._marcar_parada(barra, parado)
        if parado:
            barra.setRange(0, 100)
            barra.setValue(0)
            texto.setText("Sin avanzar")
            texto.setToolTip(
                "El motor lleva un rato sin procesar. Puede que el modelo no "
                "responda o que falte configuración."
            )
            return

        texto.setToolTip("")
        total = int(self._avance.get("chunk_total") or 0)
        hechos = int(self._avance.get("chunk_done") or 0)
        if estado == "processing" and self._avance.get("busy") and total > 0:
            por_ciento = min(100, round(hechos * 100 / total))
            barra.setRange(0, 100)
            barra.setValue(por_ciento)
            texto.setText(f"{por_ciento} % · {hechos}/{total}")
        else:
            # Indeterminada: hay trabajo, pero nadie sabe cuánto queda.
            barra.setRange(0, 0)
            texto.setText("")

    @staticmethod
    def _marcar_parada(barra: QProgressBar, parado: bool) -> None:
        """Pinta la barra de gris, o la devuelve al azul.

        Se pone y se **quita**: la misma barra se reutiliza entre sondeos, y
        una que se quedara marcada seguiría gris después de que el motor
        volviera a moverse.
        """
        if barra.property("parado") == ("si" if parado else ""):
            return
        barra.setProperty("parado", "si" if parado else "")
        barra.style().unpolish(barra)
        barra.style().polish(barra)

    def _acciones_de(self, archivo: dict[str, Any], estado: str) -> QWidget:
        caja_exterior = QWidget()
        caja_exterior.setObjectName("fila")
        caja = QHBoxLayout(caja_exterior)
        caja.setContentsMargins(4, 4, 8, 4)
        caja.setSpacing(6)
        caja.addStretch(1)

        if estado == "failed":
            # El endpoint reencola TODOS los fallidos de la memoria, no este
            # documento suelto. Se dice en el rótulo emergente en vez de
            # fingir que la acción es solo de esta fila.
            reintentar = self._boton_fila(
                "recargar",
                "Vuelve a encolar todos los documentos fallidos de esta memoria.",
            )
            reintentar.clicked.connect(self._reintentar)
            caja.addWidget(reintentar)

        borrando = estado == "deleting"
        borrar = self._boton_fila(
            "borrar", "Borrándose…" if borrando else "Borrar este archivo"
        )
        borrar.setEnabled(bool(archivo.get("name")) and not borrando)
        borrar.clicked.connect(lambda: self._confirmar_borrado(archivo))
        caja.addWidget(borrar)
        return caja_exterior

    @staticmethod
    def _boton_fila(icono: str, pista: str) -> QPushButton:
        """Un botón de acción de fila: solo icono, como en la web.

        Con rótulo, «Reintentar» y «Borrar» se comen ciento setenta píxeles
        de la columna del nombre, que es la que de verdad hace falta ancha.
        """
        boton = QPushButton()
        boton.setObjectName("icono")
        iconos.poner(boton, icono, 14)
        boton.setToolTip(pista)
        boton.setCursor(Qt.PointingHandCursor)
        boton.setFixedSize(30, 26)
        return boton

    # -- vigilancia ---------------------------------------------------------

    def _mirar(self) -> None:
        """Una petición barata que sirve para dos cosas: avance y frescura."""
        self.motor.get("/bimnemo/progress", self._avance_llego, None)

    def _avance_llego(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        self._avance = datos

        activo = bool(datos.get("busy")) or int(datos.get("working") or 0) > 0
        if activo and datos.get("stalled"):
            if self._parado_desde is None:
                self._parado_desde = monotonic()
        else:
            self._parado_desde = None

        self._cadencia(CADENCIA_ACTIVA if activo else CADENCIA_REPOSO)

        sello = str(datos.get("revision") or "")
        cambio = bool(sello) and self._sello is not None and sello != self._sello
        if sello:
            self._sello = sello

        # La lista solo se vuelve a pedir cuando algo cambió de verdad. El
        # primer sondeo únicamente toma la referencia.
        if cambio:
            self.refrescar()
        elif activo:
            self._repintar_barras()

    def _repintar_barras(self) -> None:
        """Mueve las barras que ya están puestas, sin rehacer la tabla."""
        for archivo in self._filas_visibles():
            nombre = str(archivo.get("name") or "")
            if nombre in self._barras:
                self._poner_avance(nombre, self._estado_de(archivo, nombre))

    def _cadencia(self, ms: int) -> None:
        if self._vigilante.interval() != ms:
            self._vigilante.setInterval(ms)

    # -- subir --------------------------------------------------------------

    def _filtro(self) -> str:
        """El filtro del diálogo, con lo que el motor admite de verdad.

        Sin esto se puede elegir un `.exe` que el motor rechazará después:
        el error llega tarde y parece un fallo del programa.
        """
        if not self._extensiones:
            return "Todos los archivos (*.*)"
        patrones = " ".join(f"*.{e}" for e in self._extensiones)
        return f"Documentos admitidos ({patrones});;Todos los archivos (*.*)"

    def _elegir(self) -> None:
        rutas, _filtro = QFileDialog.getOpenFileNames(
            self, "Elige los documentos", "", self._filtro()
        )
        self._subir_varios(rutas)

    def _subir_varios(self, rutas: list[str]) -> None:
        for ruta in rutas:
            if ruta:
                self._subir(ruta)

    def dragEnterEvent(self, evento: QDragEnterEvent) -> None:  # noqa: N802
        if evento.mimeData().hasUrls():
            evento.acceptProposedAction()

    def dropEvent(self, evento: QDropEvent) -> None:  # noqa: N802
        self._subir_varios(
            [u.toLocalFile() for u in evento.mimeData().urls() if u.isLocalFile()]
        )
        evento.acceptProposedAction()

    def _subir(self, ruta: str) -> None:
        nombre = Path(ruta).name
        self._subiendo[nombre] = 0
        self._repintar()

        def avanzar(hecho: int, total: int) -> None:
            if total <= 0:
                return
            self._subiendo[nombre] = int(hecho * 100 / total)
            # Se mueve la barra de esa fila y se deja la tabla en paz: pedir
            # el listado entero en cada trozo enviado es recorrer el disco
            # cincuenta veces por fichero.
            if nombre in self._barras:
                self._poner_avance(nombre, "subiendo")
            else:
                self._repintar()

        def acabo(_datos: Any) -> None:
            self._subiendo.pop(nombre, None)
            # Recién subido, el motor tarda un momento en encolarlo; el
            # vigilante se encarga de enseñarlo cuando aparezca.
            self._cadencia(CADENCIA_ACTIVA)
            self.refrescar()

        def no_pudo(motivo: str) -> None:
            self._subiendo.pop(nombre, None)
            self.aviso.fallar(f"{nombre}: {motivo}")
            self._repintar()

        self.motor.subir("/documents/upload", ruta, acabo, no_pudo, avanzar)

    # -- reindexar y reintentar ---------------------------------------------

    def _reindexar(self) -> None:
        """Encola lo que está en la carpeta pero no en la memoria."""
        self.boton_reindexar.setEnabled(False)
        self.aviso.informar("Buscando documentos sin indexar…")

        def hecho(_datos: Any) -> None:
            self.boton_reindexar.setEnabled(True)
            self.aviso.acertar("Reindexado en marcha.")
            self._cadencia(CADENCIA_ACTIVA)
            self.refrescar()

        def no_pudo(motivo: str) -> None:
            self.boton_reindexar.setEnabled(True)
            self.aviso.fallar(f"No se pudo reindexar: {motivo}")

        self.motor.post("/documents/scan", {}, hecho, no_pudo)

    def _reintentar(self) -> None:
        self.aviso.informar("Reencolando los documentos fallidos…")

        def hecho(datos: Any) -> None:
            mensaje = ""
            if isinstance(datos, dict):
                mensaje = str(datos.get("message") or "")
            self.aviso.acertar(mensaje or "Fallidos reencolados.")
            self._cadencia(CADENCIA_ACTIVA)
            self.refrescar()

        self.motor.post("/bimnemo/documents/retry", {}, hecho, self._fallo)

    # -- borrar -------------------------------------------------------------

    def _confirmar_borrado(self, archivo: dict[str, Any]) -> None:
        nombre = str(archivo.get("name") or "")
        doc_id = archivo.get("doc_id")

        aviso = (
            f"Se borrará «{nombre}» y todo lo que el motor aprendió de él: "
            "sus trozos, sus entidades y sus relaciones."
            if doc_id
            else f"Se borrará el fichero «{nombre}», que todavía no está indexado."
        )
        respuesta = QMessageBox.question(
            self,
            "Borrar archivo",
            aviso + "\n\nEsto no se puede deshacer. ¿Seguir?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if respuesta != QMessageBox.Yes:
            return

        # La fila lo dice desde ya: el servidor contesta cuando lanza el
        # trabajo, no cuando termina, y purgar un documento lleva segundos.
        self._borrandose.add(nombre)
        self.aviso.informar(f"Borrando «{nombre}»…")
        self._repintar()

        def hecho(_datos: Any) -> None:
            self.aviso.acertar(f"Borrado «{nombre}».")
            self._cadencia(CADENCIA_ACTIVA)
            self.refrescar()

        def no_pudo(motivo: str) -> None:
            self._borrandose.discard(nombre)
            self.aviso.fallar(motivo)
            self._repintar()

        if doc_id:
            self.motor.borrar(
                "/bimnemo/documents",
                {"doc_ids": [doc_id], "delete_file": True},
                hecho,
                no_pudo,
            )
        else:
            self.motor.borrar(
                f"/bimnemo/files?name={quote(nombre)}", {}, hecho, no_pudo
            )
