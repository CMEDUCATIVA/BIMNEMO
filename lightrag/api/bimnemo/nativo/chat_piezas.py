"""Las piezas del chat: la barra de arriba, el vacío y el compositor.

Están fuera de `pantalla_chat.py` para que esa pantalla se quede con lo que
de verdad hace —preguntar y pintar la respuesta— y no con trescientas líneas
de montar controles.

Los tres selectores y sus opciones son **los mismos de la interfaz web**, con
los mismos rótulos. Que la misma pregunta se haga igual en los dos sitios no
es cosmética: quien aprende a usar uno sabe usar el otro.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo import iconos

#: Valor del selector de memorias que significa «todas».
TODAS = "__all__"

#: Los modos de consulta, con el mismo rótulo que la web.
MODOS = (
    ("mix", "mix — grafo + vectores"),
    ("hybrid", "hybrid — local + global"),
    ("local", "local — entidades concretas"),
    ("global", "global — relaciones y temas"),
    ("naive", "naive — solo vectores"),
)

#: Qué se pide de vuelta.
#:
#: «Solo contexto recuperado» no es un modo de depuración: es lo que quiere
#: un agente que ya tiene su propio modelo, y no gasta la llamada al que
#: redacta. Por eso está a la vista y no escondido.
DEVOLUCIONES = (
    ("answer", "Respuesta generada"),
    ("context", "Solo contexto recuperado"),
)


class Barra(QFrame):
    """Buscar en · Modo · Devolver, y el botón de limpiar."""

    cambiado = Signal()
    limpiar = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("chat-barra")

        fila = QHBoxLayout(self)
        fila.setContentsMargins(14, 10, 14, 10)
        fila.setSpacing(8)

        self.memoria = QComboBox()
        self.memoria.addItem("Todas las memorias", TODAS)
        self.memoria.setMinimumWidth(150)
        # `currentIndexChanged` manda el índice; `cambiado` no lleva nada.
        # Conectados a pelo, Qt se queja en cada cambio de memoria.
        self.memoria.currentIndexChanged.connect(lambda _i: self.cambiado.emit())
        self._campo(fila, "Buscar en", self.memoria)

        self.modo = QComboBox()
        for clave, rotulo in MODOS:
            self.modo.addItem(rotulo, clave)
        self.modo.setMinimumWidth(170)
        self._campo(fila, "Modo", self.modo)

        self.devolver = QComboBox()
        for clave, rotulo in DEVOLUCIONES:
            self.devolver.addItem(rotulo, clave)
        self.devolver.setMinimumWidth(150)
        self._campo(fila, "Devolver", self.devolver)

        fila.addStretch(1)

        self.boton_limpiar = QPushButton("  Limpiar")
        self.boton_limpiar.setObjectName("fantasma")
        self.boton_limpiar.setIcon(iconos.icono("borrar", 13, "texto_2"))
        self.boton_limpiar.setCursor(Qt.PointingHandCursor)
        self.boton_limpiar.clicked.connect(self.limpiar.emit)
        fila.addWidget(self.boton_limpiar)

    @staticmethod
    def _campo(fila: QHBoxLayout, rotulo: str, control: QWidget) -> None:
        """Rótulo a la izquierda del control, como en la web.

        No encima: esta barra es una línea sola, y poniendo los rótulos
        arriba se duplicaría su alto para no decir nada más.
        """
        etiqueta = QLabel(rotulo)
        etiqueta.setObjectName("descripcion")
        fila.addWidget(etiqueta)
        fila.addWidget(control)

    def poner_memorias(
        self, memorias: list[dict[str, Any]], activa: Optional[str] = None
    ) -> None:
        """Rellena «Buscar en» conservando lo que hubiera elegido.

        ``activa`` es la memoria abierta en la barra de arriba, y solo se usa
        **la primera vez**, cuando todavía no hay nada elegido: es lo que
        contesta a «¿en qué estoy trabajando?». Después manda lo que haya
        elegido la persona, que para eso está el selector.
        """
        # «Primera vez» es que solo esté el «Todas las memorias» de salida:
        # el selector nace con él, así que `currentData()` nunca es nulo y no
        # sirve para saber si alguien ha elegido algo.
        primera_vez = self.memoria.count() <= 1
        elegida = self.memoria.currentData()
        if primera_vez and activa is not None:
            elegida = activa
        self.memoria.blockSignals(True)
        self.memoria.clear()
        self.memoria.addItem("Todas las memorias", TODAS)
        for nemo in memorias:
            nombre = str(nemo.get("name") or nemo.get("id") or "")
            if nombre:
                self.memoria.addItem(nombre, nemo.get("id", ""))
        indice = self.memoria.findData(elegida)
        if indice >= 0:
            self.memoria.setCurrentIndex(indice)
        self.memoria.blockSignals(False)

    def elegir_memoria(self, nemo: str) -> bool:
        """Deja «Buscar en» en esa memoria. Devuelve si estaba en la lista."""
        indice = self.memoria.findData(nemo)
        if indice < 0:
            return False
        self.memoria.blockSignals(True)
        self.memoria.setCurrentIndex(indice)
        self.memoria.blockSignals(False)
        return True

    # -- lo que se ha elegido ----------------------------------------------

    @property
    def en_todas(self) -> bool:
        return self.memoria.currentData() == TODAS

    @property
    def nemo(self) -> str:
        datos = self.memoria.currentData()
        return "" if datos == TODAS else str(datos or "")

    @property
    def solo_contexto(self) -> bool:
        return self.devolver.currentData() == "context"


class Vacio(QWidget):
    """Lo que se ve antes de la primera pregunta.

    Explica **lo que no se ve**: que por defecto busca en todas las memorias
    y que se puede pedir solo el contexto. Son las dos cosas que nadie
    descubre solo, y las dos están en los selectores de arriba.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("fila")

        columna = QVBoxLayout(self)
        columna.setContentsMargins(24, 40, 24, 40)
        columna.setSpacing(10)
        columna.addStretch(1)

        marca = QLabel()
        marca.setPixmap(iconos.pixmap("conversacion", 26, "texto_3"))
        marca.setAlignment(Qt.AlignCenter)
        columna.addWidget(marca)

        titulo = QLabel("Pregunta a tu memoria")
        titulo.setObjectName("subtitulo")
        titulo.setAlignment(Qt.AlignCenter)
        columna.addWidget(titulo)

        texto = QLabel(
            "Por defecto busca en <b>todas</b> tus memorias y te dice de cuál "
            "sale cada dato.<br>Puedes acotar a una desde «Buscar en». Con "
            "«Solo contexto recuperado» ves lo que el motor encuentra sin "
            "gastar una llamada al modelo que redacta."
        )
        texto.setObjectName("descripcion")
        texto.setAlignment(Qt.AlignCenter)
        texto.setWordWrap(True)
        columna.addWidget(texto)

        columna.addStretch(1)


class _Caja(QPlainTextEdit):
    """La caja de escribir. Enter envía; Mayús+Enter salta línea.

    Es una subclase y no un filtro sobre el marco porque las teclas llegan
    **al widget que tiene el foco**, que es esta caja. Puesto en el marco,
    el atajo no se dispararía nunca.
    """

    enviar = Signal()

    def keyPressEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        if evento.key() in (Qt.Key_Return, Qt.Key_Enter):
            if evento.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(evento)
                return
            self.enviar.emit()
            return
        super().keyPressEvent(evento)


class Compositor(QFrame):
    """La caja de escribir y el botón de enviar."""

    enviar = Signal()

    #: Alto de una línea y tope al que deja de crecer. Un compositor que se
    #: come media pantalla al pegar un texto largo tapa justamente la
    #: respuesta que se acaba de leer.
    ALTO_BASE = 42
    LINEAS_MAXIMAS = 6

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("chat-compositor")

        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)

        self.entrada = _Caja()
        self.entrada.setObjectName("entrada")
        self.entrada.setPlaceholderText(
            "Pregunta a tu memoria… (Enter envía, Mayús+Enter salta línea)"
        )
        self.entrada.setFixedHeight(self.ALTO_BASE)
        self.entrada.enviar.connect(self.enviar.emit)
        self.entrada.textChanged.connect(self._ajustar_alto)
        fila.addWidget(self.entrada, 1)

        self.boton = QPushButton("  Enviar")
        self.boton.setObjectName("principal")
        self.boton.setIcon(iconos.icono("enviar", 14, "#ffffff"))
        self.boton.setCursor(Qt.PointingHandCursor)
        self.boton.setFixedHeight(self.ALTO_BASE)
        self.boton.clicked.connect(self.enviar.emit)
        fila.addWidget(self.boton)

    def _ajustar_alto(self) -> None:
        """Crece con lo escrito, hasta el tope."""
        lineas = max(1, min(self.LINEAS_MAXIMAS, self.entrada.blockCount()))
        alto = self.ALTO_BASE + (lineas - 1) * 19
        if alto != self.entrada.height():
            self.entrada.setFixedHeight(alto)
            self.boton.setFixedHeight(alto)

    def texto(self) -> str:
        return self.entrada.toPlainText().strip()

    def vaciar(self) -> None:
        self.entrada.clear()
