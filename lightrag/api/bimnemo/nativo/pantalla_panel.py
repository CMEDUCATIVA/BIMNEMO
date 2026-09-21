"""Pantalla «Panel»: las cifras de la memoria y su grafo de conocimiento.

Las cifras salen de `GET /bimnemo/stats` y `GET /bimnemo/stats/graph`; el
grafo, de `GET /bimnemo/graph`. El dibujo y la física están en `grafo.py`,
que no sabe de endpoints: aquí se piden los datos y allí se pintan.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo.grafo import Grafo
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Pantalla, Tarjeta

#: Cuántos nodos se piden. Más allá, el grafo deja de leerse y empieza a
#: pesar: 250 ya es una maraña para un ojo humano.
TOPES = (60, 120, 250, 500)
TOPE_POR_DEFECTO = 250


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
    """Un número grande con su rótulo debajo."""

    def __init__(self, rotulo: str) -> None:
        super().__init__()
        self.setObjectName("fila")
        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(2)

        self.valor = QLabel("…")
        self.valor.setObjectName("cifra")
        columna.addWidget(self.valor)

        etiqueta = QLabel(rotulo)
        etiqueta.setObjectName("descripcion")
        columna.addWidget(etiqueta)

    def poner(self, texto: str) -> None:
        self.valor.setText(texto)


class PantallaPanel(Pantalla):
    def __init__(self, motor: Motor) -> None:
        super().__init__(
            "Panel",
            "Qué hay en esta memoria y cómo se relaciona. Arrastra para "
            "mover, rueda para acercar, y pulsa una entidad para verla.",
        )
        self.motor = motor

        self.aviso = Aviso()
        self.anadir(self.aviso)
        self.anadir(self._cifras())
        self.anadir(self._zona_grafo())
        self.anadir(self._detalle())
        # Sin espacio al final: aquí lo que sobra se lo queda el grafo,
        # que es lo que se ha venido a mirar.

        self.refrescar()

    # -- estructura ---------------------------------------------------------

    def _cifras(self) -> QWidget:
        tarjeta = Tarjeta()
        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(28)

        self.cifras = {
            "archivos": Cifra("Archivos"),
            "tamano": Cifra("Almacenado"),
            "documentos": Cifra("Documentos en memoria"),
            "trozos": Cifra("Trozos"),
            "entidades": Cifra("Entidades"),
            "relaciones": Cifra("Relaciones"),
        }
        for pieza in self.cifras.values():
            caja.addWidget(pieza)
        caja.addStretch(1)

        tarjeta.anadir(fila)
        return tarjeta

    def _zona_grafo(self) -> QWidget:
        tarjeta = Tarjeta("Grafo de conocimiento")

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)

        self.resumen_grafo = QLabel("…")
        self.resumen_grafo.setObjectName("descripcion")
        caja.addWidget(self.resumen_grafo)
        caja.addStretch(1)

        caja.addWidget(QLabel("Nodos"))
        self.tope = QComboBox()
        for n in TOPES:
            self.tope.addItem(str(n), n)
        self.tope.setCurrentIndex(TOPES.index(TOPE_POR_DEFECTO))
        self.tope.currentIndexChanged.connect(self._cargar_grafo)
        caja.addWidget(self.tope)

        encuadrar = QPushButton("Encuadrar")
        encuadrar.setCursor(Qt.PointingHandCursor)
        encuadrar.clicked.connect(lambda: self.grafo.encuadrar())
        caja.addWidget(encuadrar)

        actualizar = QPushButton("Actualizar")
        actualizar.setCursor(Qt.PointingHandCursor)
        actualizar.clicked.connect(self.refrescar)
        caja.addWidget(actualizar)

        tarjeta.anadir(fila)

        self.grafo = Grafo()
        self.grafo.elegido.connect(self._pintar_detalle)
        tarjeta.anadir(self.grafo)
        return tarjeta

    def _detalle(self) -> QWidget:
        self.tarjeta_detalle = Tarjeta("Entidad")
        self.detalle_nombre = self.tarjeta_detalle.dato("Nombre", "—")
        self.detalle_tipo = self.tarjeta_detalle.dato("Tipo", "—")
        self.detalle_grado = self.tarjeta_detalle.dato("Relaciones", "—")
        self.detalle_origen = self.tarjeta_detalle.dato("De qué documento", "—")
        self.detalle_texto = self.tarjeta_detalle.dato("Descripción", "—")
        # Empieza escondida: una tarjeta con cinco guiones no informa de nada
        # y quita sitio al grafo, que es lo que se ha venido a ver.
        self.tarjeta_detalle.hide()
        return self.tarjeta_detalle

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
        tope = self.tope.currentData() or TOPE_POR_DEFECTO
        self.resumen_grafo.setText("Cargando el grafo…")
        self.motor.get(
            f"/bimnemo/graph?label=*&max_depth=3&max_nodes={tope}",
            self._pintar_grafo,
            self._fallo,
        )

    def _pintar_grafo(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        nodos = datos.get("nodes") or []
        aristas = datos.get("edges") or []
        self.grafo.poner(nodos, aristas)
        self.grafo.encuadrar()

        texto = f"{len(nodos)} entidades y {len(aristas)} relaciones a la vista"
        if datos.get("truncated"):
            # Decirlo importa: sin esto, quien mira cree que su memoria
            # entera es lo que ve, y no lo es.
            texto += " · hay más de las que caben"
        self.resumen_grafo.setText(texto)

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
