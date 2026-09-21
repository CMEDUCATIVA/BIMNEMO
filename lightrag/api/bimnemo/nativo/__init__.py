"""La interfaz nativa de BIMNEMO.

Una ventana de Windows de verdad, en lugar de una copia de Chrome enseñando
una página local. El plan, las etapas y lo que cuesta están en
`docs/BIMNEMO_INTERFAZ_NATIVA.md`.

Se importa **solo cuando se pide**: Qt son 60 MB de bibliotecas nativas y no
hay ninguna razón para cargarlas en el motor, que no dibuja nada.
"""

from __future__ import annotations


def disponible() -> bool:
    """¿Está Qt en este paquete?

    Se pregunta antes de intentar abrir la ventana nativa para poder caer en
    el modo navegador con una explicación, en vez de con un rastro de error.
    """
    try:
        import PySide6  # noqa: F401
    except ImportError:
        return False
    return True


def abrir(base_url: str, version: str) -> int:
    """Arranca la ventana. Devuelve el código de salida de la aplicación."""
    from PySide6.QtWidgets import QApplication

    from lightrag.api.bimnemo.nativo.motor import Motor
    from lightrag.api.bimnemo.nativo.ventana import Ventana

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("BIMNEMO")
    app.setOrganizationName("CM Educativa")
    # Sin `setApplicationDisplayName`: Qt lo **añade** al título de cada
    # ventana, y la barra quedaba «BIMNEMO — Memoria de conocimiento -
    # BIMNEMO».

    ventana = Ventana(Motor(base_url), version)
    ventana.show()
    return app.exec()


__all__ = ["abrir", "disponible"]
