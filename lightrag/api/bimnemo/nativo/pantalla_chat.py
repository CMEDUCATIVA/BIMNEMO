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

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo import chat_piezas
from lightrag.api.bimnemo.nativo.piezas import Aviso


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
        raiz.setSpacing(12)

        titulo = QLabel("Chat")
        titulo.setObjectName("titulo")
        raiz.addWidget(titulo)

        self.aviso = Aviso()
        raiz.addWidget(self.aviso)

        # La barra de la web: Buscar en · Modo · Devolver, y Limpiar.
        self.barra = chat_piezas.Barra()
        self.barra.limpiar.connect(self.limpiar)
        raiz.addWidget(self.barra)

        raiz.addWidget(self._conversacion(), 1)

        self.compositor = chat_piezas.Compositor()
        self.compositor.enviar.connect(self.preguntar)
        raiz.addWidget(self.compositor)

        self._vacio = chat_piezas.Vacio()
        self.hilo.insertWidget(self.hilo.count() - 1, self._vacio)

        self.motor.get("/bimnemo/nemos", self._poner_memorias, None)

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

    def _poner_memorias(self, datos: Any) -> None:
        if isinstance(datos, dict):
            self.barra.poner_memorias(datos.get("nemos") or [])

    def limpiar(self) -> None:
        """Vacía la conversación y deja el cartel de bienvenida."""
        while self.hilo.count() > 1:
            pieza = self.hilo.takeAt(0)
            if pieza.widget():
                pieza.widget().deleteLater()
        self._vacio = chat_piezas.Vacio()
        self.hilo.insertWidget(self.hilo.count() - 1, self._vacio)
        self.aviso.callar()

    # -- conversación -------------------------------------------------------

    def _decir(self, texto: str, mio: bool = False) -> Burbuja:
        burbuja = Burbuja(texto, mio)
        # Antes del `addStretch` final, que es lo que mantiene el hilo pegado
        # abajo cuando hay pocos mensajes.
        self.hilo.insertWidget(self.hilo.count() - 1, burbuja)
        barra = self.area.verticalScrollBar()
        barra.setValue(barra.maximum())
        return burbuja

    def preguntar(self) -> None:
        pregunta = self.compositor.texto()
        if not pregunta or self._esperando:
            return

        self.compositor.vaciar()
        if self._vacio is not None:
            self._vacio.deleteLater()
            self._vacio = None

        self._decir(pregunta, mio=True)
        self._esperando = True
        self.compositor.boton.setEnabled(False)
        self._pensando = self._decir("Pensando…")

        ruta = self._ruta()
        cuerpo: dict[str, Any] = {
            "query": pregunta,
            "mode": self.barra.modo.currentData(),
        }
        self.motor.post(ruta, cuerpo, self._respondio, self._no_pudo)

    def _ruta(self) -> str:
        """La ruta que toca, según «Buscar en» y «Devolver».

        Son cuatro combinaciones y **cada una tiene su endpoint**; no es que
        una valga para todo con un parámetro. Preguntar a todas las memorias
        no es lo mismo que preguntar a una: el motor tiene que recorrerlas y
        decir de cuál sale cada dato.

        Las rutas se escriben enteras y no se dejan al reescritor de
        `Motor`, que apunta a la memoria **activa de la aplicación**: aquí
        manda el selector del chat, que puede ser otra.
        """
        from urllib.parse import quote

        solo_contexto = self.barra.solo_contexto

        if self.barra.en_todas:
            return (
                "/bimnemo/memory/search-all"
                if solo_contexto
                else "/bimnemo/memory/ask-all"
            )

        nemo = self.barra.nemo
        if not nemo:
            # **La memoria por defecto tiene el identificador vacío**: es el
            # espacio sin nombre de LightRAG. Con la ruta espejo salía
            # `/nemo//query`, que no existe. La suya es la ruta normal.
            return "/bimnemo/memory/search" if solo_contexto else "/query"

        nombre = quote(nemo, safe="")
        return (
            f"/nemo/{nombre}/memory/search"
            if solo_contexto
            else f"/nemo/{nombre}/query"
        )

    def _respondio(self, datos: Any) -> None:
        self._esperando = False
        self.compositor.boton.setEnabled(True)

        if not isinstance(datos, dict):
            self._pensando.cuerpo.setText("El motor devolvió algo que no entiendo.")
            return

        # Con «Solo contexto recuperado» no hay respuesta redactada: lo que
        # vuelve es lo que el motor encontró, y hay que enseñarlo tal cual.
        texto = str(datos.get("response") or "").strip()
        if not texto:
            contexto = datos.get("context") or datos.get("results")
            if contexto:
                import json

                texto = (
                    "**Contexto recuperado** (sin redactar):\n\n```json\n"
                    + json.dumps(contexto, ensure_ascii=False, indent=2)[:4000]
                    + "\n```"
                )
        texto = texto or "Sin respuesta."

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
        if partes:
            self.aviso.informar("  ·  ".join(partes))
        else:
            self.aviso.callar()

        barra = self.area.verticalScrollBar()
        barra.setValue(barra.maximum())

    def _no_pudo(self, motivo: str) -> None:
        self._esperando = False
        self.compositor.boton.setEnabled(True)
        self._pensando.cuerpo.setText(f"No he podido responder: {motivo}")
