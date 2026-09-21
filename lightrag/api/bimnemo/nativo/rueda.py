"""La rueda del ratón desplaza la página; no cambia los selectores.

Por defecto, en Qt, girar la rueda encima de un desplegable **cambia su
valor**. En Configuración IA eso era un peligro: al bajar por la pantalla con
la rueda, el puntero pasaba por encima del proveedor o del modelo y los iba
cambiando sin que nadie hubiera elegido nada —y un «Guardar» después lo
dejaba escrito en el `.env`—.

Así que la rueda sobre un selector cerrado **se le pasa a la página** que lo
contiene, que se desplaza como si el selector no estuviera. El valor solo
cambia al elegirlo. Con la lista desplegada, la rueda sigue recorriendo la
lista: eso ocurre en otro widget y aquí no se toca.

Es un filtro de toda la aplicación y no un selector propio: así vale para
todos los que hay y para los que se añadan, sin que nadie tenga que
acordarse de usar una clase especial.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QComboBox, QWidget


class RuedaParaLaPagina(QObject):
    """Desvía la rueda de los selectores a la página que los contiene."""

    def eventFilter(self, objeto: QObject, evento: QEvent) -> bool:  # noqa: N802
        if evento.type() != QEvent.Wheel or not isinstance(objeto, QComboBox):
            return False
        pagina = _pagina_de(objeto)
        if pagina is not None:
            QApplication.sendEvent(pagina.viewport(), evento)
        # Consumida siempre: sin página que desplazar, mejor no hacer nada
        # que cambiar el selector.
        return True


def _pagina_de(widget: QWidget) -> Optional[QAbstractScrollArea]:
    """El área desplazable más cercana que contiene al widget."""
    padre = widget.parentWidget()
    while padre is not None:
        if isinstance(padre, QAbstractScrollArea):
            return padre
        padre = padre.parentWidget()
    return None


#: El filtro instalado, para no ponerlo dos veces si se abren dos ventanas.
_instalado: Optional[RuedaParaLaPagina] = None


def instalar(app: QApplication) -> None:
    """Pone el filtro en la aplicación, una sola vez."""
    global _instalado
    if _instalado is None:
        _instalado = RuedaParaLaPagina(app)
        app.installEventFilter(_instalado)


__all__ = ["RuedaParaLaPagina", "instalar"]
