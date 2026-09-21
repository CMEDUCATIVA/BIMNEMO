"""La barra superior: marca, memoria activa y estado del motor.

Es el `topbar` de la web, con las mismas tres zonas y en el mismo orden: la
marca a la izquierda, la memoria abierta con sus tres acciones al lado, y a la
derecha si el motor responde, refrescar y el tema.

## El punto del motor y el selector contestan preguntas distintas

El punto verde dice **si la aplicación respira**; el selector dice **con qué
datos está trabajando**. Son las dos cosas que hay que saber antes de creerse
nada de lo que hay debajo, y por eso viven arriba y a la vista, no dentro de
una pantalla a la que hay que entrar.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from lightrag.api.bimnemo.nativo import iconos, tema
from lightrag.api.bimnemo.nativo.actualizar import BotonActualizar
from lightrag.api.bimnemo.nativo.memorias import Memorias
from lightrag.api.bimnemo.nativo.motor import PIDE_CLAVE, Motor
from lightrag.api.bimnemo.nativo.piezas import insignia, pintar_insignia


#: Ancho del selector de memoria.
ANCHO_SELECTOR = 250

#: Por debajo de este ancho de ventana se esconde el lema. El selector va
#: centrado de verdad, así que lo que ocupa la marca lo pierde el hueco de los
#: dos lados: con el lema a la vista y la ventana en su mínimo, el selector
#: ancho se montaba sobre «Actualizar».
ANCHO_SIN_LEMA = 1180


class BarraSuperior(QFrame):
    """La barra, con todo lo que no pertenece a ninguna pantalla."""

    #: Alguien ha pedido releer los datos de todas las pantallas.
    refrescar = Signal()
    #: Alguien ha pedido cambiar entre claro y oscuro.
    tema_alternado = Signal()

    def __init__(
        self, motor: Motor, memorias: Memorias, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.motor = motor
        self.memorias = memorias

        self.setObjectName("barra")
        self.setFixedHeight(tema.ALTO_BARRA)

        # Tres celdas y no una fila con espaciadores: la memoria abierta va
        # centrada **en la barra**, no a medio camino entre la marca y las
        # acciones. Con un espaciador a cada lado, el grupo se movería cada
        # vez que cambiara el ancho de un vecino —y el nombre de la memoria
        # cambia de ancho al cambiar de memoria—. Las columnas de los lados
        # llevan el mismo peso, así que el centro es el centro de verdad.
        rejilla = QGridLayout(self)
        rejilla.setContentsMargins(16, 0, 16, 0)
        rejilla.setSpacing(10)
        rejilla.setColumnStretch(0, 1)
        rejilla.setColumnStretch(2, 1)

        rejilla.addWidget(self._marca(), 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        rejilla.addWidget(self._memorias(), 0, 1, Qt.AlignHCenter | Qt.AlignVCenter)
        rejilla.addWidget(self._acciones(), 0, 2, Qt.AlignRight | Qt.AlignVCenter)

        self.memorias.listado.connect(self.pintar_selector)
        self.motor.caido.connect(self._motor_caido)

    # -- zonas --------------------------------------------------------------

    def _marca(self) -> QWidget:
        caja_exterior = QWidget()
        caja_exterior.setObjectName("fila")
        fila = QHBoxLayout(caja_exterior)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)

        self.marca = QLabel()
        self.marca.setObjectName("marca")
        self.marca.setFixedSize(28, 28)
        self.marca.setPixmap(iconos.marca(28))
        self.marca.setAlignment(Qt.AlignCenter)
        fila.addWidget(self.marca)

        nombre = QLabel("BIMNEMO")
        nombre.setObjectName("nombre")
        fila.addWidget(nombre)

        self.lema = QLabel("Memoria de conocimiento")
        self.lema.setObjectName("lema")
        fila.addWidget(self.lema)
        return caja_exterior

    def _memorias(self) -> QWidget:
        grupo = QFrame()
        grupo.setObjectName("grupo-nemo")
        caja = QHBoxLayout(grupo)
        caja.setContentsMargins(5, 4, 5, 4)
        caja.setSpacing(4)

        self.selector = QComboBox()
        # Ancho de sobra para leer el nombre entero: es lo que dice con qué
        # datos se está trabajando, y cortado a media palabra no lo dice.
        self.selector.setMinimumWidth(ANCHO_SELECTOR)
        self.selector.setFixedHeight(30)
        self.selector.setToolTip("Memoria abierta")
        # `activated` y no `currentIndexChanged`: el primero solo salta cuando
        # lo elige una persona. El segundo salta también al repintar la lista,
        # y eso es un bucle — repintar, «cambiar», repintar.
        self.selector.activated.connect(self._elegida)
        caja.addWidget(self.selector)

        self.boton_nueva = self._boton(
            "acercar", "Crear una memoria nueva", principal=True
        )
        self.boton_nueva.clicked.connect(lambda: self.memorias.crear(self))
        caja.addWidget(self.boton_nueva)

        self.boton_renombrar = self._boton("editar", "Renombrar la memoria abierta")
        self.boton_renombrar.clicked.connect(lambda: self.memorias.renombrar(self))
        caja.addWidget(self.boton_renombrar)

        self.boton_borrar = self._boton("borrar", "Borrar la memoria abierta")
        self.boton_borrar.clicked.connect(lambda: self.memorias.borrar(self))
        caja.addWidget(self.boton_borrar)
        return grupo

    def _acciones(self) -> QWidget:
        caja_exterior = QWidget()
        caja_exterior.setObjectName("fila")
        fila = QHBoxLayout(caja_exterior)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)

        # Escondido hasta que haya una versión nueva; entonces parpadea.
        self.boton_actualizar = BotonActualizar()
        fila.addWidget(self.boton_actualizar, 0, Qt.AlignVCenter)

        self.estado_motor = insignia(
            "Comprobando…", tema.ACTUAL.texto_3, tema.ACTUAL.secundaria, punto=True
        )
        # Con alto propio: una etiqueta suelta en la barra se estira hasta
        # los 56 píxeles de alto y la insignia deja de parecer una insignia.
        self.estado_motor.setFixedHeight(24)
        fila.addWidget(self.estado_motor, 0, Qt.AlignVCenter)

        self.boton_refrescar = self._boton("recargar", "Releer los datos del motor")
        self.boton_refrescar.clicked.connect(self.refrescar.emit)
        fila.addWidget(self.boton_refrescar)

        self.boton_tema = self._boton("claro", "Cambiar entre claro y oscuro")
        self.boton_tema.clicked.connect(self.tema_alternado.emit)
        fila.addWidget(self.boton_tema)
        return caja_exterior

    def resizeEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        super().resizeEvent(evento)
        self.lema.setVisible(self.width() >= ANCHO_SIN_LEMA)

    def _boton(self, icono: str, pista: str, principal: bool = False) -> QPushButton:
        boton = QPushButton()
        boton.setObjectName("principal-icono" if principal else "icono")
        iconos.poner(boton, icono, 15, "sobre_azul" if principal else "texto_2")
        boton.setToolTip(pista)
        boton.setCursor(Qt.PointingHandCursor)
        boton.setFixedSize(32, 30)
        return boton

    # -- memoria activa -----------------------------------------------------

    def pintar_selector(self) -> None:
        """Rehace la lista de memorias dejando marcada la abierta.

        Solo el nombre. Antes la de por defecto llevaba un `·` detrás, que en
        el selector se leía como parte del nombre. Cuál es la de por defecto
        lo sigue diciendo su rótulo emergente, que es donde se busca.
        """
        self.selector.blockSignals(True)
        self.selector.clear()
        for nemo in self.memorias.nemos:
            identificador = str(nemo.get("id", ""))
            self.selector.addItem(str(nemo.get("name", "")), identificador)
            if identificador == self.memorias.por_defecto:
                self.selector.setItemData(
                    self.selector.count() - 1,
                    "Es la memoria por defecto: la que se abre al arrancar",
                    Qt.ToolTipRole,
                )
        # Sin ninguna memoria —instalación nueva, o después de borrar la
        # última— el selector lo dice en vez de quedarse en blanco, y no hay
        # nada que renombrar ni que borrar.
        hay = bool(self.memorias.nemos)
        if not hay:
            self.selector.addItem("Sin memorias", None)
        self.selector.setEnabled(hay)
        self.boton_renombrar.setEnabled(hay)
        self.boton_borrar.setEnabled(hay)

        indice = self.selector.findData(self.memorias.actual)
        if indice >= 0 and hay:
            self.selector.setCurrentIndex(indice)
        self.selector.blockSignals(False)

    def _elegida(self, indice: int) -> None:
        self.memorias.elegir(str(self.selector.itemData(indice) or ""))

    # -- estado del motor ---------------------------------------------------

    def comprobar_motor(self) -> None:
        """Pregunta al motor si está vivo. Es `GET /health`, como la web."""
        self.motor.get("/health", self._motor_contesto, self._motor_fallo)

    def _motor_contesto(self, datos: Any) -> None:
        estado = ""
        if isinstance(datos, dict):
            estado = str(datos.get("status") or "").lower()
        if estado in ("healthy", "ok"):
            self._pintar_motor("Motor activo", "#10b981", "rgba(16, 185, 129, 0.12)")
        else:
            self._pintar_motor(
                f"Motor: {estado or 'sin estado'}",
                "#f59e0b",
                "rgba(245, 158, 11, 0.12)",
            )

    def _motor_fallo(self, motivo: str) -> None:
        texto = "Requiere clave" if motivo == PIDE_CLAVE else "Motor no disponible"
        self._pintar_motor(texto, "#ef4444", "rgba(239, 68, 68, 0.12)", motivo)

    def _motor_caido(self, motivo: str) -> None:
        """Cualquier petición que se quede sin motor lo dice aquí.

        Es el único sitio donde se enseña: seis pantallas avisando por su
        cuenta de lo mismo serían seis avisos por un solo problema.
        """
        self._pintar_motor(
            "Motor no disponible", "#ef4444", "rgba(239, 68, 68, 0.12)", motivo
        )

    def _pintar_motor(
        self, texto: str, color: str, fondo: str, pista: str = ""
    ) -> None:
        pintar_insignia(self.estado_motor, texto, color, fondo, punto=True)
        self.estado_motor.setToolTip(pista or texto)

    # -- tema ---------------------------------------------------------------

    def retematizar(self) -> None:
        """Vuelve a teñir lo que no se pinta con la hoja de estilo."""
        iconos.retenir(self)
        # El botón enseña adónde va, no dónde está: con el tema oscuro
        # puesto, el sol es la salida.
        oscuro = tema.ACTUAL is tema.OSCURO
        iconos.poner(self.boton_tema, "claro" if oscuro else "oscuro", 15)
        self.boton_tema.setToolTip(
            "Cambiar al tema claro" if oscuro else "Cambiar al tema oscuro"
        )
        self.comprobar_motor()


__all__ = ["BarraSuperior"]
