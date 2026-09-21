"""Pantalla «Archivos»: subir documentos, ver por dónde van y borrarlos.

## El estado va en su columna, no en una barra aparte

Cada fichero tiene su propio estado —uno subiendo, otro en cola, otro ya en
memoria— y una barra global no puede contar eso. La columna **Estado** de
cada fila es la que cambia: «Subiendo 40 %», «En cola», «Indexando», «En
memoria», «Falló». Es donde el usuario ya está mirando.

## Por qué se sondea

El motor no empuja nada: hay que preguntarle. Se pregunta **solo mientras
haya algo en marcha**, y se para en cuanto todo está quieto; un sondeo
perpetuo contra un motor ocioso gasta batería para no enterarse de nada.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Pantalla, Tarjeta

#: Cada cuánto se pregunta por el avance mientras hay trabajo.
SONDEO_MS = 1500

#: Cómo se dice en castellano cada estado del motor.
ESTADOS = {
    "processed": "En memoria",
    "processing": "Indexando",
    "pending": "En cola",
    "failed": "Falló",
    "": "Sin indexar",
    None: "Sin indexar",
}

#: Estados que significan «esto todavía se está moviendo».
EN_MARCHA = ("pending", "processing")

COLUMNAS = ("Nombre", "Tipo", "Tamaño", "Estado", "")


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


class PantallaArchivos(Pantalla):
    def __init__(self, motor: Motor) -> None:
        super().__init__(
            "Archivos",
            "Arrastra documentos aquí o pulsa «Añadir». BIMNEMO los lee, los "
            "trocea y los guarda en su memoria.",
        )
        self.motor = motor
        #: Lo que se está subiendo ahora, por nombre: el porcentaje manda
        #: sobre el estado que diga el motor, porque el motor todavía no
        #: sabe que ese fichero existe.
        self._subiendo: dict[str, int] = {}

        self.aviso = Aviso()
        self.anadir(self.aviso)
        self.anadir(self._barra_de_acciones())
        self.anadir(self._tabla())
        self.cerrar_con_espacio()

        self.setAcceptDrops(True)

        self._reloj = QTimer(self)
        self._reloj.setInterval(SONDEO_MS)
        self._reloj.timeout.connect(self.refrescar)

        self.refrescar()

    # -- estructura ---------------------------------------------------------

    def _barra_de_acciones(self) -> QWidget:
        tarjeta = Tarjeta()
        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)

        self.resumen = QLabel("…")
        self.resumen.setObjectName("descripcion")
        caja.addWidget(self.resumen)
        caja.addStretch(1)

        refrescar = QPushButton("Actualizar")
        refrescar.setCursor(Qt.PointingHandCursor)
        refrescar.clicked.connect(self.refrescar)
        caja.addWidget(refrescar)

        anadir = QPushButton("Añadir archivos")
        anadir.setObjectName("principal")
        anadir.setCursor(Qt.PointingHandCursor)
        anadir.clicked.connect(self._elegir)
        caja.addWidget(anadir)

        tarjeta.anadir(fila)
        return tarjeta

    def _tabla(self) -> QWidget:
        tarjeta = Tarjeta()

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setObjectName("tabla")
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        # El alto de fila manda sobre el relleno de la hoja de estilo:
        # es lo que decide si el botón de la última columna cabe.
        self.tabla.verticalHeader().setDefaultSectionSize(40)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setShowGrid(False)
        self.tabla.setMinimumHeight(420)

        cabecera = self.tabla.horizontalHeader()
        # Alineado desde el código y no desde la hoja de estilo: Qt ignora
        # `text-align` en las secciones de cabecera, y el nombre salía
        # centrado mientras su columna estaba alineada a la izquierda.
        cabecera.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        cabecera.setSectionResizeMode(0, QHeaderView.Stretch)
        for columna in (1, 2, 3):
            cabecera.setSectionResizeMode(columna, QHeaderView.ResizeToContents)
        # La última lleva un botón, no texto. `ResizeToContents` mide la
        # celda —que está vacía— y lo aplastaba hasta dejarlo sin rótulo.
        cabecera.setSectionResizeMode(4, QHeaderView.Fixed)
        self.tabla.setColumnWidth(4, 104)

        tarjeta.anadir(self.tabla)
        return tarjeta

    # -- datos --------------------------------------------------------------

    def refrescar(self) -> None:
        self.motor.get("/bimnemo/files", self._pintar, self._fallo)

    def _pintar(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        archivos = datos.get("files") or []
        self.aviso.callar()

        # Los que se están subiendo todavía no están en la lista del motor:
        # se ponen delante para que el usuario vea que pasa algo.
        pendientes = [
            {"name": nombre, "type": "", "size_bytes": None, "status": "subiendo"}
            for nombre in self._subiendo
            if not any(a.get("name") == nombre for a in archivos)
        ]
        filas = pendientes + list(archivos)

        self.tabla.setRowCount(len(filas))
        trabajando = False

        for indice, archivo in enumerate(filas):
            nombre = str(archivo.get("name") or "")
            self.tabla.setItem(indice, 0, QTableWidgetItem(nombre))
            self.tabla.setItem(
                indice, 1, QTableWidgetItem(str(archivo.get("type") or "—"))
            )
            self.tabla.setItem(
                indice, 2, QTableWidgetItem(_tamano(archivo.get("size_bytes")))
            )

            estado, activo = self._estado_de(archivo, nombre)
            celda = QTableWidgetItem(estado)
            fallo = archivo.get("error_msg")
            if fallo:
                # El motivo, al pasar el ratón: cabe entero y no rompe la
                # columna, que es lo que pasaría poniéndolo en la celda.
                celda.setToolTip(str(fallo))
            self.tabla.setItem(indice, 3, celda)
            trabajando = trabajando or activo

            self.tabla.setCellWidget(indice, 4, self._boton_borrar(archivo))

        total = datos.get("total", len(archivos))
        self.resumen.setText(
            f"{total} archivo{'s' if total != 1 else ''} en esta memoria"
        )

        if datos.get("scan_error"):
            self.aviso.fallar(str(datos["scan_error"]))

        # Se sondea solo mientras haya movimiento.
        if trabajando and not self._reloj.isActive():
            self._reloj.start()
        elif not trabajando and self._reloj.isActive():
            self._reloj.stop()

    def _estado_de(self, archivo: dict[str, Any], nombre: str) -> tuple[str, bool]:
        if nombre in self._subiendo:
            return f"Subiendo {self._subiendo[nombre]} %", True

        bruto = archivo.get("status")
        texto = ESTADOS.get(bruto, str(bruto))
        if bruto == "processing":
            trozos = archivo.get("chunks_count")
            if trozos:
                texto = f"Indexando · {trozos} trozos"
        return texto, bruto in EN_MARCHA

    def _fallo(self, motivo: str) -> None:
        self.aviso.fallar(motivo)
        self._reloj.stop()

    # -- subir --------------------------------------------------------------

    def _elegir(self) -> None:
        rutas, _filtro = QFileDialog.getOpenFileNames(
            self, "Elige los documentos", "", "Todos los archivos (*.*)"
        )
        for ruta in rutas:
            self._subir(ruta)

    def dragEnterEvent(self, evento: QDragEnterEvent) -> None:
        if evento.mimeData().hasUrls():
            evento.acceptProposedAction()

    def dropEvent(self, evento: QDropEvent) -> None:
        for url in evento.mimeData().urls():
            if url.isLocalFile():
                self._subir(url.toLocalFile())
        evento.acceptProposedAction()

    def _subir(self, ruta: str) -> None:
        from pathlib import Path

        nombre = Path(ruta).name
        self._subiendo[nombre] = 0
        self.refrescar()

        def avanzar(hecho: int, total: int) -> None:
            if total > 0:
                self._subiendo[nombre] = int(hecho * 100 / total)
                self.refrescar()

        def acabo(_datos: Any) -> None:
            self._subiendo.pop(nombre, None)
            # Recién subido, el motor tarda un momento en encolarlo; el
            # sondeo se encarga de enseñarlo cuando aparezca.
            if not self._reloj.isActive():
                self._reloj.start()
            self.refrescar()

        def no_pudo(motivo: str) -> None:
            self._subiendo.pop(nombre, None)
            self.aviso.fallar(f"{nombre}: {motivo}")
            self.refrescar()

        self.motor.subir("/documents/upload", ruta, acabo, no_pudo, avanzar)

    # -- borrar -------------------------------------------------------------

    def _boton_borrar(self, archivo: dict[str, Any]) -> QWidget:
        boton = QPushButton("Borrar")
        boton.setObjectName("borrar-fila")
        boton.setCursor(Qt.PointingHandCursor)
        boton.setFixedHeight(26)
        boton.setEnabled(bool(archivo.get("name")))
        boton.clicked.connect(lambda: self._confirmar_borrado(archivo))

        # El botón va dentro de una caja con margen: pegado al borde de la
        # celda queda tocando la línea de la fila de al lado.
        envoltorio = QWidget()
        envoltorio.setObjectName("fila")
        caja = QHBoxLayout(envoltorio)
        caja.setContentsMargins(4, 4, 8, 4)
        caja.addWidget(boton)
        return envoltorio

    def _confirmar_borrado(self, archivo: dict[str, Any]) -> None:
        nombre = str(archivo.get("name") or "")
        doc_id = archivo.get("doc_id")

        aviso = (
            f"Se borrará «{nombre}» y todo lo que el motor aprendió de él: "
            "sus trozos, sus entidades y sus relaciones."
            if doc_id
            else f"Se borrará el fichero «{nombre}», que todavía no está "
            "indexado."
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

        self.aviso.informar(f"Borrando «{nombre}»…")

        def hecho(_datos: Any) -> None:
            self.aviso.acertar(f"Borrado «{nombre}».")
            # El borrado de un documento indexado va en segundo plano, así
            # que se sigue sondeando hasta que desaparezca de la lista.
            if not self._reloj.isActive():
                self._reloj.start()
            self.refrescar()

        if doc_id:
            self.motor.borrar(
                "/bimnemo/documents",
                {"doc_ids": [doc_id], "delete_file": True},
                hecho,
                self._fallo,
            )
        else:
            from urllib.parse import quote

            self.motor.borrar(
                f"/bimnemo/files?name={quote(nombre)}", {}, hecho, self._fallo
            )
