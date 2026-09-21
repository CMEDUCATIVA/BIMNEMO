"""Pantalla «Motor»: qué está usando BIMNEMO por dentro, y reiniciarlo.

Todo sale de `GET /bimnemo/engine`, que es el mismo sitio del que lo saca la
interfaz web. No hay ningún dato calculado aquí: si el motor cambia lo que
publica, esta pantalla cambia con él.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Pantalla, Tarjeta
from lightrag.api.bimnemo.nativo.reinicio import Reinicio, conectar_barra

#: Qué se enseña de cada bloque que devuelve `/bimnemo/engine`, y con qué
#: nombre. En una tabla y no repartido por el código: añadir un dato nuevo
#: es una línea aquí.
BLOQUES = (
    (
        "Producto",
        "product",
        (
            ("name", "Nombre"),
            ("version", "Versión"),
            ("engine", "Motor"),
            ("engine_version", "Versión del motor"),
            ("build", "Compilación"),
        ),
    ),
    (
        "Modelo de lenguaje",
        "llm",
        (
            ("binding", "Proveedor"),
            ("model", "Modelo"),
            ("host", "Dirección"),
            ("api_key_set", "Clave configurada"),
            ("max_async", "Peticiones en paralelo"),
            ("cache_enabled", "Caché de respuestas"),
        ),
    ),
    (
        "Embeddings",
        "embedding",
        (
            ("binding", "Proveedor"),
            ("model", "Modelo"),
            ("host", "Dirección"),
            ("api_key_set", "Clave configurada"),
            ("dim", "Dimensiones"),
            ("batch_num", "Tamaño de lote"),
        ),
    ),
    (
        "Troceado de documentos",
        "chunking",
        (
            ("chunk_token_size", "Tamaño del trozo"),
            ("overlap_token_size", "Solape"),
            ("chunker", "Troceador"),
            ("max_parallel_insert", "Documentos en paralelo"),
        ),
    ),
    (
        "Búsqueda",
        "query_defaults",
        (
            ("top_k", "Resultados por consulta"),
            ("cosine_threshold", "Umbral de similitud"),
            ("rerank_enabled", "Reordenado"),
        ),
    ),
    (
        "Almacenes",
        "storages",
        (
            ("kv", "Clave-valor"),
            ("vector", "Vectores"),
            ("graph", "Grafo"),
            ("doc_status", "Estado de documentos"),
        ),
    ),
)


def _legible(valor: Any) -> str:
    """Un valor del motor, en castellano.

    `True` no es una respuesta: quien lee esta pantalla quiere saber si la
    clave está puesta, no el literal de un booleano de Python.
    """
    if valor is None or valor == "":
        return "—"
    if valor is True:
        return "Sí"
    if valor is False:
        return "No"
    return str(valor)


class PantallaMotor(Pantalla):
    def __init__(self, motor: Motor) -> None:
        super().__init__(
            "Motor",
            "Lo que BIMNEMO está usando ahora mismo. Se lee del motor, no "
            "del fichero de configuración: es lo que de verdad está en "
            "marcha.",
        )
        self.motor = motor
        self._valores: dict[str, QLabel] = {}

        self.aviso = Aviso()
        self.anadir(self.aviso)

        for titulo, bloque, campos in BLOQUES:
            tarjeta = Tarjeta(titulo)
            for clave, nombre in campos:
                self._valores[f"{bloque}.{clave}"] = tarjeta.dato(nombre, "…")
            self.anadir(tarjeta)

        self.anadir(self._carpetas())
        self.anadir(self._zona_de_reinicio())
        self.cerrar_con_espacio()

        self.refrescar()

    # -- datos --------------------------------------------------------------

    def _carpetas(self) -> QWidget:
        tarjeta = Tarjeta("Dónde guarda las cosas")
        self._valores["working_dir"] = tarjeta.dato("Memorias", "…")
        self._valores["input_dir"] = tarjeta.dato("Documentos", "…")
        return tarjeta

    def refrescar(self) -> None:
        self.motor.get("/bimnemo/engine", self._pintar, self._fallo)

    def _pintar(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        self.aviso.callar()

        for _titulo, bloque, campos in BLOQUES:
            seccion = datos.get(bloque) or {}
            for clave, _nombre in campos:
                etiqueta = self._valores.get(f"{bloque}.{clave}")
                if etiqueta is not None:
                    etiqueta.setText(_legible(seccion.get(clave)))

        for clave in ("working_dir", "input_dir"):
            etiqueta = self._valores.get(clave)
            if etiqueta is not None:
                etiqueta.setText(_legible(datos.get(clave)))

    def _fallo(self, motivo: str) -> None:
        self.aviso.fallar(motivo)

    # -- reinicio -----------------------------------------------------------

    def _zona_de_reinicio(self) -> QWidget:
        tarjeta = Tarjeta("Reiniciar")

        explicacion = QLabel(
            "Reiniciar aplica los cambios de configuración. Tarda unos cuatro "
            "segundos y la ventana se queda aquí: no hay que volver a abrir "
            "nada.\n\n"
            "Si BIMNEMO está indexando, el motor se niega a reiniciarse — "
            "cortar a mitad dejaría documentos a medias."
        )
        explicacion.setObjectName("descripcion")
        explicacion.setWordWrap(True)
        tarjeta.anadir(explicacion)

        self.barra = QProgressBar()
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(6)
        self.barra.hide()
        tarjeta.anadir(self.barra)

        self.estado_reinicio = Aviso()
        tarjeta.anadir(self.estado_reinicio)

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.addStretch(1)

        self.boton = QPushButton("Reiniciar motor LightRAG")
        self.boton.setObjectName("peligro")
        self.boton.setCursor(Qt.PointingHandCursor)
        self.boton.clicked.connect(self._reiniciar)
        caja.addWidget(self.boton)

        tarjeta.anadir(fila)
        return tarjeta

    def _reiniciar(self) -> None:
        self.boton.setEnabled(False)
        self.barra.setValue(0)
        self.barra.show()

        self._trabajo = Reinicio(self.motor, self)
        conectar_barra(
            self._trabajo,
            self.estado_reinicio.informar,
            lambda hecho, tope: (
                self.barra.setMaximum(tope),
                self.barra.setValue(hecho),
            ),
        )
        self._trabajo.terminado.connect(self._acabado)
        self._trabajo.arrancar()

    def _acabado(self, bien: bool, motivo: str) -> None:
        self.barra.hide()
        self.boton.setEnabled(True)
        if bien:
            self.estado_reinicio.acertar("El motor ha vuelto.")
            self.refrescar()
        else:
            self.estado_reinicio.fallar(motivo)
