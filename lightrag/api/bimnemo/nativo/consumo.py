"""Tarjeta «Uso y coste de la IA»: lo que se gasta, por día y modelo.

Va en Archivos, debajo de la zona de arrastre, porque es ahí donde se decide
gastar: subir un documento es lo que dispara la indexación, que es lo caro.

Los datos salen de ``GET /bimnemo/usage``, que reúne el ``usage`` real que
devuelve cada proveedor (``bimnemo/consumo.py``). La tarjeta no calcula nada:
pinta.

## Cuándo pregunta

Cada 3 s con la pantalla a la vista y nada más: una tarjeta que nadie mira no
necesita estar al día, ya se pondrá al volver. La respuesta trae un
``revision`` que cambia con cada llamada contada; si no cambió, no se repinta
la tabla.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Tarjeta

SONDEO_MS = 3_000

COLUMNAS = (
    "Fecha",
    "Tipo",
    "Tarea",
    "Modelo",
    "Llamadas",
    "Tokens entrada",
    "Tokens salida",
    "Coste (USD)",
)
FECHA, TIPO, TAREA, MODELO, LLAMADAS, ENTRADA, SALIDA, COSTE = range(len(COLUMNAS))
NUMERICAS = (LLAMADAS, ENTRADA, SALIDA, COSTE)

TIPOS = {"llm": "Lenguaje", "embedding": "Embeddings"}

#: Filas que se ven sin desplazar. Con más, la tabla se desplaza por dentro
#: en vez de empujar la lista de archivos hacia abajo.
FILAS_VISIBLES = 8
ALTO_FILA = 34


def miles(n: int) -> str:
    """1234567 → «1.234.567», como se escribe en español."""
    return f"{int(n):,}".replace(",", ".")


def dinero(usd: float) -> str:
    """Con cuatro decimales por debajo de un dólar: ahí están los céntimos."""
    decimales = 4 if abs(usd) < 1 else 2
    texto = f"{usd:,.{decimales}f}"
    # Separadores españoles: punto para miles, coma para decimales.
    return "$" + texto.replace(",", "·").replace(".", ",").replace("·", ".")


def coste_de(fila: dict[str, Any]) -> str:
    coste = float(fila.get("coste") or 0)
    if fila.get("sin_precio"):
        return f"{dinero(coste)} + ?" if coste else "sin precio"
    return dinero(coste)


class TarjetaConsumo(Tarjeta):
    def __init__(self, motor: Motor) -> None:
        super().__init__("Uso y coste de la IA")
        self.motor = motor
        self._revision: Optional[int] = None

        self.totales = QLabel("…")
        self.totales.setObjectName("dato-valor")
        self.totales.setTextFormat(Qt.RichText)
        self.anadir(self.totales)

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setObjectName("tabla")
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(ALTO_FILA)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabla.setShowGrid(False)
        self.tabla.setWordWrap(False)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # Anchos a mano, como en «Almacenados»: `ResizeToContents` mide también
        # el relleno de la hoja de estilo e infla cada columna hasta sacar una
        # barra horizontal. Solo el modelo se estira.
        cabecera.setMinimumSectionSize(60)
        for columna, ancho in (
            (FECHA, 96),
            (TIPO, 96),
            (TAREA, 116),
            (LLAMADAS, 80),
            (ENTRADA, 116),
            (SALIDA, 108),
            (COSTE, 104),
        ):
            cabecera.setSectionResizeMode(columna, QHeaderView.Interactive)
            self.tabla.setColumnWidth(columna, ancho)
        cabecera.setSectionResizeMode(MODELO, QHeaderView.Stretch)
        for columna in NUMERICAS:
            item = self.tabla.horizontalHeaderItem(columna)
            if item is not None:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.anadir(self.tabla)

        self.vacio = QLabel(
            "Todavía no se ha gastado nada. En cuanto indexes un documento o "
            "hagas una pregunta, aparecerá aquí."
        )
        self.vacio.setObjectName("descripcion")
        self.vacio.setWordWrap(True)
        self.vacio.hide()
        self.anadir(self.vacio)

        pie = QWidget()
        pie.setObjectName("fila")
        caja = QHBoxLayout(pie)
        caja.setContentsMargins(0, 0, 0, 0)
        self.pista = QLabel("")
        self.pista.setObjectName("pista")
        self.pista.setWordWrap(True)
        caja.addWidget(self.pista, 1)
        self.anadir(pie)

        self._reloj = QTimer(self)
        self._reloj.setInterval(SONDEO_MS)
        self._reloj.timeout.connect(self._sondear)
        self._reloj.start()
        self.mirar()

    # -- datos --------------------------------------------------------------

    def _sondear(self) -> None:
        if self.isVisible():
            self.mirar()

    def showEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        super().showEvent(evento)
        self.mirar()

    def mirar(self) -> None:
        self.motor.get("/bimnemo/usage?days=30", self.pintar, None)

    def pintar(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        revision = datos.get("revision")
        if revision is not None and revision == self._revision:
            return
        self._revision = revision

        self._pintar_totales(datos.get("totals") or {})
        self._pintar_filas(list(datos.get("rows") or []))
        self.pista.setText(
            "Medido con lo que devuelve cada proveedor en cada llamada. Es un "
            "techo: no descuenta la entrada que el proveedor cobra más barata "
            "por tenerla en caché. Precios comprobados el "
            f"{datos.get('prices_checked') or '?'}; los locales cuentan 0."
        )

    def _pintar_totales(self, totales: dict[str, Any]) -> None:
        partes = []
        for clave, nombre in (
            ("today", "Hoy"),
            ("week", "7 días"),
            ("month", "30 días"),
        ):
            t = totales.get(clave) or {}
            partes.append(f"{nombre}: <b>{coste_de(t)}</b>")
        self.totales.setText("  ·  ".join(partes))

    def _pintar_filas(self, filas: list[dict[str, Any]]) -> None:
        self.tabla.setRowCount(len(filas))
        for i, fila in enumerate(filas):
            valores = {
                FECHA: str(fila.get("fecha") or ""),
                TIPO: TIPOS.get(str(fila.get("tipo")), str(fila.get("tipo") or "")),
                TAREA: str(fila.get("tarea") or ""),
                MODELO: str(fila.get("modelo") or ""),
                LLAMADAS: miles(fila.get("llamadas") or 0),
                ENTRADA: miles(fila.get("entrada") or 0),
                SALIDA: miles(fila.get("salida") or 0),
                COSTE: coste_de(fila),
            }
            for columna, texto in valores.items():
                item = QTableWidgetItem(texto)
                if columna in NUMERICAS:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if columna == MODELO:
                    item.setToolTip(texto)
                self.tabla.setItem(i, columna, item)

        vacia = not filas
        self.tabla.setVisible(not vacia)
        self.vacio.setVisible(vacia)
        # El alto justo para las filas, contando el marco y la barra
        # horizontal: sin ella en la cuenta, cuando aparece se come la última
        # fila y sale una barra vertical para ver una sola línea.
        visibles = min(len(filas), FILAS_VISIBLES)
        self.tabla.setFixedHeight(
            self.tabla.horizontalHeader().sizeHint().height()
            + visibles * ALTO_FILA
            + 2 * self.tabla.frameWidth()
            + self.tabla.horizontalScrollBar().sizeHint().height()
        )


__all__ = ["TarjetaConsumo", "coste_de", "dinero", "miles"]
