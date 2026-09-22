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

from datetime import date, datetime
from typing import Any, Optional
from urllib.parse import quote

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from lightrag.api.bimnemo.nativo import iconos
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Tarjeta

SONDEO_MS = 3_000

COLUMNAS = (
    "Fecha y hora",
    "Tarea",
    "Archivo",
    "Modelo",
    "Razonamiento",
    "Tokens ent. / sal.",
    "Tiempo",
    "Coste (USD)",
    "Acciones",
)
(
    FECHA,
    TAREA,
    ARCHIVO,
    MODELO,
    RAZONAMIENTO,
    TOKENS,
    TIEMPO,
    COSTE,
    ACCIONES,
) = range(len(COLUMNAS))
NUMERICAS = (TOKENS, TIEMPO, COSTE)

#: El nivel «Lo que decida el modelo», abreviado: en la tabla no cabe entero
#: junto al porcentaje.
POR_DEFECTO = {"Lo que decida el modelo": "Por defecto"}

#: Tareas que no son de ningún archivo: salen de las preguntas del chat.
DEL_CHAT = ("Responder", "Palabras clave")


def archivo_de(fila: dict[str, Any]) -> str:
    """A quién se carga la fila: el archivo, el chat, o «—» si no se sabe.

    «—» es para lo contado antes de que el consumo guardara el archivo: no se
    puede saber a posteriori y es mejor decirlo que adivinarlo.
    """
    archivo = str(fila.get("archivo") or "")
    if archivo:
        return archivo
    if fila.get("tarea") in DEL_CHAT:
        return "Preguntas del chat"
    return "—"


def razonamiento_de(fila: dict[str, Any]) -> str:
    """El nivel configurado y, si el proveedor lo informa, cuánto se pensó.

    «Por defecto · 68 %». El porcentaje es de los tokens de salida, que es
    lo que se paga caro. Si el proveedor no informa del razonamiento,
    solo el nivel: un 0 % sería afirmar algo que no se sabe. Los embeddings
    no razonan, y lo contado antes de este dato sale «—».
    """
    if fila.get("tipo") == "embedding":
        return "—"
    nivel = str(fila.get("nivel") or "") or "—"
    nivel = POR_DEFECTO.get(nivel, nivel)
    salida = int(fila.get("salida") or 0)
    razonando = int(fila.get("razonando") or 0)
    if salida and razonando:
        return f"{nivel} · {round(razonando * 100 / salida)} %"
    return nivel


def _hora(iso: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(iso)).astimezone()
    except (TypeError, ValueError):
        return None


def fecha_de(fila: dict[str, Any]) -> str:
    """«22/09 · 08:44–09:12»: el día y de qué hora a qué hora hubo llamadas.

    Cada fila junta un día de llamadas de un archivo y modelo; una sola hora
    diría solo la última. Lo contado antes de medir horas enseña solo el día.
    """
    inicio, fin = _hora(fila.get("inicio")), _hora(fila.get("fin"))
    if inicio is None or fin is None:
        dia = str(fila.get("fecha") or "")
        try:
            return date.fromisoformat(dia).strftime("%d/%m/%Y")
        except ValueError:
            return dia
    desde, hasta = inicio.strftime("%H:%M"), fin.strftime("%H:%M")
    horas = desde if desde == hasta else f"{desde}–{hasta}"
    return f"{fin.strftime('%d/%m')} · {horas}"


def duracion(segundos: float) -> str:
    """45 s · 12 min 30 s · 1 h 05 min."""
    segundos = int(round(segundos))
    if segundos < 60:
        return f"{segundos} s"
    minutos, s = divmod(segundos, 60)
    if minutos < 60:
        return f"{minutos} min {s:02d} s"
    horas, m = divmod(minutos, 60)
    return f"{horas} h {m:02d} min"


def tiempo_de(fila: dict[str, Any]) -> tuple[str, str]:
    """Lo que tardó, y cómo se ha medido (para el rótulo emergente).

    - Un **archivo**: de la primera llamada a la última, lo que tardó su
      indexación. Sumar las llamadas daría de más: van varias a la vez.
    - Lo demás (**preguntas del chat**): la suma de lo que tardó cada una. De
      la primera pregunta del día a la última no es tiempo de nadie.
    """
    if fila.get("archivo"):
        inicio, fin = _hora(fila.get("inicio")), _hora(fila.get("fin"))
        if inicio is not None and fin is not None:
            return (
                duracion((fin - inicio).total_seconds()),
                "Desde la primera llamada hasta la última: lo que tardó.",
            )
    elif fila.get("segundos") is not None:
        return (
            duracion(float(fila["segundos"])),
            "La suma de lo que tardó en contestar cada llamada.",
        )
    return "—", "Contado antes de que BIMNEMO midiera el tiempo."


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

        self.pendiente = Aviso()
        self.anadir(self.pendiente)

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
        # barra horizontal. Solo el archivo se estira: es el nombre largo.
        cabecera.setMinimumSectionSize(60)
        for columna, ancho in (
            (FECHA, 146),
            (TAREA, 112),
            (MODELO, 140),
            (RAZONAMIENTO, 140),
            (TOKENS, 140),
            (TIEMPO, 92),
            (COSTE, 84),
        ):
            cabecera.setSectionResizeMode(columna, QHeaderView.Interactive)
            self.tabla.setColumnWidth(columna, ancho)
        cabecera.setSectionResizeMode(ARCHIVO, QHeaderView.Stretch)
        # La de acciones lleva un botón de tamaño fijo: estirarla solo deja hueco.
        cabecera.setSectionResizeMode(ACCIONES, QHeaderView.Fixed)
        self.tabla.setColumnWidth(ACCIONES, 64)
        cabecera_tokens = self.tabla.horizontalHeaderItem(TOKENS)
        if cabecera_tokens is not None:
            cabecera_tokens.setToolTip("Tokens de entrada / tokens de salida")
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
        # Antes de mirar la revisión: el aviso importa aunque todavía no se
        # haya gastado nada con lo de antes.
        self._pintar_pendiente(datos)
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

    def _pintar_pendiente(self, datos: dict[str, Any]) -> None:
        """Lo guardado no es lo que usa el motor: dicho en rojo, con los nombres."""
        if not datos.get("restart_required"):
            self.pendiente.callar()
            return
        guardado = datos.get("saved_model") or "otro modelo"
        en_uso = datos.get("running_model") or "el anterior"
        if guardado != en_uso:
            texto = (
                f"Guardaste «{guardado}», pero el motor sigue usando «{en_uso}»: "
                "lo que se indexe ahora se paga con ese. "
            )
        else:
            texto = "Hay configuración guardada que el motor todavía no usa. "
        self.pendiente.fallar(
            texto + "Ve a Configuración IA y pulsa «Reiniciar motor» (si está "
            "indexando, pausa primero)."
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
            tiempo, como = tiempo_de(fila)
            valores = {
                FECHA: fecha_de(fila),
                TAREA: str(fila.get("tarea") or ""),
                ARCHIVO: archivo_de(fila),
                MODELO: str(fila.get("modelo") or ""),
                RAZONAMIENTO: razonamiento_de(fila),
                TOKENS: (
                    f"{miles(fila.get('entrada') or 0)} / "
                    f"{miles(fila.get('salida') or 0)}"
                ),
                TIEMPO: tiempo,
                COSTE: coste_de(fila),
            }
            for columna, texto in valores.items():
                item = QTableWidgetItem(texto)
                if columna in NUMERICAS:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if columna in (ARCHIVO, MODELO, RAZONAMIENTO):
                    # Recortados con puntos suspensivos: el nombre entero, aquí.
                    item.setToolTip(texto)
                if columna == TIEMPO:
                    item.setToolTip(como)
                if columna == TOKENS:
                    item.setToolTip(f"{miles(fila.get('llamadas') or 0)} llamadas")
                if columna == RAZONAMIENTO and "%" in texto:
                    item.setToolTip(
                        "Nivel configurado · parte de la salida que fue razonamiento"
                    )
                self.tabla.setItem(i, columna, item)
            self.tabla.setCellWidget(i, ACCIONES, self._acciones(fila))

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

    # -- acciones -----------------------------------------------------------

    def _acciones(self, fila: dict[str, Any]) -> QWidget:
        caja_exterior = QWidget()
        caja_exterior.setObjectName("fila")
        caja = QHBoxLayout(caja_exterior)
        caja.setContentsMargins(4, 2, 8, 2)
        caja.addStretch(1)
        borrar = QPushButton()
        borrar.setObjectName("icono")
        iconos.poner(borrar, "borrar", 14)
        borrar.setToolTip("Quitar esta fila de la tabla")
        borrar.setCursor(Qt.PointingHandCursor)
        borrar.setFixedSize(30, 26)
        borrar.setEnabled(bool(fila.get("id")))
        borrar.clicked.connect(lambda: self._borrar(fila))
        caja.addWidget(borrar)
        return caja_exterior

    def _borrar(self, fila: dict[str, Any]) -> None:
        que = archivo_de(fila)
        que = que if que != "—" else str(fila.get("tarea") or "esta fila")
        respuesta = self.confirmar(
            "Quitar de la tabla",
            f"Se quitará la fila de «{que}» ({fila.get('modelo')}, "
            f"{fecha_de(fila)}) de la tabla de uso y coste.\n\n"
            "Solo se borra de este registro: lo que el proveedor ya cobró "
            "sigue cobrado. Esto no se puede deshacer. ¿Seguir?",
        )
        if not respuesta:
            return
        self.motor.borrar(
            f"/bimnemo/usage?id={quote(str(fila['id']), safe='')}",
            None,
            lambda _datos: self.mirar(),
            lambda motivo: self.pendiente.fallar(f"No se pudo quitar: {motivo}"),
        )

    def confirmar(self, titulo: str, texto: str) -> bool:
        """Pregunta sí o no. Aparte para poder sustituirlo en las pruebas."""
        return (
            QMessageBox.question(self, titulo, texto, QMessageBox.Yes | QMessageBox.No)
            == QMessageBox.Yes
        )


__all__ = [
    "TarjetaConsumo",
    "coste_de",
    "dinero",
    "duracion",
    "fecha_de",
    "miles",
    "tiempo_de",
]
