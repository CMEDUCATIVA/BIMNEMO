"""Exigir —o dejar de exigir— una clave para usar la API.

Vive aparte de `pantalla_api.py` por lo mismo que en la web vive aparte de
`apiview.js`: aquella pantalla **enseña** cómo usar la API y esto **cambia
quién puede entrar**, escribiendo el `.env` y reiniciando el motor.

## Por qué el interruptor no aplica nada por sí solo

La clave no la decide la ventana: la decide el motor. El guardia de las rutas
solo existe si `LIGHTRAG_API_KEY` está en el entorno, y eso se lee **al
arrancar**. Así que «activar» significa de verdad: escribir la clave en el
fichero y levantar el motor de nuevo.

Un interruptor que se limitara a guardar dejaría la pantalla diciendo «exige
clave» con el motor abierto de par en par —mintiendo en la dirección
peligrosa— y la clave esperando en el fichero para sorprender al usuario en
el siguiente arranque, fuera de su propia aplicación. Por eso el interruptor
solo descubre un botón que confirma, y el botón hace las tres cosas.

## El orden no es negociable

**Al proteger**: primero esta ventana se queda con la clave, después el
fichero, y al final el reinicio. Si el motor volviera pidiendo una clave que
la ventana no tiene, la aplicación se quedaría mirando 401 en todas las
pantallas.

**Al abrir** se invierte: el motor **sigue pidiendo la clave hasta que
reinicia**, y el propio reinicio es una ruta protegida como las demás. Quitar
la clave de la ventana antes de tiempo deja el reinicio rechazado con un 403,
el motor en pie con la clave vieja y el fichero ya sin ella: nadie podría
volver a reiniciarlo. Se suelta **después**, con el motor nuevo ya en pie.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QWidget,
)

from lightrag.api.bimnemo.nativo import api_piezas
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso
from lightrag.api.bimnemo.nativo.reinicio import Reinicio, conectar_barra

#: Longitud de la clave que se genera, y su alfabeto.
#:
#: Sin parejas que se confundan al copiarlas a mano: nada de `0/O` ni de
#: `1/l/I`. Una clave que se teclea mal es una clave que parece rota.
LARGO_CLAVE = 32
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"

ABIERTA = (
    "Tu memoria está <b>abierta</b>: cualquier programa de este ordenador "
    "puede consultarla, escribir en ella y borrarla sin presentar nada. "
    "Cómodo para conectar tus skills sin configurar."
)
PROTEGIDA = (
    "La API <b>pide una clave</b>. Esta ventana ya la tiene; pégala en las "
    "herramientas a las que quieras dar acceso. Es una credencial: viaja con "
    "el fichero donde la pegues."
)


def clave_nueva() -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(LARGO_CLAVE))


class PanelAcceso(api_piezas.Panel):
    """El interruptor, su confirmación y el reinicio que lo hace verdad."""

    #: La clave que rige ahora —vacía si la API está abierta—. La pantalla la
    #: escucha para rehacer los ejemplos, que la llevan dentro.
    cambiada = Signal(str)

    def __init__(self, motor: Motor) -> None:
        super().__init__("Acceso a la API", "api", "Abierta")
        self.motor = motor
        self._protegida = False
        self._anterior = ""
        self._trabajo: Optional[Reinicio] = None

        self.anadir(self._palanca())

        self.texto = QLabel(ABIERTA)
        self.texto.setObjectName("descripcion")
        self.texto.setTextFormat(Qt.RichText)
        self.texto.setWordWrap(True)
        self.anadir(self.texto)

        self.anadir(self._clave())

        self.aviso = Aviso()
        self.anadir(self.aviso)

        self.barra = QProgressBar()
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(6)
        self.barra.hide()
        self.anadir(self.barra)

        self.anadir(self._confirmar())
        self.refrescar()

    # -- estructura ---------------------------------------------------------

    def _palanca(self) -> QWidget:
        caja = QWidget()
        caja.setObjectName("fila")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)

        self.interruptor = api_piezas.Interruptor()
        self.interruptor.clicked.connect(self._pensarlo)
        fila.addWidget(self.interruptor)

        rotulo = QLabel("Pedir una clave para entrar")
        rotulo.setObjectName("dato-valor")
        fila.addWidget(rotulo, 1)
        return caja

    def _clave(self) -> QWidget:
        self.caja_clave = QWidget()
        self.caja_clave.setObjectName("fila")
        fila = QHBoxLayout(self.caja_clave)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)

        self.campo = QLineEdit()
        self.campo.setReadOnly(True)
        self.campo.setPlaceholderText("Se genera al activar")
        fila.addWidget(self.campo, 1)

        copiar = QPushButton("Copiar clave")
        copiar.setCursor(Qt.PointingHandCursor)
        copiar.clicked.connect(
            lambda: api_piezas.al_portapapeles(self.campo.text())
        )
        fila.addWidget(copiar)

        self.caja_clave.hide()
        return self.caja_clave

    def _confirmar(self) -> QWidget:
        caja = QWidget()
        caja.setObjectName("fila")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addStretch(1)

        self.boton = QPushButton()
        self.boton.setObjectName("principal")
        self.boton.setCursor(Qt.PointingHandCursor)
        self.boton.clicked.connect(self._aplicar)
        self.boton.hide()
        fila.addWidget(self.boton)
        return caja

    # -- estado -------------------------------------------------------------

    def refrescar(self) -> None:
        """Le pregunta al motor **en marcha** si pide clave.

        No se mira el `.env`: ahí está lo que pedirá el próximo arranque, que
        no es lo mismo. Entre guardar y reiniciar son cosas distintas, y ésta
        es la pantalla donde esa diferencia importa.
        """
        self.motor.get("/bimnemo/memory/manifest", self._leido, self._no_leido)

    def _leido(self, datos: Any) -> None:
        texto = ""
        if isinstance(datos, dict):
            texto = str(datos.get("authentication") or "")
        self._pintar(bool(texto) and "sin autenticación" not in texto.lower())

    def _no_leido(self, _motivo: str) -> None:
        # Un 401 es la respuesta correcta de una API protegida a quien no
        # enseña la clave: dice justo lo que se estaba preguntando.
        self._pintar(True)

    def _pintar(self, protegida: bool) -> None:
        self._protegida = protegida
        self.interruptor.setChecked(protegida)
        self.nota.setText("Protegida" if protegida else "Abierta")
        self.texto.setText(PROTEGIDA if protegida else ABIERTA)
        self.caja_clave.setVisible(protegida)
        self.boton.hide()

    def _pensarlo(self) -> None:
        """El interruptor solo descubre el botón: no aplica nada."""
        quiere = self.interruptor.isChecked()
        if quiere == self._protegida:
            self.boton.hide()
            return
        self.boton.setText(
            "Generar clave y reiniciar" if quiere else "Quitar la clave y reiniciar"
        )
        self.boton.show()

    # -- aplicar ------------------------------------------------------------

    def _aplicar(self) -> None:
        self.boton.setEnabled(False)
        if self.interruptor.isChecked():
            self._proteger()
        else:
            self.motor.post(
                "/bimnemo/access",
                {"enabled": False},
                lambda _d: self._reiniciar("Quitando la clave…"),
                self._fallo,
            )

    def _proteger(self) -> None:
        self._anterior = self.motor.clave
        clave = clave_nueva()

        # La ventana primero: si el motor vuelve pidiéndola y ésta no la
        # tiene, la aplicación se queda fuera de su propia memoria.
        self.motor.usar_clave(clave)
        self.campo.setText(clave)
        self.caja_clave.show()
        self.aviso.informar(f"Clave generada: {clave}  ·  cópiala ahora.")

        self.motor.post(
            "/bimnemo/access",
            {"enabled": True, "key": clave},
            lambda _d: self._reiniciar("Guardando la clave…"),
            self._no_se_guardo,
        )

    def _no_se_guardo(self, motivo: str) -> None:
        # No llegó a escribirse: devolver la ventana a como estaba, porque
        # mandar una clave que el motor no conoce rompería cada petición.
        self.motor.usar_clave(self._anterior)
        self.campo.clear()
        self._fallo(motivo)

    def _reiniciar(self, paso: str) -> None:
        self.aviso.informar(paso)
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
        self.boton.setEnabled(True)
        if not bien:
            self.aviso.fallar(motivo)
            return

        if not self.interruptor.isChecked():
            # Ahora sí: el motor nuevo ya está en pie y ya no la pide.
            self.motor.usar_clave("")
            self.campo.clear()
            self.aviso.acertar("La API queda abierta.")
        else:
            self.aviso.acertar("Hecho: la API ya pide la clave.")

        self.cambiada.emit(self.motor.clave)
        self.refrescar()

    def _fallo(self, motivo: str) -> None:
        self.boton.setEnabled(True)
        self.barra.hide()
        self.aviso.fallar(motivo)
