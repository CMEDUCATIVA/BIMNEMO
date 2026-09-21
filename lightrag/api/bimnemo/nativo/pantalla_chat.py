"""Pantalla «Chat»: preguntarle a la memoria.

Va contra `POST /query`, el mismo endpoint que usa la interfaz web y el que
usaría cualquier IA conectada por la API. La respuesta trae el texto, las
referencias —qué documentos la sustentan—, cuánto tardó y si de verdad la
generó el modelo.

## Lo de «cuánto tardó» y «lo generó el modelo» no es adorno

Una pregunta puede tardar ocho segundos, y sin nada en pantalla eso se lee
como un programa colgado. Y `llm_generated` en `false` significa que lo que
se está leyendo **no lo escribió el modelo** —salió de la caché o de un
camino de respaldo—, que es justo lo que uno quiere saber antes de fiarse.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Tarjeta

#: Los modos de consulta, con la explicación del manifiesto para que quien
#: elige sepa qué está eligiendo.
MODOS = (
    ("mix", "Grafo + vectores (recomendado)"),
    ("hybrid", "Combina local y global"),
    ("local", "Entidades concretas y su contexto"),
    ("global", "Relaciones y temas amplios"),
    ("naive", "Solo búsqueda vectorial, sin grafo"),
)


class Burbuja(QWidget):
    """Un mensaje de la conversación.

    El texto es seleccionable a propósito: una respuesta que no se puede
    copiar obliga a teclearla a mano, y eso es lo primero que se intenta
    hacer con algo que ha costado ocho segundos y dinero.
    """

    def __init__(self, texto: str, mio: bool) -> None:
        super().__init__()
        self.setObjectName("fila")

        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)

        cuerpo = QLabel()
        cuerpo.setObjectName("burbuja-mia" if mio else "burbuja")
        # El modelo responde en Markdown: títulos, listas y negritas. Sin
        # esto se ven los `##` y los asteriscos en crudo, que es como leer
        # el código fuente de la respuesta en vez de la respuesta.
        #
        # Lo que escribe el usuario va en texto plano a propósito: si
        # pregunta por un `*` o un `#`, su pregunta no debe transformarse.
        cuerpo.setTextFormat(Qt.PlainText if mio else Qt.MarkdownText)
        cuerpo.setText(texto)
        cuerpo.setWordWrap(True)
        cuerpo.setOpenExternalLinks(True)
        cuerpo.setTextInteractionFlags(Qt.TextSelectableByMouse)
        cuerpo.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        cuerpo.setMaximumWidth(760)

        if mio:
            fila.addStretch(1)
            fila.addWidget(cuerpo)
        else:
            fila.addWidget(cuerpo)
            fila.addStretch(1)

        self.cuerpo = cuerpo


class PantallaChat(QWidget):
    def __init__(self, motor: Motor) -> None:
        super().__init__()
        self.motor = motor
        self._esperando = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(32, 28, 32, 20)
        raiz.setSpacing(14)

        titulo = QLabel("Chat")
        titulo.setObjectName("titulo")
        raiz.addWidget(titulo)

        descripcion = QLabel(
            "Pregúntale a esta memoria. Responde con lo que hay en tus "
            "documentos y dice de cuáles lo ha sacado."
        )
        descripcion.setObjectName("descripcion")
        descripcion.setWordWrap(True)
        raiz.addWidget(descripcion)

        self.aviso = Aviso()
        raiz.addWidget(self.aviso)

        raiz.addWidget(self._conversacion(), 1)
        raiz.addWidget(self._redaccion())

        self._saludar()

    # -- estructura ---------------------------------------------------------

    def _conversacion(self) -> QWidget:
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setObjectName("conversacion")
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        dentro = QWidget()
        dentro.setObjectName("fila")
        self.hilo = QVBoxLayout(dentro)
        self.hilo.setContentsMargins(4, 4, 12, 4)
        self.hilo.setSpacing(12)
        self.hilo.addStretch(1)
        self.area.setWidget(dentro)
        return self.area

    def _redaccion(self) -> QWidget:
        tarjeta = Tarjeta()

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)

        caja.addWidget(QLabel("Modo"))
        self.modo = QComboBox()
        for clave, rotulo in MODOS:
            self.modo.addItem(rotulo, clave)
        caja.addWidget(self.modo, 1)

        self.tiempo = QLabel("")
        self.tiempo.setObjectName("descripcion")
        caja.addWidget(self.tiempo)
        tarjeta.anadir(fila)

        abajo = QWidget()
        abajo.setObjectName("fila")
        caja2 = QHBoxLayout(abajo)
        caja2.setContentsMargins(0, 0, 0, 0)
        caja2.setSpacing(10)

        self.entrada = QPlainTextEdit()
        self.entrada.setObjectName("entrada")
        self.entrada.setPlaceholderText(
            "Escribe tu pregunta…   (Ctrl+Intro para enviar)"
        )
        self.entrada.setFixedHeight(76)
        caja2.addWidget(self.entrada, 1)

        self.boton = QPushButton("Preguntar")
        self.boton.setObjectName("principal")
        self.boton.setCursor(Qt.PointingHandCursor)
        self.boton.setFixedHeight(76)
        self.boton.clicked.connect(self.preguntar)
        caja2.addWidget(self.boton)

        tarjeta.anadir(abajo)
        return tarjeta

    def keyPressEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        # Intro a secas hace salto de línea: una pregunta larga es normal y
        # perderla por pulsar Intro sin querer es de las cosas que más
        # molestan de un chat.
        if evento.key() in (Qt.Key_Return, Qt.Key_Enter) and (
            evento.modifiers() & Qt.ControlModifier
        ):
            self.preguntar()
            return
        super().keyPressEvent(evento)

    # -- conversación -------------------------------------------------------

    def _decir(self, texto: str, mio: bool = False) -> Burbuja:
        burbuja = Burbuja(texto, mio)
        # Antes del `addStretch` final, que es lo que mantiene el hilo pegado
        # abajo cuando hay pocos mensajes.
        self.hilo.insertWidget(self.hilo.count() - 1, burbuja)
        barra = self.area.verticalScrollBar()
        barra.setValue(barra.maximum())
        return burbuja

    def _saludar(self) -> None:
        self._decir(
            "Pregúntame lo que quieras sobre tus documentos.\n\n"
            "Por ejemplo: «¿qué acuerdos se tomaron?», «¿quién es "
            "responsable de qué?», «¿qué plazos hay?»."
        )

    def preguntar(self) -> None:
        pregunta = self.entrada.toPlainText().strip()
        if not pregunta or self._esperando:
            return

        self.entrada.clear()
        self._decir(pregunta, mio=True)
        self._esperando = True
        self.boton.setEnabled(False)
        self.tiempo.setText("Pensando…")
        self._pensando = self._decir("…")

        self.motor.post(
            "/query",
            {"query": pregunta, "mode": self.modo.currentData()},
            self._respondio,
            self._no_pudo,
        )

    def _respondio(self, datos: Any) -> None:
        self._esperando = False
        self.boton.setEnabled(True)

        if not isinstance(datos, dict):
            self._pensando.cuerpo.setText("El motor devolvió algo que no entiendo.")
            return

        texto = str(datos.get("response") or "").strip() or "Sin respuesta."

        # El modelo suele citar él mismo, con marcas `[1]` y su propia lista
        # de referencias al final. Cuando lo hace, añadir otra línea con los
        # mismos documentos es repetirse; solo se añade si no citó.
        ya_cita = "[1]" in texto

        referencias = datos.get("references") or []
        if referencias and not ya_cita:
            documentos = []
            for r in referencias:
                nombre = str(r.get("file_path") or "").strip()
                if nombre and nombre not in documentos:
                    documentos.append(nombre)
            if documentos:
                texto += "\n\nDe: " + " · ".join(documentos)

        self._pensando.cuerpo.setText(texto)

        segundos = datos.get("response_time")
        partes = []
        if isinstance(segundos, (int, float)):
            partes.append(f"{segundos:.1f} s")
        if datos.get("llm_generated") is False:
            # Importa decirlo: no lo escribió el modelo, salió de la caché o
            # de un camino de respaldo.
            partes.append("sin generar (caché o respaldo)")
        self.tiempo.setText("  ·  ".join(partes))

        barra = self.area.verticalScrollBar()
        barra.setValue(barra.maximum())

    def _no_pudo(self, motivo: str) -> None:
        self._esperando = False
        self.boton.setEnabled(True)
        self.tiempo.setText("")
        self._pensando.cuerpo.setText(f"No he podido responder: {motivo}")
