"""Pantalla «API»: cómo conectar cualquier IA a esta memoria.

Los mismos paneles que la interfaz web y en su orden: la dirección, los
endpoints por ámbito —esta memoria, todas las memorias, el motor—, los
ejemplos, la instrucción para un agente, los modos de recuperación y el
acceso.

## Las rutas siguen a la memoria abierta

Cambiar de memoria **cambia los endpoints que se enseñan**. No es cosmética:
con «Obra Sur» abierta, copiar `/bimnemo/memory/search` lee la memoria por
defecto. Funciona al pegarlo y devuelve lo que no es, que es peor que
fallar. Quien resuelve cada ruta es `api_rutas`.

## Los endpoints van en tabla, no en fichas

Cuatro columnas —acción, ruta, para qué sirve y copiar— que mandan sobre
todas las filas del ámbito. Antes cada endpoint repartía su ancho a su aire
y llevaba debajo su cuerpo JSON: doce bloques amontonados en los que había
que leerlo todo para encontrar uno. El cuerpo no se ha perdido, está en lo
que copia el botón y en su globo de ayuda.

## Swagger y ReDoc se abren fuera

La ventana nativa no lleva motor web —esa fue justo la decisión que la hizo
nativa—, así que no puede pintar Swagger dentro. Las solapas están y lo
abren en el navegador. Fingir que están dentro sería mentir sobre lo que se
puede hacer aquí.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.manifiesto import AMBITOS, ENDPOINTS, MODOS
from lightrag.api.bimnemo.nativo import (
    api_acceso,
    api_piezas,
    api_rutas,
    api_textos,
    iconos,
)
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Pantalla, Tarjeta

#: Las tres solapas, con lo que abre cada una. La «Guía» es esta pantalla.
SOLAPAS = (("Guía", ""), ("Swagger", "/docs"), ("ReDoc", "/redoc"))

#: Qué se dice a la derecha del título de cada ámbito. Sin esto, «Todas las
#: memorias» y «El motor» se leen como si también dependieran de cuál esté
#: abierta, que es justo lo contrario de lo que significan.
NOTA_AMBITO = {
    "todas": "Sin importar cuál esté abierta",
    "motor": "LightRAG por debajo",
}


class PantallaApi(Pantalla):
    def __init__(self, motor: Motor) -> None:
        super().__init__(
            "API",
            "Conecta cualquier IA a esta memoria. Todo lo que hace BIMNEMO "
            "se puede hacer desde aquí.",
        )
        self.motor = motor
        self.base = motor.base
        self._memoria = motor.memoria
        self._paneles: list = []
        self._instruccion = ""

        self.aviso = Aviso()
        self.anadir(self._encabezado())
        self.anadir(self.aviso)
        self.anadir(self._direccion())

        # Las tablas se rehacen al cambiar de memoria, así que van en su
        # propio contenedor y no sueltas en la pantalla.
        zona = QWidget()
        zona.setObjectName("fila")
        self.caja_endpoints = QVBoxLayout(zona)
        self.caja_endpoints.setContentsMargins(0, 0, 0, 0)
        self.caja_endpoints.setSpacing(16)
        self.anadir(zona)

        self.curl = self._ficha_de_codigo("Ejemplo — curl")
        self.python = self._ficha_de_codigo("Ejemplo — Python")
        self.agente = self._ficha_de_codigo(
            "Instrucción para un agente", alto=260, icono="conversacion"
        )

        self.anadir(self._modos())

        self.acceso = api_acceso.PanelAcceso(motor)
        self.acceso.cambiada.connect(self._refrescar_ejemplos)
        self.anadir(self.acceso)
        self.cerrar_con_espacio()

        self.refrescar()

    # -- encabezado ---------------------------------------------------------

    def _encabezado(self) -> QWidget:
        caja = QWidget()
        caja.setObjectName("fila")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)
        fila.addStretch(1)

        copiar = QPushButton("  Copiar para la IA")
        copiar.setObjectName("principal")
        copiar.setIcon(iconos.icono("copiar", 14, "#ffffff"))
        copiar.setCursor(Qt.PointingHandCursor)
        copiar.setToolTip(
            "Todo lo que una IA necesita para usar esta memoria: la "
            "dirección, los endpoints ya resueltos y cómo llamarlos."
        )
        copiar.clicked.connect(lambda: self._copiado(self._instruccion))
        fila.addWidget(copiar)

        self.solapas = api_piezas.Pestanas(tuple(n for n, _r in SOLAPAS))
        self.solapas.elegida.connect(self._abrir_solapa)
        fila.addWidget(self.solapas)
        return caja

    def _abrir_solapa(self, nombre: str) -> None:
        for rotulo, ruta in SOLAPAS:
            if rotulo != nombre or not ruta:
                continue
            QDesktopServices.openUrl(QUrl(f"{self.base}{ruta}"))
            self.aviso.informar(
                f"{nombre} se ha abierto en tu navegador: {self.base}{ruta}"
            )
            return
        self.aviso.callar()

    # -- paneles ------------------------------------------------------------

    def _direccion(self) -> QWidget:
        panel = api_piezas.Panel("Dirección de la memoria", "entidades")
        self.panel_direccion = panel

        panel.anadir(
            api_piezas.fila_con_boton(
                self.base, "Copiar", lambda: self._copiado(self.base)
            )
        )

        nota = QLabel(
            "Escucha solo en esta máquina. Cualquier programa de este "
            "ordenador puede usarla; nada de fuera llega."
        )
        nota.setObjectName("descripcion")
        nota.setWordWrap(True)
        panel.anadir(nota)
        return panel

    def _pintar_endpoints(self) -> None:
        """Rehace las tablas con las rutas de la memoria abierta."""
        while self.caja_endpoints.count():
            viejo = self.caja_endpoints.takeAt(0)
            if viejo.widget():
                viejo.widget().deleteLater()

        self._paneles = api_rutas.por_ambito(ENDPOINTS, self._memoria, AMBITOS)
        for clave, titulo, filas in self._paneles:
            nota = NOTA_AMBITO.get(clave, self._memoria or "General")
            panel = api_piezas.Panel(titulo, "api", nota)
            panel.anadir(api_piezas.Tabla(filas, self.base))
            self.caja_endpoints.addWidget(panel)

    def _ficha_de_codigo(
        self, titulo: str, alto: int = 0, icono: str = "code"
    ) -> QPlainTextEdit:
        """Una ficha con su código dentro y el botón de copiar en la cabecera.

        El botón va **arriba**, no debajo del bloque: es donde lo busca quien
        ya ha leído el título y solo quiere llevárselo. Al final del bloque
        hay que desplazarse para encontrarlo.
        """
        panel = api_piezas.Panel(titulo, icono, boton="Copiar")

        caja = QPlainTextEdit()
        caja.setObjectName("codigo")
        caja.setReadOnly(True)
        caja.setLineWrapMode(QPlainTextEdit.NoWrap)
        if alto:
            caja.setFixedHeight(alto)
        panel.anadir(caja)

        if panel.boton is not None:
            panel.boton.clicked.connect(
                lambda _m=False, c=caja: self._copiado(c.toPlainText())
            )
        self.anadir(panel)
        # El alto se ajusta al contenido salvo que se haya fijado: un bloque
        # de seis líneas con la altura por defecto de Qt sale con barra de
        # desplazamiento y media línea cortada.
        caja.ajustar = None if alto else self._ajustador(caja)  # type: ignore[attr-defined]
        return caja

    @staticmethod
    def _ajustador(caja: QPlainTextEdit) -> Callable[[], None]:
        """Deja el bloque a la altura de lo que lleva dentro.

        Se cuenta todo lo que ocupa sitio y no es texto: los márgenes del
        documento, el relleno que le pone la hoja de estilo y **la barra
        horizontal**. Un `curl` no cabe de ancho en ninguna pantalla, así que
        esa barra siempre aparece; sin reservarle su hueco se comía la última
        línea del ejemplo, que es justo la que lleva la pregunta.
        """

        def ajustar() -> None:
            lineas = caja.document().blockCount()
            alto = caja.fontMetrics().lineSpacing() * lineas
            alto += 2 * int(caja.document().documentMargin()) + 20
            alto += caja.horizontalScrollBar().sizeHint().height()
            caja.setFixedHeight(min(int(alto), 420))

        return ajustar

    def _modos(self) -> QWidget:
        panel = api_piezas.Panel(
            "Modos de recuperación", "trozos", 'El campo "mode" de las consultas'
        )
        tarjeta = Tarjeta()
        for nombre, explicacion in MODOS.items():
            tarjeta.dato(nombre, explicacion)
        panel.anadir(tarjeta)
        return panel

    # -- datos --------------------------------------------------------------

    def refrescar(self) -> None:
        self._memoria = self.motor.memoria
        self._pintar_endpoints()
        self._refrescar_ejemplos()
        self.acceso.refrescar()

    def cambiar_memoria(self, nemo: str) -> None:
        """La ventana llama a esto al cambiar de memoria."""
        if nemo == self._memoria:
            return
        self._memoria = nemo
        self._pintar_endpoints()
        self._refrescar_ejemplos()

    def showEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        """Al volver a la pantalla, seguir a la memoria que haya activa.

        El cambio de memoria se hace desde la barra de arriba, que no sabe
        de esta pantalla. Comprobarlo al mostrarse cuesta nada y evita
        enseñar rutas de la memoria anterior.
        """
        super().showEvent(evento)
        self.cambiar_memoria(self.motor.memoria)

    def _refrescar_ejemplos(self, _clave: str = "") -> None:
        """Rehace los tres bloques. Lleva dentro la clave si la hay.

        Con la API protegida se escribe **la de verdad**, no un hueco que
        rellenar: el botón de copiar tiene que entregar algo que funcione al
        pegarlo. Ese es el sentido de proteger y compartir.
        """
        clave = self.motor.clave
        rutas = api_rutas.de_memoria(ENDPOINTS, self._memoria)

        self.curl.setPlainText(api_textos.ejemplo_curl(self.base, rutas, clave))
        self.python.setPlainText(
            api_textos.ejemplo_python(self.base, rutas, clave)
        )
        self._instruccion = api_textos.instrucciones(
            self.base, self._memoria, self._paneles, MODOS, clave
        )
        self.agente.setPlainText(self._instruccion)

        for caja in (self.curl, self.python):
            if caja.ajustar:  # type: ignore[attr-defined]
                caja.ajustar()  # type: ignore[attr-defined]

    # -- copiar -------------------------------------------------------------

    def _copiado(self, texto: str) -> None:
        api_piezas.al_portapapeles(texto)
        self.aviso.acertar("Copiado al portapapeles.")
