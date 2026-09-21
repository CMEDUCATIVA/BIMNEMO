"""La primera vez: crear la memoria y elegir el modelo, en un solo paso.

Una instalación nueva abría en un Panel vacío, con una memoria llamada
«General» que nadie había creado y sin modelo configurado. Subir un documento
en ese estado fallaba al indexar, y el motivo —falta la clave— estaba en otra
pantalla. Esto lo pide todo junto y al principio: el nombre de la memoria, el
modelo de lenguaje y los embeddings.

## Cuándo sale

Cuando no hay ninguna memoria: una instalación nueva, o después de borrar la
última. También con la «General» de fábrica vacía, que es como quedaban las
instalaciones de antes de que la base pudiera ocultarse. En cuanto hay
documentos, o una memoria con nombre, no sale: preguntar «¿cómo se llama tu
primera memoria?» a quien ya lleva meses usándolo sería absurdo.

## La primera memoria es la base, con el nombre que se elija

El motor necesita un espacio de trabajo por defecto, así que la memoria base
existe siempre, aunque oculta. Ponerle nombre es lo que la hace aparecer: no
se crea otra al lado, y no queda ninguna «General» colgando en el selector.
El identificador no cambia —renombrar solo toca el rótulo—, así que no se
mueve ningún fichero.

## «Ahora no» y no «Salir»

Cierra el cuadro y deja usar la aplicación: quien solo quiere echar un
vistazo no tiene por qué configurar nada. Mientras siga siendo nueva, el
cuadro vuelve en el siguiente arranque. Cerrar el programa entero castigaría
justo a quien está decidiendo si lo quiere.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo import tema
from lightrag.api.bimnemo.nativo.memorias import Memorias
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.pantalla_configuracion import SECCIONES, Seccion
from lightrag.api.bimnemo.nativo.piezas import Aviso
from lightrag.api.bimnemo.nativo.reinicio import Reinicio, conectar_barra

#: El nombre con el que viene de fábrica la memoria por defecto. Es el de
#: `nemo_registry.LEGACY_NAME`; se repite aquí para no cargar el registro del
#: motor en la ventana.
NOMBRE_DE_FABRICA = "General"

#: Cuánto se difumina lo que queda detrás.
RADIO_DIFUMINADO = 22

#: Las dos tarjetas que se piden. El reordenado es opcional y se queda en
#: Configuración: en el primer arranque, cada campo de más es una razón más
#: para cerrar el cuadro sin hacer nada.
PEDIDAS = ("llm", "embedding")


def es_nueva(nemos: list[dict[str, Any]], archivos: int) -> bool:
    """¿Es una instalación sin estrenar?

    Sin ninguna memoria a la vista, o con la de fábrica, con su nombre de
    fábrica y sin archivos.
    """
    if not nemos:
        return True
    if len(nemos) != 1:
        return False
    unica = nemos[0]
    return (
        str(unica.get("id") or "") == ""
        and str(unica.get("name") or "") == NOMBRE_DE_FABRICA
        and archivos == 0
    )


def difuminar(foto: QPixmap, radio: int = RADIO_DIFUMINADO) -> QPixmap:
    """Una copia desenfocada de la foto, del mismo tamaño.

    Qt no tiene un desenfoque de imágenes suelto: lo tiene como efecto de la
    escena gráfica. Se monta una escena de un solo elemento, se le aplica y se
    pinta sobre una imagen nueva.
    """
    escena = QGraphicsScene()
    elemento = QGraphicsPixmapItem(foto)
    efecto = QGraphicsBlurEffect()
    efecto.setBlurRadius(radio)
    efecto.setBlurHints(QGraphicsBlurEffect.QualityHint)
    elemento.setGraphicsEffect(efecto)
    escena.addItem(elemento)

    ancho, alto = foto.width(), foto.height()
    imagen = QImage(ancho, alto, QImage.Format_ARGB32_Premultiplied)
    imagen.fill(Qt.transparent)
    pintor = QPainter(imagen)
    escena.render(pintor, QRectF(0, 0, ancho, alto), QRectF(0, 0, ancho, alto))
    pintor.end()

    resultado = QPixmap.fromImage(imagen)
    resultado.setDevicePixelRatio(foto.devicePixelRatio())
    return resultado


class Bienvenida(QWidget):
    """El cuadro flotante, con la ventana desenfocada detrás.

    Es un hijo de la ventana que la cubre entera, no un `QDialog`: un diálogo
    es otra ventana del sistema, con su propia barra de título, y no puede
    desenfocar lo que tiene detrás. Esto sí.
    """

    #: Se emite al terminar bien: la memoria tiene nombre y el motor, modelo.
    terminada = Signal()

    def __init__(self, ventana: QWidget, motor: Motor, memorias: Memorias) -> None:
        super().__init__(ventana)
        self.ventana = ventana
        self.motor = motor
        self.memorias = memorias
        self._fondo: Optional[QPixmap] = None
        self._trabajo: Optional[Reinicio] = None
        self.secciones: dict[str, Seccion] = {}
        #: Si en la última lista había alguna memoria. Sirve para volver a
        #: salir al borrar la última, pero no cada vez que la ventana relee
        #: una lista que ya estaba vacía: quien dijo «Ahora no» lo dijo.
        self._habia: Optional[bool] = None
        # La lista puede haber llegado ya: con un motor que contesta
        # enseguida, antes de que este cuadro exista.
        if memorias.nemos:
            self._habia = True
        memorias.listado.connect(self._lista_nueva)

        fuera = QVBoxLayout(self)
        fuera.setContentsMargins(24, 24, 24, 24)
        fuera.addStretch(1)
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(self._tarjeta())
        fila.addStretch(1)
        fuera.addLayout(fila)
        fuera.addStretch(1)

        ventana.installEventFilter(self)
        self.hide()

    # -- estructura ---------------------------------------------------------

    def _tarjeta(self) -> QFrame:
        tarjeta = QFrame()
        tarjeta.setObjectName("bienvenida")
        # Ancho fijo por abajo: con el que Qt calcula solo, las dos tarjetas
        # quedaban tan estrechas que los desplegables cortaban el nombre del
        # proveedor —«OpenAI (Ch»— y del modelo.
        tarjeta.setMinimumWidth(880)
        tarjeta.setMaximumWidth(1000)
        columna = QVBoxLayout(tarjeta)
        columna.setContentsMargins(28, 24, 28, 22)
        columna.setSpacing(12)

        titulo = QLabel("Crea tu primera memoria")
        titulo.setObjectName("titulo")
        columna.addWidget(titulo)

        texto = QLabel(
            "Una memoria guarda los documentos de un proyecto y lo que BIMNEMO "
            "aprende de ellos. Ponle nombre y elige el modelo de IA que los va "
            "a leer."
        )
        texto.setObjectName("descripcion")
        texto.setWordWrap(True)
        columna.addWidget(texto)

        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText("Nombre de la memoria, p. ej. «Obra Norte»")
        self.nombre.setMaxLength(60)
        self.nombre.returnPressed.connect(self._guardar)
        columna.addWidget(self.nombre)

        columna.addWidget(self._modelos(), 1)

        self.aviso = Aviso()
        columna.addWidget(self.aviso)

        self.barra = QProgressBar()
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(6)
        self.barra.hide()
        columna.addWidget(self.barra)

        columna.addWidget(self._botones())
        return tarjeta

    def _modelos(self) -> QWidget:
        """Las dos tarjetas de Configuración, las mismas y no una copia.

        En un desplazable: en una ventana baja, las dos tarjetas y los
        botones no caben, y un botón de guardar fuera de la pantalla es un
        cuadro del que no se puede salir más que cerrándolo.
        """
        dentro = QWidget()
        dentro.setObjectName("fila")
        fila = QHBoxLayout(dentro)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(14)
        for clave, titulo, explicacion in SECCIONES:
            if clave not in PEDIDAS:
                continue
            seccion = Seccion(clave, titulo, explicacion)
            self.secciones[clave] = seccion
            # Arriba: con explicaciones de distinto largo, centradas quedaban
            # a alturas distintas y las filas no se correspondían.
            fila.addWidget(seccion, 1, Qt.AlignTop)

        desplazable = QScrollArea()
        desplazable.setObjectName("conversacion")
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desplazable.setWidget(dentro)
        desplazable.setMinimumHeight(390)
        return desplazable

    def _botones(self) -> QWidget:
        caja = QWidget()
        caja.setObjectName("fila")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(0, 4, 0, 0)
        fila.setSpacing(10)
        fila.addStretch(1)

        self.boton_luego = QPushButton("Ahora no")
        self.boton_luego.setCursor(Qt.PointingHandCursor)
        self.boton_luego.setToolTip(
            "Cierra este cuadro. Volverá a salir la próxima vez que abras "
            "BIMNEMO, mientras no haya ninguna memoria creada."
        )
        self.boton_luego.clicked.connect(self.cerrar)
        fila.addWidget(self.boton_luego)

        self.boton_guardar = QPushButton("Crear memoria y guardar")
        self.boton_guardar.setObjectName("principal")
        self.boton_guardar.setCursor(Qt.PointingHandCursor)
        self.boton_guardar.clicked.connect(self._guardar)
        fila.addWidget(self.boton_guardar)
        return caja

    # -- aparecer y desaparecer ---------------------------------------------

    def comprobar(self) -> None:
        """Pregunta al motor si esto está sin estrenar y, si lo está, sale."""

        def memorias(datos: Any) -> None:
            if not isinstance(datos, dict):
                return
            nemos = list(datos.get("nemos") or [])
            if not nemos:
                self.mostrar()
                return
            if len(nemos) != 1:
                return
            self.motor.get(
                "/bimnemo/stats", lambda stats: archivos(nemos, stats), None
            )

        def archivos(nemos: list[dict[str, Any]], stats: Any) -> None:
            total = 0
            if isinstance(stats, dict):
                total = int((stats.get("storage") or {}).get("total_files") or 0)
            if es_nueva(nemos, total):
                self.mostrar()

        self.motor.get("/bimnemo/nemos", memorias, None)

    def _lista_nueva(self) -> None:
        """Al borrar la última memoria, el cuadro vuelve."""
        hay = bool(self.memorias.nemos)
        if self._habia and not hay and self.isHidden():
            self.mostrar()
        self._habia = hay

    def mostrar(self) -> None:
        # Limpio cada vez: al volver tras borrar la última memoria traía el
        # nombre de la anterior y el último mensaje del reinicio.
        self.nombre.clear()
        self.aviso.callar()
        self.barra.hide()
        self._fotografiar()
        # Lo de detrás no se puede tocar mientras el cuadro esté: se pintaría
        # encima de una pantalla que sigue viva por debajo.
        central = self._central()
        if central is not None:
            central.setEnabled(False)
        self.setGeometry(self.ventana.rect())
        self.show()
        self.raise_()
        self.nombre.setFocus()
        self.motor.get("/bimnemo/providers", self._poner_catalogo, None)

    def cerrar(self) -> None:
        central = self._central()
        if central is not None:
            central.setEnabled(True)
        self.hide()

    def _central(self) -> Optional[QWidget]:
        dame = getattr(self.ventana, "centralWidget", None)
        return dame() if callable(dame) else None

    def _fotografiar(self) -> None:
        """La foto desenfocada de lo que hay detrás.

        Se fotografía el contenido central y no la ventana: este cuadro es
        hijo de la ventana, no del contenido, así que no sale en su propia
        foto.
        """
        central = self._central()
        if central is None or central.width() == 0:
            self._fondo = None
            return
        self._fondo = difuminar(central.grab())

    # -- pintar -------------------------------------------------------------

    def paintEvent(self, _evento) -> None:  # noqa: N802 (nombre de Qt)
        pintor = QPainter(self)
        if self._fondo is not None:
            pintor.drawPixmap(self.rect(), self._fondo)
        # Un velo del color del fondo encima: el desenfoque solo no basta
        # para que el cuadro se lea como lo único que importa ahora.
        velo = QColor(tema.ACTUAL.fondo)
        velo.setAlpha(150)
        pintor.fillRect(self.rect(), velo)

    def eventFilter(self, objeto, evento) -> bool:  # noqa: N802 (nombre de Qt)
        """Seguir el tamaño de la ventana.

        Un hijo colocado a mano no se entera de que su padre cambia de tamaño:
        sin esto, al agrandar la ventana quedaba una franja sin velo por la
        que se veía —y se podía pulsar— lo de detrás. La foto no se repite:
        se estira, que desenfocada no se nota.
        """
        if objeto is self.ventana and evento.type() == QEvent.Resize:
            self.setGeometry(self.ventana.rect())
        return False

    def keyPressEvent(self, evento: QKeyEvent) -> None:  # noqa: N802
        if evento.key() == Qt.Key_Escape and self.boton_luego.isEnabled():
            self.cerrar()
            return
        super().keyPressEvent(evento)

    # -- datos --------------------------------------------------------------

    def _poner_catalogo(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        for clave, seccion in self.secciones.items():
            seccion.poner_catalogo(datos.get(clave) or [])
        # Los valores después del catálogo: si llegan antes, el desplegable
        # se queda en el primer proveedor de la lista.
        self.motor.get("/bimnemo/settings", self._poner_valores, None)

    def _poner_valores(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        for clave, seccion in self.secciones.items():
            seccion.poner_valores(datos.get(clave) or {})

    # -- guardar ------------------------------------------------------------

    def _que_falta(self) -> str:
        if not self.nombre.text().strip():
            return "Ponle un nombre a la memoria."
        for clave, seccion in self.secciones.items():
            if seccion.falta_clave():
                que = "el modelo de lenguaje" if clave == "llm" else "los embeddings"
                return f"Falta la clave de API de {que}."
        return ""

    def _guardar(self) -> None:
        falta = self._que_falta()
        if falta:
            self.aviso.fallar(falta)
            return

        self._ocupado(True)
        self.aviso.informar("Creando la memoria…")
        # Es la base la que se nombra. Tiene el identificador vacío: se indica
        # por parámetro, porque una cadena vacía no cabe en una ruta.
        self.motor.parchear(
            "/bimnemo/nemos?nemo=",
            {"name": self.nombre.text().strip()},
            lambda _datos: self._guardar_modelos(),
            self._fallo,
        )

    def _guardar_modelos(self) -> None:
        self.aviso.informar("Guardando el modelo…")
        cuerpo = {clave: s.a_peticion() for clave, s in self.secciones.items()}
        self.motor.post(
            "/bimnemo/settings", cuerpo, lambda _datos: self._reiniciar(), self._fallo
        )

    def _reiniciar(self) -> None:
        """El motor lee el modelo al arrancar: sin reiniciar no lo usaría."""
        self.barra.setValue(0)
        self.barra.show()
        self._trabajo = Reinicio(self.motor, self)
        conectar_barra(
            self._trabajo,
            self.aviso.informar,
            lambda hecho, tope: (
                self.barra.setMaximum(tope),
                self.barra.setValue(hecho),
            ),
        )
        self._trabajo.terminado.connect(self._reiniciado)
        self._trabajo.arrancar()

    def _reiniciado(self, bien: bool, motivo: str) -> None:
        self.barra.hide()
        self._ocupado(False)
        if not bien:
            self.aviso.fallar(
                "La memoria y el modelo están guardados, pero el motor no "
                f"volvió: {motivo}. Reinícialo desde la pantalla Motor."
            )
            return
        self.memorias.cargar()
        self.cerrar()
        self.terminada.emit()

    def _fallo(self, motivo: str) -> None:
        self._ocupado(False)
        self.aviso.fallar(motivo)

    def _ocupado(self, si: bool) -> None:
        for control in (self.nombre, self.boton_guardar, self.boton_luego):
            control.setEnabled(not si)
        for seccion in self.secciones.values():
            seccion.setEnabled(not si)


__all__ = ["Bienvenida", "difuminar", "es_nueva"]
