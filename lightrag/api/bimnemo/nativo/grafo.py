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
import unicodedata
from typing import Any, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from lightrag.api.bimnemo.nativo import disposicion, silueta, tema

# --- Constantes de la simulación, copiadas de `grafo-lienzo.js` -------------

REPULSION = 2400.0  # Empuje entre nodos; subirlo abre el grafo.
SPRING = 0.05  # Tirón de cada arista.
SPRING_LEN = 96.0  # Longitud en reposo de una arista, en píxeles.
GRAVITY = 0.015  # Atracción hacia el centro, para que no se escape.
DAMPING = 0.82  # Rozamiento; sin él el grafo oscila y no se asienta.
ALPHA_DECAY = 0.984
ALPHA_MIN = 0.008
MAX_STEP = 40.0  # Tope de desplazamiento por paso, contra explosiones.

# Force Atlas reparte distinto: la repulsión crece con el número de relaciones
# de CADA extremo, así que los concentradores se apartan entre sí y arrastran a
# sus vecinos; y la atracción es lineal con la distancia, sin longitud en
# reposo. El resultado son cúmulos marcados en vez del reparto parejo de las
# fuerzas normales.
#
# Las dos constantes están calibradas para que un par unido se equilibre en
# `10 * raíz((ga+1)(gb+1))` píxeles. Con los valores «naturales» de la fórmula,
# la repulsión salía cien veces mayor que la atracción y el grafo se deshacía.
ATLAS_REPULSION = 2.0
ATLAS_ATTRACTION = 0.02

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

#: El color de la búsqueda y de las sinapsis, según el fondo.
#:
#: Ámbar y no el azul de marca: el azul es el color que el reparto por
#: frecuencia le da al tipo de entidad más común, así que un acierto azul
#: sobre un nodo azul no se distinguía de sus vecinos.
#:
#: Pero el ámbar solo salta sobre un fondo oscuro. Sobre uno claro se lava —
#: una línea fina de dos píxeles desaparece— y ahí hace falta un naranja
#: quemado, que es el mismo tono con la luz que el fondo claro le quita.
AMBAR = "#fbbf24"
NARANJA = "#ea580c"


def _fondo_claro() -> bool:
    """¿El lienzo es claro?

    Se mide la luminosidad del color de fondo en vez de comparar con la
    paleta clara. Así sigue acertando el día que haya un tema más: lo que
    decide si un naranja se lee no es cómo se llame el tema, es cuánta luz
    tiene detrás.
    """
    fondo = QColor(tema.ACTUAL.fondo)
    return (
        0.2126 * fondo.redF() + 0.7152 * fondo.greenF() + 0.0722 * fondo.blueF()
    ) > 0.5


def color_pulso() -> QColor:
    """El color con el que se pintan la búsqueda y las sinapsis."""
    return QColor(NARANJA if _fondo_claro() else AMBAR)


#: 16 ms ≈ 60 fotogramas por segundo.
PASO_MS = 16

# --- Sinapsis ---------------------------------------------------------------

#: Cuánto tarda el impulso en recorrer una arista, en milisegundos.
SINAPSIS_TRAMO_MS = 420

#: Cuántos saltos se propaga desde el nodo de partida. Con más, el grafo
#: entero se enciende de una vez y deja de leerse como un recorrido.
SINAPSIS_SALTOS = 4

#: Cuántas aristas como mucho salen de cada nodo. Un concentrador con
#: treinta y siete relaciones encendería medio grafo en un solo salto.
SINAPSIS_RAMAS = 3

#: El empujón que deja el impulso en el nodo al que llega, y cuánta vida le
#: devuelve a la simulación.
#:
#: Es el mismo mecanismo que recalienta el grafo al pulsar un nodo, pero
#: treinta y cinco veces más flojo: allí `alpha` sube a 0,35 y el grafo se
#: recoloca entero; aquí sube lo justo para que la red tiemble y se vuelva a
#: posar. Los muelles de las aristas hacen el resto —el vecino tira del
#: vecino— y eso es lo que se ve como agua.
#:
#: Las dos constantes hacen cosas distintas, y por eso se calibran aparte:
#: `alpha` decide cuánto se mueve **todo el grafo** y `empuje`, cuánto se
#: mueve **lo que el impulso toca**. Con `alpha` alto el temblor deja de ser
#: local: la red entera se recoloca y ya no se lee como algo que recorre unas
#: relaciones concretas.
#:
#: Medido sobre una sinapsis entera —sus cuatro saltos— con 191 nodos: los 15
#: nodos que toca se mueven 6,2 px de media y 12,9 el que más; el resto del
#: grafo, 1 px. Todo vuelve a la quietud en 0,9 s, mucho antes de la
#: siguiente sinapsis, que llega a los 5 s.
SINAPSIS_EMPUJE = 90.0
SINAPSIS_ALPHA = 0.010


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
        # Mínimo bajo a propósito. Con 300 píxeles, en una ventana corta el
        # box no daba para lienzo + leyenda y Qt los solapaba: medido, el pie
        # empezaba **nueve píxeles antes** de que el lienzo terminara. Quien
        # manda sobre el alto es la leyenda, que es texto y no se puede
        # encoger; el lienzo cede lo que haga falta.
        self.setMinimumHeight(160)
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)

        self._nodos: list[dict[str, Any]] = []
        self._aristas: list[tuple[int, int]] = []
        self._color: list[QColor] = []
        self._radio: np.ndarray = np.zeros(0)
        self._pos: np.ndarray = np.zeros((0, 2))
        self._vel: np.ndarray = np.zeros((0, 2))
        self._con_rotulo: set[int] = set()
        self._grados: np.ndarray = np.zeros(0)
        self._tipos: list[tuple[str, int, QColor]] = []
        self._disposicion = disposicion.POR_DEFECTO
        self._resaltados: set[int] = set()
        self._vecinos: set[int] = set()
        self._encuadre_pendiente = False
        #: ¿Ha movido el usuario la vista a mano?
        #:
        #: Mientras no la toque, el grafo se reencuadra solo cada vez que su
        #: caja cambia de tamaño —al pasar a apilado, al maximizar—. En
        #: cuanto arrastra o hace zoom, deja de hacerlo: reencuadrar encima
        #: de alguien que acaba de colocarse donde quería es lo más molesto
        #: que puede hacer una interfaz. Vuelve a seguirle el tamaño con el
        #: botón de encajar o al cargar otro grafo.
        self._vista_tocada = False
        #: Impulsos vivos: (arista, cuándo empezó, cuántos saltos le quedan).
        self._sinapsis: list[tuple[int, int, float, int]] = []
        self._reloj_sinapsis = QTimer(self)
        self._reloj_sinapsis.setInterval(PASO_MS)
        self._reloj_sinapsis.timeout.connect(self._latir)

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
        self._grados = np.array(grados, dtype=float)
        self._radio = np.array([radio_de(g) for g in grados], dtype=float)
        self._con_rotulo = set(
            sorted(range(len(grados)), key=lambda i: -grados[i])[:ROTULADAS]
        )
        # La leyenda de abajo: tipo, cuántos hay y de qué color se pintan.
        self._tipos = [(t, cuenta[t], del_tipo[t]) for t in orden]

        self._repartir()
        self._elegido = None
        self._encima = None
        self._resaltados = set()
        self._vecinos = set()
        self._encuadre_pendiente = True
        self._vista_tocada = False
        self._colocar()
        self.update()

    def tipos(self) -> list[tuple[str, int, QColor]]:
        """Lo que necesita la leyenda: tipo, cuántos y su color."""
        return list(self._tipos)

    def disponer(self, clave: str) -> None:
        """Cambia la disposición y recoloca."""
        self._disposicion = clave
        self._colocar()
        self.encuadrar()
        self.update()

    def _colocar(self) -> None:
        """Aplica la disposición elegida.

        Las fijas colocan y apagan la simulación; las de simulación la
        encienden y dejan que el grafo se asiente solo.
        """
        if not self._nodos:
            self._reloj.stop()
            return
        if disposicion.aplicar(self._disposicion, self._nodos, self._pos):
            self._vel[:] = 0.0
            self._alpha = 0.0
            self._reloj.stop()
            return
        self._alpha = 1.0
        self._reloj.start()

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
            # Encuadrar **al terminar**, no al empezar. Al cargar, los nodos
            # están todavía amontonados en la espiral de partida: encuadrar
            # ahí daba un zoom pegadísimo, y cuando el grafo se abría ya
            # nadie lo recolocaba.
            if self._encuadre_pendiente:
                self._encuadre_pendiente = False
                self.encuadrar(por_el_usuario=False)
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
        atlas = self._disposicion == "atlas"
        if atlas:
            # La repulsión crece con las relaciones de cada extremo: los
            # concentradores se apartan y arrastran a sus vecinos.
            peso = self._grados + 1.0
            escala = (ATLAS_REPULSION * peso[:, None] * peso[None, :]) / (
                dist2 * np.sqrt(dist2)
            )
        else:
            escala = REPULSION / (dist2 * np.sqrt(dist2))
        np.fill_diagonal(escala, 0.0)
        fuerza += np.sum(delta * escala[:, :, None], axis=1)

        # Muelles de las aristas.
        for a, b in self._aristas:
            d = pos[b] - pos[a]
            largo = float(np.hypot(d[0], d[1])) or 0.01
            # En Atlas la atracción es lineal con la distancia y sin longitud
            # en reposo: por eso hace cúmulos en vez de repartir parejo.
            tiron = ATLAS_ATTRACTION if atlas else SPRING * (largo - SPRING_LEN) / largo
            fuerza[a] += d * tiron
            fuerza[b] -= d * tiron

        # Gravedad hacia el centro.
        fuerza -= pos * GRAVITY

        # Y, si toca, el contorno devolviendo dentro a los que se salen.
        if self._disposicion == "cerebro":
            fuerza += silueta.contener(pos, silueta.escala_para(len(pos)))

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

    # -- sinapsis -----------------------------------------------------------

    def disparar_sinapsis(self, desde: Optional[int] = None) -> None:
        """Lanza un impulso que recorre las relaciones desde un nodo.

        Sin nodo de partida elige uno al azar **entre los conectados**: el
        grafo tiene entidades sueltas, y un impulso que sale de una de ellas
        no recorre nada y parece que no ha pasado.
        """
        import random

        if not self._aristas:
            return

        if desde is None:
            a, b = random.choice(self._aristas)
            desde = a if random.random() < 0.5 else b

        self._encender(desde, SINAPSIS_SALTOS)
        if not self._reloj_sinapsis.isActive():
            self._reloj_sinapsis.start()

    def _encender(self, nodo: int, saltos: int) -> None:
        """Enciende las aristas que salen de un nodo."""
        import random
        import time

        if saltos <= 0:
            return
        vecinas = [(a, b) for a, b in self._aristas if a == nodo or b == nodo]
        if not vecinas:
            return

        ahora = time.monotonic()
        for a, b in random.sample(vecinas, min(len(vecinas), SINAPSIS_RAMAS)):
            # Se guarda con el origen primero, para que el impulso viaje
            # **desde** el nodo que se encendió y no al revés.
            origen, destino = (a, b) if a == nodo else (b, a)
            self._sinapsis.append((origen, destino, ahora, saltos))

    def _ondular(self, origen: int, destino: int) -> None:
        """El temblor que deja el impulso al llegar a un nodo.

        Se empuja **en la dirección en la que viajaba**, no al azar: lo que
        se está representando es algo que llega y mueve lo que toca.

        No se mueve el nodo: se le suma velocidad y se despierta un poco la
        simulación. Moverlo directamente sería un salto; así lo apartan las
        fuerzas y lo devuelven los muelles, que es lo que hace que el vecino
        se entere y el temblor se reparta.

        En las disposiciones fijas no se hace nada. Ahí los nodos están
        colocados a propósito —el círculo, los anillos por tipo— y encender
        las fuerzas deshace en dos segundos lo que el usuario acaba de pedir.
        """
        if not disposicion.es_simulacion(self._disposicion):
            return

        direccion = self._pos[destino] - self._pos[origen]
        largo = float(np.hypot(direccion[0], direccion[1]))
        if largo < 1e-6:
            return

        self._vel[destino] += direccion / largo * SINAPSIS_EMPUJE
        self._alpha = max(self._alpha, SINAPSIS_ALPHA)
        if not self._reloj.isActive():
            self._reloj.start()

    def _latir(self) -> None:
        """Avanza los impulsos y propaga los que llegan al otro extremo."""
        import time

        if not self._sinapsis:
            self._reloj_sinapsis.stop()
            return

        ahora = time.monotonic()
        siguen = []
        for origen, destino, cuando, saltos in self._sinapsis:
            if (ahora - cuando) * 1000.0 < SINAPSIS_TRAMO_MS:
                siguen.append((origen, destino, cuando, saltos))
                continue
            # Llegó: empuja lo que ha alcanzado y salta al siguiente tramo.
            self._ondular(origen, destino)
            self._encender(destino, saltos - 1)

        self._sinapsis = siguen
        self.update()

    # -- vista --------------------------------------------------------------

    def encuadrar(self, por_el_usuario: bool = True) -> None:
        """Centra y ajusta el zoom para que quepa todo."""
        if por_el_usuario:
            # Pulsar «encajar» vuelve a poner el grafo a seguir el tamaño de
            # su caja. Es la forma de deshacer un zoom del que uno se
            # arrepiente sin tener que recargar.
            self._vista_tocada = False
        if not len(self._pos):
            return
        minimos = self._pos.min(axis=0)
        maximos = self._pos.max(axis=0)
        ancho = max(float(maximos[0] - minimos[0]), 1.0)
        alto = max(float(maximos[1] - minimos[1]), 1.0)

        # Tope de 1.0 y no de 2.0: con pocas entidades el encuadre se pegaba
        # hasta duplicar el tamaño natural y el grafo entraba «con lupa». Un
        # grafo se lee mejor con aire alrededor que ocupando hasta el borde.
        margen = 110.0
        escala = min(
            (self.width() - margen) / ancho, (self.height() - margen) / alto, 1.0
        )
        centro = (minimos + maximos) / 2.0
        self._vista = [
            self.width() / 2.0 - centro[0] * escala,
            self.height() / 2.0 - centro[1] * escala,
            max(escala, 0.05),
        ]
        self.update()

    def acercar(self, factor: float = 1.25) -> None:
        """Zoom desde el botón: sobre el centro del lienzo, no sobre el ratón."""
        centro = QPointF(self.width() / 2.0, self.height() / 2.0)
        antes = self._a_mundo(centro)
        self._vista[2] = max(0.05, min(6.0, self._vista[2] * factor))
        despues = self._a_mundo(centro)
        self._vista[0] += (despues[0] - antes[0]) * self._vista[2]
        self._vista[1] += (despues[1] - antes[1]) * self._vista[2]
        self.update()

    def alejar(self) -> None:
        self.acercar(1 / 1.25)

    @staticmethod
    def _sin_tildes(texto: str) -> str:
        """Para comparar nombres sin que una tilde decida el resultado.

        Buscar «modulo» y no encontrar «Módulo Reuniones» es, en castellano,
        una búsqueda rota: nadie escribe las tildes al buscar. Comprobado
        antes de arreglarlo: daba **cero** resultados con el grafo lleno de
        entidades que empiezan por «Módulo».
        """
        descompuesto = unicodedata.normalize("NFD", texto.lower())
        return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")

    def soltar(self) -> None:
        """Deshace la selección: ni nodo elegido ni relaciones aisladas."""
        self._elegido = None
        self._aislar(None)
        self.update()

    def resaltar(self, texto: str) -> int:
        """Marca las entidades cuyo nombre contenga `texto`. Devuelve cuántas.

        Resaltar y no filtrar: quitar de la vista lo que no casa deja un
        grafo sin contexto, y el contexto es justo lo que se está mirando.
        """
        aguja = self._sin_tildes((texto or "").strip())
        if not aguja:
            self._resaltados = set()
        else:
            self._resaltados = {
                i
                for i, n in enumerate(self._nodos)
                if aguja in self._sin_tildes(str(n.get("label") or n.get("id") or ""))
            }
        self.update()
        return len(self._resaltados)

    def _aislar(self, indice: Optional[int]) -> None:
        """Los vecinos del nodo elegido, para poder apagar el resto."""
        if indice is None:
            self._vecinos = set()
            return
        self._vecinos = {indice} | {
            b if a == indice else a for a, b in self._aristas if indice in (a, b)
        }

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

    def resizeEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        """Sigue el tamaño de su caja.

        Al pasar de dos columnas a apiladas, o al maximizar la ventana, la
        caja cambia de tamaño pero la vista se quedaba como estaba: el grafo
        salía descentrado, o diminuto en una caja grande.
        """
        super().resizeEvent(evento)
        if self._nodos and not self._vista_tocada:
            self.encuadrar(por_el_usuario=False)

    # -- dibujo -------------------------------------------------------------

    def paintEvent(self, _evento) -> None:  # noqa: N802 (nombre de Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)
        # Redondeado arriba y recto abajo: el lienzo ocupa la parte de
        # arriba del box y abajo lo corta la línea de separación. Sin
        # redondear arriba se comería las esquinas del box.
        fondo = QPainterPath()
        radio = 7.0
        caja = QRectF(self.rect())
        fondo.moveTo(caja.left(), caja.bottom())
        fondo.lineTo(caja.left(), caja.top() + radio)
        fondo.quadTo(caja.left(), caja.top(), caja.left() + radio, caja.top())
        fondo.lineTo(caja.right() - radio, caja.top())
        fondo.quadTo(caja.right(), caja.top(), caja.right(), caja.top() + radio)
        fondo.lineTo(caja.right(), caja.bottom())
        fondo.closeSubpath()
        pintor.fillPath(fondo, QColor(tema.ACTUAL.fondo))
        # Todo lo demás se recorta a ese fondo: ni un nodo fuera del box.
        pintor.setClipPath(fondo)

        if not self._nodos:
            pintor.setPen(QColor(tema.ACTUAL.texto_3))
            pintor.drawText(
                self.rect(),
                Qt.AlignCenter,
                "Todavía no hay nada en el grafo.\n"
                "Sube un documento y BIMNEMO lo llenará.",
            )
            return

        k = self._vista[2]

        if self._disposicion == "cerebro":
            self._pintar_silueta(pintor, k)

        # Con un nodo elegido, sus relaciones se ven y el resto se apaga:
        # eso es «aislar». Sin apagar nada, elegir no sirve de nada en un
        # grafo de doscientas entidades.
        aislando = bool(self._vecinos)
        for a, b in self._aristas:
            suya = (not aislando) or (a in self._vecinos and b in self._vecinos)
            pluma = QPen(QColor(148, 163, 184, 150 if suya and aislando else 95))
            if aislando and not suya:
                pluma.setColor(QColor(148, 163, 184, 25))
            pluma.setWidthF(max(0.6, 1.0 * k))
            pintor.setPen(pluma)
            pintor.drawLine(
                self._a_pantalla(self._pos[a]), self._a_pantalla(self._pos[b])
            )

        if self._sinapsis:
            self._pintar_sinapsis(pintor, k)

        fuente = QFont(self.font())
        fuente.setPointSizeF(max(6.0, 8.0 * min(k, 1.6)))
        pintor.setFont(fuente)

        for i, nodo in enumerate(self._nodos):
            centro = self._a_pantalla(self._pos[i])
            radio = self._radio[i] * k

            buscando = bool(self._resaltados)
            casa = i in self._resaltados

            color = QColor(self._color[i])
            if aislando and i not in self._vecinos:
                # Apagado, no escondido: sigue dando forma al conjunto.
                color.setAlpha(45)
            if buscando and not casa:
                # Buscando, lo que no casa se apaga. Un anillo de color sobre
                # un nodo del MISMO color no se ve: el resaltado tiene que
                # apagar el resto, no adornar el acierto.
                color.setAlpha(40)
            pintor.setBrush(color)

            if casa:
                # Halo ámbar alrededor del acierto, y anillo del mismo color.
                halo = QColor(color_pulso())
                halo.setAlpha(90)
                pintor.setPen(Qt.NoPen)
                pintor.setBrush(halo)
                pintor.drawEllipse(centro, radio + 7, radio + 7)
                pintor.setBrush(color)
                pintor.setPen(QPen(color_pulso(), 2.2))
            elif i == self._elegido:
                pintor.setPen(QPen(QColor(tema.ACTUAL.texto), 2.0))
            elif i == self._encima:
                pintor.setPen(QPen(QColor(tema.ACTUAL.texto_2), 1.5))
            else:
                pintor.setPen(Qt.NoPen)
            pintor.drawEllipse(centro, radio, radio)

        # Los rótulos, en una **segunda pasada**. Dibujados dentro del bucle
        # de nodos, el nodo siguiente —y sobre todo su halo de búsqueda, que
        # es más ancho que él— pintaba encima del nombre del anterior: desde
        # fuera, nombres cortados por la mitad. Todo el texto va después de
        # todos los círculos.
        for i, nodo in enumerate(self._nodos):
            if k <= 0.35:
                break
            if i not in self._con_rotulo and i not in self._resaltados:
                continue
            if aislando and i not in self._vecinos:
                continue

            centro = self._a_pantalla(self._pos[i])
            radio = self._radio[i] * k

            # El ancho del rótulo **crece con el zoom**. Con 160 píxeles
            # fijos pasaba lo contrario de lo que uno espera: al acercar, la
            # letra se hacía más grande, cabían menos caracteres en la misma
            # caja y los nombres salían más cortados que de lejos.
            ancho = max(110.0, min(420.0, 190.0 * k))
            alto = pintor.fontMetrics().height() + 2
            caja = QRectF(centro.x() - ancho / 2, centro.y() + radio + 2, ancho, alto)
            texto = pintor.fontMetrics().elidedText(
                str(nodo.get("label") or nodo.get("id") or ""),
                Qt.ElideRight,
                int(caja.width()),
            )

            if i in self._resaltados:
                # Fondo detrás del nombre del acierto: sobre una maraña de
                # aristas, el texto claro solo no se lee.
                ancho_chip = pintor.fontMetrics().horizontalAdvance(texto) + 10
                fondo = QRectF(
                    centro.x() - ancho_chip / 2,
                    caja.top() - 1,
                    ancho_chip,
                    caja.height() + 2,
                )
                pintor.setPen(Qt.NoPen)
                # Pastilla ámbar con el texto del color del fondo: se lee
                # igual de bien en tema claro y en oscuro, y no hay que
                # elegir un color de texto por tema.
                pintor.setBrush(color_pulso())
                pintor.drawRoundedRect(fondo, 3, 3)
                pintor.setPen(QColor(tema.ACTUAL.fondo))
            else:
                pintor.setPen(QColor(tema.ACTUAL.texto_2))

            pintor.setBrush(Qt.NoBrush)
            pintor.drawText(
                caja,
                Qt.AlignHCenter | Qt.AlignTop | Qt.TextSingleLine,
                texto,
            )

    def _pintar_sinapsis(self, pintor: QPainter, k: float) -> None:
        """Los impulsos recorriendo sus aristas.

        Se pinta una estela corta, no un punto: un punto de tres píxeles a
        escala reducida no se ve, y lo que hace reconocible el gesto es el
        rastro, no el móvil.
        """
        import time

        ahora = time.monotonic()
        for origen, destino, cuando, _saltos in self._sinapsis:
            avance = min(1.0, (ahora - cuando) * 1000.0 / SINAPSIS_TRAMO_MS)

            a = self._pos[origen]
            b = self._pos[destino]
            cabeza = a + (b - a) * avance
            # La cola va un 18 % por detrás, sin salirse del tramo.
            cola = a + (b - a) * max(0.0, avance - 0.18)

            # Se apaga al llegar: sin esto, el impulso desaparece de golpe
            # en el nodo de destino y parece un fallo de dibujo.
            color = color_pulso()
            color.setAlpha(int(235 * (1.0 - avance**3)))

            pluma = QPen(color, max(1.6, 2.6 * k))
            pluma.setCapStyle(Qt.RoundCap)
            pintor.setPen(pluma)
            pintor.drawLine(self._a_pantalla(cola), self._a_pantalla(cabeza))

    def _pintar_silueta(self, pintor: QPainter, k: float) -> None:
        """El contorno del cerebro, detrás de todo.

        Sin dibujarlo, la forma solo se adivina por dónde no hay nodos: con
        entidades sueltas o pocas relaciones no se reconoce nada. El trazo
        es tenue a propósito — es el recipiente, no el contenido.
        """
        escala = silueta.escala_para(len(self._pos))

        forma = QPainterPath()
        for cx, cy, rx, ry in silueta.PIEZAS:
            centro = self._a_pantalla(np.array([cx * escala, cy * escala]))
            pieza = QPainterPath()
            pieza.addEllipse(centro, rx * escala * k, ry * escala * k)
            forma = forma.united(pieza)

        # `simplified` deja el contorno de la unión y quita las costuras de
        # donde unas elipses se meten dentro de otras.
        forma = forma.simplified()

        relleno = QColor(tema.ACTUAL.azul)
        relleno.setAlpha(14)
        pintor.setPen(Qt.NoPen)
        pintor.setBrush(relleno)
        pintor.drawPath(forma)

        trazo = QColor(tema.ACTUAL.azul)
        trazo.setAlpha(70)
        pintor.setPen(QPen(trazo, max(1.0, 1.4 * k)))
        pintor.setBrush(Qt.NoBrush)
        pintor.drawPath(forma)

    # -- gestos -------------------------------------------------------------

    def wheelEvent(self, evento: QWheelEvent) -> None:  # noqa: N802
        self._vista_tocada = True
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
            self._aislar(i)
            self.elegido.emit(self._nodos[i])

            # Recalentar la simulación **solo si hay simulación**.
            #
            # Con una disposición fija —circular, por tipos, radial— los
            # nodos están colocados a propósito, y encender las fuerzas al
            # pulsar uno deshacía el círculo entero: bastaba con elegir una
            # entidad para perder la disposición que se acababa de pedir.
            #
            # En las de fuerzas sí se recalienta, porque si no el grafo se
            # queda rígido y arrastrar un nodo no sirve de nada.
            if disposicion.es_simulacion(self._disposicion):
                self._alpha = max(self._alpha, 0.35)
                if not self._reloj.isActive():
                    self._reloj.start()
        else:
            self._paneando = evento.position()
            self._elegido = None
            self._aislar(None)
            self.elegido.emit(None)
            self.setCursor(Qt.ClosedHandCursor)
        self.update()

    def mouseMoveEvent(self, evento: QMouseEvent) -> None:  # noqa: N802
        if self._arrastrando is not None:
            self._pos[self._arrastrando] = self._a_mundo(evento.position())
            self.update()
            return
        if self._paneando is not None:
            self._vista_tocada = True
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
