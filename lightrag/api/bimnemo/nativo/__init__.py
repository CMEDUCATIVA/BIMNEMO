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


def clave_guardada() -> str:
    """La clave de acceso que el motor va a exigir, si hay alguna.

    Sin esto, protegerla y volver a abrir BIMNEMO deja al usuario **fuera de
    su propia aplicación**: el motor arranca pidiendo la clave del `.env`, la
    ventana no la presenta y todas las pantallas reciben 401. La única salida
    sería editar el fichero a mano, que es justo lo que esta aplicación
    existe para no tener que hacer.

    Se buscan los dos ficheros que pueden ser el bueno: el del directorio de
    trabajo —el que lee LightRAG al arrancar— y el de la raíz instalada, que
    es donde lo crea el primer arranque. Coinciden salvo que se lance BIMNEMO
    desde otra carpeta.
    """
    import os
    from pathlib import Path

    from lightrag.api.bimnemo.envfile import read_env

    aqui = Path(__file__).resolve()
    for carpeta in (Path(os.getcwd()), aqui.parents[4]):
        fichero = carpeta / ".env"
        if not fichero.is_file():
            continue
        try:
            clave = read_env(fichero).get("LIGHTRAG_API_KEY", "").strip()
        except OSError:
            continue
        if clave:
            return clave
    return ""


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

    motor = Motor(base_url)
    motor.usar_clave(clave_guardada())
    ventana = Ventana(motor, version)
    ventana.show()
    return app.exec()


__all__ = ["abrir", "clave_guardada", "disponible"]
