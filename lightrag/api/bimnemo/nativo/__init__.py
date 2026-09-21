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


#: Cómo se identifica BIMNEMO ante la barra de tareas de Windows.
ID_APLICACION = "CMEducativa.BIMNEMO"


def _identidad_en_windows() -> None:
    """Que la barra de tareas trate la ventana como BIMNEMO, no como Python.

    Windows agrupa los botones de la barra por *identificador de aplicación*,
    y si el proceso no declara uno usa el del ejecutable: el intérprete, con
    su icono. Entonces `setWindowIcon` cambia la esquina de la ventana pero
    no el botón de la barra, que es lo que se ve. Tiene que declararse
    **antes** de crear la primera ventana.
    """
    import sys

    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            ID_APLICACION
        )
    except (AttributeError, OSError):
        # Windows muy antiguo: se queda el icono del ejecutable, que no es
        # motivo para no abrir.
        pass


def abrir(base_url: str, version: str) -> int:
    """Arranca la ventana. Devuelve el código de salida de la aplicación."""
    _identidad_en_windows()
    from PySide6.QtWidgets import QApplication

    from lightrag.api.bimnemo.nativo import iconos
    from lightrag.api.bimnemo.nativo.motor import Motor
    from lightrag.api.bimnemo.nativo.ventana import Ventana

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("BIMNEMO")
    app.setOrganizationName("CM Educativa")
    # Sin `setApplicationDisplayName`: Qt lo **añade** al título de cada
    # ventana, y la barra quedaba «BIMNEMO — Memoria de conocimiento -
    # BIMNEMO».

    # La marca, en todos los tamaños que Windows pide.
    #
    # Sin esto la barra de tareas enseña el icono del intérprete —la «py»
    # amarilla y azul—, que es verdad y es lo peor que puede decir: que esto
    # no es un programa, es Python ejecutando algo. Se dan varios tamaños
    # porque Windows pide 16 para la barra de título y 32 para Alt+Tab, y si
    # solo hay uno lo escala él, mal.
    app.setWindowIcon(iconos.de_la_aplicacion())

    motor = Motor(base_url)
    motor.usar_clave(clave_guardada())
    ventana = Ventana(motor, version)
    ventana.show()
    return app.exec()


__all__ = ["abrir", "clave_guardada", "disponible"]
