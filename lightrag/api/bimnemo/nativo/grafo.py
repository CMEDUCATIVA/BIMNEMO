"""El grafo de conocimiento, dibujado con Qt.

Es una traducción de `ui/js/grafo-lienzo.js`, **con sus mismas constantes**.
No se han recalibrado: están ajustadas para que un grafo mediano se asiente
bien, y cambiarlas «a ojo» aquí haría que la misma memoria se viera distinta
según por dónde se mire, que es exactamente lo que no queremos.

## Por qué numpy y no un bucle

La repulsión es de todos contra todos: con 250 nodos son 31.000 parejas por
fotograma, y a 60 por segundo salen casi dos millones de operaciones por
segundo. En Python puro eso se arrastra. Con numpy es una resta de matrices y
no se nota. numpy ya es dependencia de LightRAG, así que no añade nada.

## Se para solo

La simulación tiene una «temperatura» que baja en cada paso; al llegar a
`ALPHA_MIN` el reloj se detiene. Un grafo quieto que sigue calculando es un
ventilador encendido para no mover nada.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

# --- Constantes de la simulación, copiadas de `grafo-lienzo.js` -------------

REPULSION = 2400.0  # Empuje entre nodos; subirlo abre el grafo.
SPRING = 0.05  # Tirón de cada arista.
SPRING_LEN = 96.0  # Longitud en reposo de una arista, en píxeles.
GRAVITY = 0.015  # Atracción hacia el centro, para que no se escape.
DAMPING = 0.82  # Rozamiento; sin él el grafo oscila y no se asienta.
ALPHA_DECAY = 0.984
ALPHA_MIN = 0.008
MAX_STEP = 40.0  # Tope de desplazamiento por paso, contra explosiones.

#: Cuántas entidades llevan rótulo, de más conectadas a menos. Con todas, un
#: grafo mediano se convierte en una mancha de texto; sin ninguna, es un
#: adorno. Las más conectadas son las que dan sentido a lo demás.
ROTULADAS = 40

#: Los colores de categoría de `tokens.css`, en el orden de `PALETTE`.
COLORES = (
    "#0ea5e9",  # sky
    "#8b5cf6",  # violet
    "#10b981",  # emerald
    "#f97316",  # orange
    "#14b8a6",  # teal
    "#f43f5e",  # rose
    "#f59e0b",  # amber
    "#64748b",  # slate
)

#: 16 ms ≈ 60 fotogramas por segundo.
PASO_MS = 16


def radio_de(grado: int) -> float:
    """El mismo tamaño de nodo que la web: crece con la raíz del grado."""
    return 6.0 + min(15.0, math.sqrt(max(grado, 0)) * 3.2)


class Grafo(QWidget):
    """Lienzo del grafo: simulación, dibujo y gestos."""

    #: Se emite al elegir un nodo, o con `None` al soltar la selección.
    elegido = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # Alto generoso a propósito: con poco sitio, el encuadre reduce
        # tanto la escala que los nodos quedan en dos píxeles y los
        # rótulos no llegan a salir. Un grafo que no se lee no informa.
        self.setMinimumHeight(560)
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)

        self._nodos: list[dict[str, Any]] = []
        self._aristas: list[tuple[int, int]] = []
        self._color: list[QColor] = []
        self._radio: np.ndarray = np.zeros(0)
        self._pos: np.ndarray = np.zeros((0, 2))
        self._vel: np.ndarray = np.zeros((0, 2))
        self._con_rotulo: set[int] = set()

        self._alpha = 0.0
        self._vista = [0.0, 0.0, 1.0]  # desplazamiento x, y, y escala
        self._encima: Optional[int] = None
        self._elegido: Optional[int] = None
        self._arrastrando: Optional[int] = None
        self._paneando: Optional[QPointF] = None

        self._reloj = QTimer(self)
        self._reloj.setInterval(PASO_MS)
        self._reloj.timeout.connect(self._paso)

    # -- datos --------------------------------------------------------------

    def poner(self, nodos: list[dict], aristas: list[dict]) -> None:
        """Carga un grafo nuevo y lo deja asentarse."""
        self._nodos = list(nodos)
        indice = {n.get("id"): i for i, n in enumerate(self._nodos)}

        self._aristas = [
            (indice[a["source"]], indice[a["target"]])
            for a in aristas
            if a.get("source") in indice and a.get("target") in indice
        ]

        # El color lo decide el tipo, y los tipos se ordenan por frecuencia:
        # así el más común se lleva siempre el primer color y el grafo no
        # cambia de aspecto entre dos lecturas seguidas de lo mismo.
        cuenta: dict[str, int] = {}
        for n in self._nodos:
            tipo = str(n.get("type") or "—")
            cuenta[tipo] = cuenta.get(tipo, 0) + 1
        orden = sorted(cuenta, key=lambda t: (-cuenta[t], t))
        del_tipo = {t: QColor(COLORES[i % len(COLORES)]) for i, t in enumerate(orden)}
        self._color = [del_tipo[str(n.get("type") or "—")] for n in self._nodos]

        grados = [int(n.get("degree") or 0) for n in self._nodos]
        self._radio = np.array([radio_de(g) for g in grados], dtype=float)
        self._con_rotulo = set(
            sorted(range(len(grados)), key=lambda i: -grados[i])[:ROTULADAS]
        )

        self._repartir()
        self._elegido = None
        self._encima = None
        self._alpha = 1.0
        if self._nodos:
            self._reloj.start()
        else:
            self._reloj.stop()
        self.update()

    def _repartir(self) -> None:
        """Posiciones de partida en espiral.

        En círculo, los nodos de grado alto quedan repartidos por el borde y
        la simulación tarda mucho en recogerlos. En espiral ya salen con los
        primeros —que son los más conectados— cerca del centro.
        """
        total = len(self._nodos)
        self._pos = np.zeros((total, 2))
        self._vel = np.zeros((total, 2))
        for i in range(total):
            angulo = i * 2.399963  # ángulo áureo: reparte sin alinear
            radio = 14.0 * math.sqrt(i + 1)
            self._pos[i] = (radio * math.cos(angulo), radio * math.sin(angulo))

    # -- simulación ---------------------------------------------------------

    def _paso(self) -> None:
        if not len(self._pos) or self._alpha < ALPHA_MIN:
            self._reloj.stop()
            return

        pos = self._pos
        fuerza = np.zeros_like(pos)

        # Repulsión de todos contra todos, de una vez.
        #
        # OJO CON LA POTENCIA. En la web la fuerza vale `REPULSION / d²` y se
        # aplica sobre el vector **normalizado**, así que sobre el vector sin
        # normalizar hay que dividir por `d³`. Dividiendo por `d²` —que es lo
        # que parece a primera vista— sale una ley de `1/r` en vez de `1/r²`:
        # mucho más largo de alcance, y el grafo se desparrama hasta que el
        # encuadre lo deja en dos píxeles. Medido: escala 0,05, el mínimo.
        delta = pos[:, None, :] - pos[None, :, :]
        dist2 = np.sum(delta * delta, axis=2)
        # La diagonal es cada nodo consigo mismo: a infinito para que no se
        # empuje a sí mismo, y un suelo para cuando dos coinciden, que en el
        # primer fotograma pasa más de lo que parece.
        np.fill_diagonal(dist2, np.inf)
        dist2 = np.maximum(dist2, 1.0)
        escala = REPULSION / (dist2 * np.sqrt(dist2))
        fuerza += np.sum(delta * escala[:, :, None], axis=1)

        # Muelles de las aristas.
        for a, b in self._aristas:
            d = pos[b] - pos[a]
            largo = float(np.hypot(d[0], d[1])) or 0.01
            tiron = SPRING * (largo - SPRING_LEN) / largo
            fuerza[a] += d * tiron
            fuerza[b] -= d * tiron

        # Gravedad hacia el centro.
        fuerza -= pos * GRAVITY

        self._vel = (self._vel + fuerza) * DAMPING
        paso = self._vel * self._alpha
        # Tope por eje: sin esto, un nodo aislado con mucha repulsión sale
        # disparado y se lleva la escala del grafo con él.
        np.clip(paso, -MAX_STEP, MAX_STEP, out=paso)

        if self._arrastrando is not None:
            paso[self._arrastrando] = 0.0
            self._vel[self._arrastrando] = 0.0

        self._pos = pos + paso
        self._alpha *= ALPHA_DECAY
        self.update()

    # -- vista --------------------------------------------------------------

    def encuadrar(self) -> None:
        """Centra y ajusta el zoom para que quepa todo."""
        if not len(self._pos):
            return
        minimos = self._pos.min(axis=0)
        maximos = self._pos.max(axis=0)
        ancho = max(float(maximos[0] - minimos[0]), 1.0)
        alto = max(float(maximos[1] - minimos[1]), 1.0)

        margen = 60.0
        escala = min(
            (self.width() - margen) / ancho, (self.height() - margen) / alto, 2.0
        )
        centro = (minimos + maximos) / 2.0
        self._vista = [
            self.width() / 2.0 - centro[0] * escala,
            self.height() / 2.0 - centro[1] * escala,
            max(escala, 0.05),
        ]
        self.update()

    def _a_pantalla(self, punto: np.ndarray) -> QPointF:
        x, y, k = self._vista
        return QPointF(punto[0] * k + x, punto[1] * k + y)

    def _a_mundo(self, punto: QPointF) -> np.ndarray:
        x, y, k = self._vista
        return np.array([(punto.x() - x) / k, (punto.y() - y) / k])

    def _nodo_en(self, punto: QPointF) -> Optional[int]:
        if not len(self._pos):
            return None
        mundo = self._a_mundo(punto)
        d = np.hypot(*(self._pos - mundo).T)
        # El radio se compara en píxeles: con el zoom muy alejado, un nodo
        # dibujado de 3 píxeles no puede exigir 20 de puntería.
        cerca = d - self._radio / max(self._vista[2], 0.05)
        i = int(np.argmin(cerca))
        return i if cerca[i] <= 0 else None

    # -- dibujo -------------------------------------------------------------

    def paintEvent(self, _evento) -> None:  # noqa: N802 (nombre de Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)
        pintor.fillRect(self.rect(), QColor("#020617"))

        if not self._nodos:
            pintor.setPen(QColor("#94a3b8"))
            pintor.drawText(
                self.rect(),
                Qt.AlignCenter,
                "Todavía no hay nada en el grafo.\n"
                "Sube un documento y BIMNEMO lo llenará.",
            )
            return

        k = self._vista[2]

        pluma = QPen(QColor(148, 163, 184, 95))
        pluma.setWidthF(max(0.6, 1.0 * k))
        pintor.setPen(pluma)
        for a, b in self._aristas:
            pintor.drawLine(self._a_pantalla(self._pos[a]), self._a_pantalla(self._pos[b]))

        fuente = QFont(self.font())
        fuente.setPointSizeF(max(6.0, 8.0 * min(k, 1.6)))
        pintor.setFont(fuente)

        for i, nodo in enumerate(self._nodos):
            centro = self._a_pantalla(self._pos[i])
            radio = self._radio[i] * k

            color = QColor(self._color[i])
            if i == self._elegido:
                pintor.setPen(QPen(QColor("#f1f5f9"), 2.0))
            elif i == self._encima:
                pintor.setPen(QPen(QColor("#cbd5e1"), 1.5))
            else:
                pintor.setPen(Qt.NoPen)
            pintor.setBrush(color)
            pintor.drawEllipse(centro, radio, radio)

            if i in self._con_rotulo and k > 0.35:
                pintor.setPen(QColor("#cbd5e1"))
                pintor.drawText(
                    QRectF(centro.x() - 70, centro.y() + radio + 1, 140, 14),
                    Qt.AlignHCenter | Qt.AlignTop,
                    str(nodo.get("label") or nodo.get("id") or ""),
                )

    # -- gestos -------------------------------------------------------------

    def wheelEvent(self, evento: QWheelEvent) -> None:  # noqa: N802
        factor = 1.0 + evento.angleDelta().y() / 1200.0
        antes = self._a_mundo(evento.position())
        self._vista[2] = max(0.05, min(6.0, self._vista[2] * factor))
        despues = self._a_mundo(evento.position())
        # Se corrige el desplazamiento para que el zoom ocurra bajo el ratón
        # y no en el centro de la ventana, que desorienta.
        self._vista[0] += (despues[0] - antes[0]) * self._vista[2]
        self._vista[1] += (despues[1] - antes[1]) * self._vista[2]
        self.update()

    def mousePressEvent(self, evento: QMouseEvent) -> None:  # noqa: N802
        if evento.button() != Qt.LeftButton:
            return
        i = self._nodo_en(evento.position())
        if i is not None:
            self._arrastrando = i
            self._elegido = i
            self.elegido.emit(self._nodos[i])
            # Al mover un nodo se recalienta un poco la simulación: si no,
            # el grafo se queda como estaba y el arrastre no sirve de nada.
            self._alpha = max(self._alpha, 0.35)
            if not self._reloj.isActive():
                self._reloj.start()
        else:
            self._paneando = evento.position()
            self._elegido = None
            self.elegido.emit(None)
            self.setCursor(Qt.ClosedHandCursor)
        self.update()

    def mouseMoveEvent(self, evento: QMouseEvent) -> None:  # noqa: N802
        if self._arrastrando is not None:
            self._pos[self._arrastrando] = self._a_mundo(evento.position())
            self.update()
            return
        if self._paneando is not None:
            delta = evento.position() - self._paneando
            self._vista[0] += delta.x()
            self._vista[1] += delta.y()
            self._paneando = evento.position()
            self.update()
            return

        antes = self._encima
        self._encima = self._nodo_en(evento.position())
        if self._encima is not None:
            nodo = self._nodos[self._encima]
            self.setToolTip(
                f"{nodo.get('label') or nodo.get('id')}\n"
                f"{nodo.get('type') or ''} · {nodo.get('degree', 0)} relaciones"
            )
        else:
            self.setToolTip("")
        if antes != self._encima:
            self.update()

    def mouseReleaseEvent(self, _evento: QMouseEvent) -> None:  # noqa: N802
        self._arrastrando = None
        self._paneando = None
        self.setCursor(Qt.OpenHandCursor)
