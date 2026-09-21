"""Reiniciar el motor sin que parezca que la aplicación se ha colgado.

El reinicio tarda unos cuatro segundos —medido sobre 148 reinicios: mínimo
3,46 s, mediana 4,00 s, máximo 4,81 s— y durante ese rato el motor no
contesta. Sin nada en pantalla, cuatro segundos de silencio se leen como un
programa muerto.

## Cómo se sabe que el motor ya volvió

**No vale preguntar por `/health`.** El proceso que se está muriendo sigue
contestando un rato: medido, `/health` decía que sí 5,7 segundos antes de que
el motor nuevo estuviera listo, y la interfaz se recargaba contra un cadáver.

Se mira el `boot_id` de `/bimnemo/app-build`, que es un identificador
distinto por cada proceso. Un `boot_id` distinto del de antes **demuestra**
que quien contesta es otro proceso. No hay que adivinar nada.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from lightrag.api.bimnemo.nativo.motor import Motor

#: Cada cuánto se pregunta si ya volvió.
SONDEO_MS = 400

#: Cuánto se espera antes de rendirse. Generoso: el peor reinicio medido son
#: 4,8 segundos, pero un ordenador cargado puede tardar bastante más y es
#: mejor esperar de más que decir que falló algo que estaba a punto de salir.
PLAZO_MS = 60_000


class Reinicio(QObject):
    """Pide el reinicio y avisa por el camino.

    Se emiten tres señales porque la pantalla necesita las tres cosas: qué
    poner en el cartel, cuánto se lleva esperando y cómo acabó.
    """

    #: Texto para el usuario: «Pidiendo el reinicio…», «Esperando al motor…»
    paso = Signal(str)
    #: Milisegundos transcurridos, para mover la barra.
    avance = Signal(int)
    #: `True` si el motor volvió; si no, `False` y el motivo.
    terminado = Signal(bool, str)

    def __init__(self, motor: Motor, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.motor = motor
        self._boot_anterior: Optional[str] = None
        self._transcurrido = 0
        #: Parar el reloj no basta para dejar de terminar.
        #:
        #: Se sondea cada 400 ms sin esperar a que conteste el sondeo
        #: anterior, así que cuando uno descubre que el motor volvió hay
        #: otros ya en vuelo. Cada uno de ellos llegaba después y anunciaba
        #: el final otra vez: medido, **once veces** en un reinicio. La
        #: pantalla lo aguantaba, pero recargaba los datos once veces y
        #: habría vuelto a habilitar botones a destiempo.
        self._acabado = False
        self._reloj = QTimer(self)
        self._reloj.setInterval(SONDEO_MS)
        self._reloj.timeout.connect(self._mirar)

    def arrancar(self) -> None:
        """Empieza: primero se apunta quién contesta ahora."""
        self._transcurrido = 0
        self._acabado = False
        self.paso.emit("Comprobando el motor…")
        self.motor.get(
            "/bimnemo/app-build",
            self._apuntar_y_pedir,
            lambda _motivo: self._apuntar_y_pedir(None),
        )

    def _apuntar_y_pedir(self, datos: object) -> None:
        if isinstance(datos, dict):
            self._boot_anterior = datos.get("boot_id")
        self.paso.emit("Pidiendo el reinicio…")
        self.motor.post("/bimnemo/restart", {}, self._pedido, self._no_pudo)

    def _pedido(self, _datos: object) -> None:
        self.paso.emit("Esperando a que el motor vuelva…")
        self._reloj.start()

    def _terminar(self, bien: bool, motivo: str) -> None:
        """Anuncia el final **una sola vez**."""
        if self._acabado:
            return
        self._acabado = True
        self._reloj.stop()
        self.terminado.emit(bien, motivo)

    def _no_pudo(self, motivo: str) -> None:
        # El caso corriente es 409: el motor está indexando y se niega a
        # cortarse a mitad. Eso no es un fallo, es lo correcto, y el mensaje
        # que llega del motor ya lo explica.
        self._terminar(False, motivo)

    def _mirar(self) -> None:
        if self._acabado:
            return
        self._transcurrido += SONDEO_MS
        self.avance.emit(self._transcurrido)

        if self._transcurrido >= PLAZO_MS:
            self._terminar(
                False,
                "El motor no ha vuelto en un minuto. Cierra BIMNEMO y "
                "vuelve a abrirlo.",
            )
            return

        self.motor.get(
            "/bimnemo/app-build",
            self._comprobar,
            # Que no conteste es lo **normal** mientras reinicia: no es un
            # fallo, es la parte de en medio. Se sigue esperando.
            lambda _motivo: None,
        )

    def _comprobar(self, datos: object) -> None:
        if not isinstance(datos, dict):
            return
        actual = datos.get("boot_id")
        if not actual:
            return
        if self._boot_anterior is not None and actual == self._boot_anterior:
            # Sigue contestando el de antes, el que se está muriendo.
            return

        self._terminar(True, "")


def conectar_barra(
    reinicio: Reinicio,
    poner_texto: Callable[[str], None],
    poner_avance: Callable[[int, int], None],
) -> None:
    """Enchufa un reinicio a un cartel y una barra.

    La barra va por tiempo y no por progreso real, porque progreso real no
    hay: el motor no informa de por dónde va su arranque. Se marca el tope en
    el peor reinicio medido, así que casi siempre termina antes de llenarse,
    que es mucho mejor que al revés.
    """
    tope = 5_000
    reinicio.paso.connect(poner_texto)
    reinicio.avance.connect(lambda ms: poner_avance(min(ms, tope), tope))
