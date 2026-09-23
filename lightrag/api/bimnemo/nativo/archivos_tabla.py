"""La tabla de «Almacenados»: sus columnas y cómo se pinta cada fila.

Separada de la pantalla porque son dos trabajos distintos: la pantalla
decide **qué** se enseña —qué memoria, qué filtro, qué se está subiendo— y
esto decide **cómo** se dibuja. Juntos pasaban de las novecientas líneas, y
en un fichero así el ancho de una columna y la lógica de un reintento acaban
viviendo a diez líneas el uno del otro.

Lo que la tabla no sabe hacer se le inyecta: las acciones de cada fila son
funciones que le pasa la pantalla (:class:`Acciones`). Así los botones se
dibujan aquí y lo que hacen sigue estando donde están los avisos y el
refresco, que es lo que tocan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet, Any, Callable, Mapping, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo import formato, iconos, tema
from lightrag.api.bimnemo.nativo.archivos_avance import Barras
from lightrag.api.bimnemo.nativo.archivos_piezas import (
    categoria_de,
    icono_categoria,
)
from lightrag.api.bimnemo.nativo.piezas import insignia

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

#: Alto de cada fila. Manda sobre el relleno de la hoja de estilo: es lo que
#: decide si la barra de avance y los botones caben.
ALTO_FILA = 46


@dataclass(frozen=True)
class Acciones:
    """Lo que puede hacerse con una fila, puesto por la pantalla."""

    pausar: Callable[[], None]
    reintentar: Callable[[str], None]
    renombrar: Callable[[str], None]
    borrar: Callable[[dict[str, Any]], None]
    #: Si el nombre cabe en la ruta de la memoria abierta.
    no_cabe: Callable[[str], bool]


def estado_de(
    archivo: Mapping[str, Any],
    nombre: str,
    subiendo: Mapping[str, int],
    borrandose: AbstractSet[str],
) -> str:
    """El estado que manda en esa fila, en crudo.

    El orden importa: lo que se está subiendo gana —el motor aún no sabe que
    existe— y «borrándose» gana a lo que diga el motor, que es lo último que
    se pidió sobre esa fila y lo único que explica por qué sigue ahí.
    """
    if nombre in subiendo:
        return "subiendo"
    if nombre in borrandose:
        return "deleting"
    if archivo.get("waiting"):
        # Tiene una acción apuntada que espera a que la memoria se libere.
        return "espera"
    if archivo.get("duplicate_of") is not None:
        return "duplicado"
    if archivo.get("paused") and archivo.get("status") == "failed":
        return "pausado"
    return str(archivo.get("status") or "")


def pista_de(archivo: Mapping[str, Any], estado: str) -> str:
    """Por qué un documento falló, o de qué es copia, al pasar el ratón.

    El motivo ya viajaba en cada fila y no se enseñaba en ningún sitio: la
    tabla decía «Fallido» y había que ir a buscar el porqué al Panel.
    """
    if estado in ("failed", "duplicado", "pausado"):
        return str(archivo.get("error_msg") or "")
    return ""


def numero(texto: str) -> QTableWidgetItem:
    """Una celda de cifra, alineada a la derecha para poder compararlas."""
    item = QTableWidgetItem(texto)
    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return item


def envolver(widget: QWidget, derecha: int = 8) -> QWidget:
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


def boton_fila(icono: str, pista: str) -> QPushButton:
    """Un botón de acción de fila: solo icono, como en la web.

    Con rótulo, «Reintentar» y «Borrar» se comen ciento setenta píxeles de
    la columna del nombre, que es la que de verdad hace falta ancha.
    """
    boton = QPushButton()
    boton.setObjectName("icono")
    iconos.poner(boton, icono, 14)
    boton.setToolTip(pista)
    boton.setCursor(Qt.PointingHandCursor)
    boton.setFixedSize(30, 26)
    return boton


class TablaArchivos(QTableWidget):
    """Las ocho columnas de «Almacenados» y el pintado de sus filas."""

    def __init__(self, barras: Barras, acciones: Acciones) -> None:
        super().__init__(0, len(COLUMNAS))
        self.barras = barras
        self.acciones = acciones
        self._catalogo: list[dict[str, Any]] = []
        self._montar()

    # -- estructura ---------------------------------------------------------

    def _montar(self) -> None:
        self.setObjectName("tabla")
        self.setHorizontalHeaderLabels(COLUMNAS)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(ALTO_FILA)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setShowGrid(False)
        # Sin envolver: un nombre largo parte en dos líneas y aprieta la fila
        # hasta que no cabe la barra de avance. Se recorta con puntos
        # suspensivos, y el nombre entero está en el rótulo emergente.
        self.setWordWrap(False)

        cabecera = self.horizontalHeader()
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
            self.setColumnWidth(columna, ancho)
        # La de acciones no: lleva botones de tamaño fijo y estirarla solo
        # deja hueco vacío.
        cabecera.setSectionResizeMode(ACCIONES, QHeaderView.Fixed)
        self.setColumnWidth(ACCIONES, 96)

        # Las dos columnas de números se alinean a la derecha, cabecera
        # incluida: es como se comparan cifras de un vistazo.
        for columna in (TAMANO, FRAGMENTOS):
            item = self.horizontalHeaderItem(columna)
            if item is not None:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    # -- pintado ------------------------------------------------------------

    def pintar(
        self,
        visibles: Sequence[Mapping[str, Any]],
        catalogo: Sequence[Mapping[str, Any]],
        subiendo: Mapping[str, int],
        borrandose: AbstractSet[str],
    ) -> None:
        """Rehace la tabla entera con las filas que toca enseñar."""
        self._catalogo = list(catalogo)
        self.barras.olvidar()
        self.setRowCount(len(visibles))
        for indice, archivo in enumerate(visibles):
            nombre = str(archivo.get("name") or "")
            estado = estado_de(archivo, nombre, subiendo, borrandose)
            self._pintar_fila(indice, dict(archivo), nombre, estado, subiendo)
        self.ajustar_alto(len(visibles))

    def ajustar_alto(self, filas: int) -> None:
        """La tabla ocupa lo que ocupan sus filas, ni más ni menos.

        Con un alto fijo, seis ficheros dejaban media tarjeta en blanco —que
        se lee como «aquí falta algo»— y cincuenta no cabían igual. El tope
        existe para que la tarjeta no crezca sin fin: pasado ese punto, la
        que se desplaza es la tabla.
        """
        alto = self.horizontalHeader().height() + filas * ALTO_FILA + 4
        self.setFixedHeight(max(120, min(alto, 620)))

    def _pintar_fila(
        self,
        indice: int,
        archivo: dict[str, Any],
        nombre: str,
        estado: str,
        subiendo: Mapping[str, int],
    ) -> None:
        categoria = categoria_de(self._catalogo, archivo.get("category"))
        color, fondo = tema.color_categoria(str(categoria.get("color") or "slate"))

        celda = QTableWidgetItem(nombre)
        celda.setIcon(icono_categoria(str(categoria.get("color") or "slate")))
        # El nombre completo al pasar el ratón: la columna lo recorta cuando
        # la ventana es estrecha, y estos nombres se parecen entre sí justo
        # en el final.
        celda.setToolTip(nombre)
        self.setItem(indice, ARCHIVO, celda)

        self.setCellWidget(
            indice,
            CATEGORIA,
            envolver(insignia(str(categoria["label"]), color, fondo)),
        )
        self.setItem(indice, TIPO, QTableWidgetItem(str(archivo.get("type") or "—")))
        self.setItem(
            indice, TAMANO, numero(formato.tamano(archivo.get("size_bytes")))
        )
        self.setCellWidget(
            indice,
            ESTADO,
            self._celda_estado(archivo, nombre, estado, subiendo),
        )

        trozos = archivo.get("chunks_count")
        self.setItem(
            indice,
            FRAGMENTOS,
            numero("—" if trozos is None else formato.numero(trozos)),
        )
        self.setItem(
            indice,
            MODIFICADO,
            QTableWidgetItem(formato.fecha(archivo.get("modified_at"))),
        )
        self.setCellWidget(indice, ACCIONES, self._acciones_de(archivo, estado))

    def _celda_estado(
        self,
        archivo: Mapping[str, Any],
        nombre: str,
        estado: str,
        subiendo: Mapping[str, int],
    ) -> QWidget:
        """La insignia del estado y, si hay trabajo, su barra debajo."""
        caja_exterior = QWidget()
        caja_exterior.setObjectName("fila")
        caja_exterior.setToolTip(pista_de(archivo, estado))
        columna = QVBoxLayout(caja_exterior)
        columna.setContentsMargins(4, 4, 8, 4)
        columna.setSpacing(3)

        if estado == "subiendo":
            # Subir no es un estado del motor: va del azul de «trabajando»,
            # que es lo que está pasando de verdad.
            rotulo = f"Subiendo {subiendo.get(nombre, 0)} %"
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
            columna.addWidget(self.barras.crear(nombre, caja_exterior))
            self.barras.pintar(
                nombre,
                str(archivo.get("doc_id") or ""),
                estado,
                subiendo.get(nombre, 0) if estado == "subiendo" else None,
            )

        return caja_exterior

    def _acciones_de(self, archivo: dict[str, Any], estado: str) -> QWidget:
        caja_exterior = QWidget()
        caja_exterior.setObjectName("fila")
        caja = QHBoxLayout(caja_exterior)
        caja.setContentsMargins(4, 4, 8, 4)
        caja.setSpacing(6)
        caja.addStretch(1)

        doc_id = str(archivo.get("doc_id") or "")
        nombre = str(archivo.get("name") or "")

        if estado in formato.PAUSABLES:
            # LightRAG para la tubería de la memoria entera, no un documento
            # suelto: se dice en el rótulo en vez de fingir lo contrario.
            pausar = boton_fila(
                "pausa",
                "Pausar la indexación de esta memoria. Se reanuda con ⟳ sin "
                "volver a pagar lo ya extraído (con el mismo modelo).",
            )
            pausar.clicked.connect(lambda: self.acciones.pausar())
            caja.addWidget(pausar)

        if estado == "espera":
            # Ya está apuntada: otro botón aquí solo la duplicaría.
            pass
        elif archivo.get("name_too_long") or (
            not archivo.get("status") and self.acciones.no_cabe(nombre)
        ):
            # Se arregla renombrando, no reintentando: fallaría igual.
            renombrar = boton_fila("editar", "Renombrar y volver a leer")
            renombrar.clicked.connect(lambda: self.acciones.renombrar(nombre))
            caja.addWidget(renombrar)
        elif estado in ("failed", "pausado") and doc_id:
            # Solo este documento: el botón está en su fila. Los demás
            # fallidos se quedan como están.
            reintentar = boton_fila(
                "recargar",
                "Reanudar este documento"
                if estado == "pausado"
                else "Reintentar este documento",
            )
            reintentar.clicked.connect(lambda: self.acciones.reintentar(doc_id))
            caja.addWidget(reintentar)

        borrando = estado == "deleting"
        if borrando:
            pista = "Borrándose…"
        elif estado == "duplicado":
            # Reintentar una copia no serviría de nada: se volvería a
            # rechazar. Lo único útil es quitarla, y se dice qué se pierde.
            pista = "Borrar esta copia. El original sigue en la memoria."
        else:
            pista = "Borrar este archivo"
        borrar = boton_fila("borrar", pista)
        borrar.setEnabled(bool(nombre) and not borrando)
        borrar.clicked.connect(lambda: self.acciones.borrar(archivo))
        caja.addWidget(borrar)
        return caja_exterior


__all__ = [
    "ACCIONES",
    "ALTO_FILA",
    "ARCHIVO",
    "Acciones",
    "COLUMNAS",
    "TablaArchivos",
    "boton_fila",
    "envolver",
    "estado_de",
    "numero",
    "pista_de",
]
