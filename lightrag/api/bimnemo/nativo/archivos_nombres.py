"""Que ningún archivo entre en Archivos con un nombre que no cabe.

Dos momentos:

- **Al subir.** Antes de mandar nada, los nombres que no caben pasan por
  :class:`DialogoNombres`. Los que caben suben sin preguntar.
- **Después.** Una fila que ya falló por nombre largo —o un archivo sin
  indexar con el nombre largo— ofrece «Renombrar»: se renombra en la memoria
  y se vuelve a leer, sin subirlo otra vez (``POST /bimnemo/files/rename``).

Aparte de ``pantalla_archivos.py`` porque ese fichero ya pasa de 600 líneas;
aquí está todo lo de los nombres y allí solo se engancha.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtWidgets import QDialog, QWidget

from lightrag.api.bimnemo import nombres
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.nombres_dialogo import DialogoNombres


class GuardianNombres:
    """Sabe cuánto cabe en la memoria abierta y lo hace cumplir."""

    def __init__(
        self,
        motor: Motor,
        padre: QWidget,
        existentes: Callable[[], frozenset[str]],
    ) -> None:
        self.motor = motor
        self.padre = padre
        self._existentes = existentes
        #: Longitud de «<entrada>\\__parsed__\\» de la memoria abierta. Sin
        #: ella no se sabe cuánto cabe, y entonces no se frena nada.
        self.raiz: Optional[int] = None
        #: Para las pruebas: la ventana se sustituye por una respuesta.
        self.dialogo = DialogoNombres

    def cargar(self) -> None:
        """Lo que cabe depende de la memoria: se pide cada vez que cambia."""
        self.raiz = None

        def llego(datos: Any) -> None:
            if isinstance(datos, dict) and datos.get("parsed_root_len"):
                self.raiz = int(datos["parsed_root_len"])

        self.motor.get("/bimnemo/files/limits", llego, None)

    def limite(self, nombre: str) -> Optional[int]:
        if self.raiz is None:
            return None
        return nombres.maximo(self.raiz, nombres.extension(nombre))

    def no_cabe(self, nombre: str) -> bool:
        limite = self.limite(nombre)
        return limite is not None and bool(nombres.problemas(nombre, limite))

    # -- al subir -----------------------------------------------------------

    def preparar(self, rutas: list[str]) -> list[tuple[str, str]]:
        """``[(ruta, nombre con el que sube)]``; los que no caben, tras preguntar.

        Si se cancela el aviso, esos no suben y los demás sí: cancelar dice
        «estos no», no «ninguno».
        """
        listos = [(r, Path(r).name) for r in rutas if r]
        largos = [nombre for _, nombre in listos if self.no_cabe(nombre)]
        if not largos:
            return listos

        dialogo = self.dialogo(
            self.padre, largos, lambda n: self.limite(n) or len(n), self._existentes()
        )
        if dialogo.exec() != QDialog.Accepted:
            return [(r, n) for r, n in listos if n not in largos]
        nuevos = dialogo.resultado()
        return [(r, nuevos.get(n, n)) for r, n in listos]

    # -- después: renombrar lo que ya está ---------------------------------

    def renombrar(
        self,
        nombre: str,
        hecho: Callable[[Any], None],
        fallo: Callable[[str], None],
    ) -> None:
        dialogo = self.dialogo(
            self.padre,
            [nombre],
            lambda n: self.limite(n) or len(n),
            self._existentes(),
            titulo="Renombrar y volver a leer",
            explicacion=(
                "Se cambia el nombre dentro de la memoria y se vuelve a leer el "
                "documento. No hace falta subirlo otra vez, y el archivo de tu "
                "PC no cambia."
            ),
            seguir="Renombrar y volver a leer",
        )
        if dialogo.exec() != QDialog.Accepted:
            return
        nuevo = dialogo.resultado()[nombre]
        self.motor.post(
            "/bimnemo/files/rename", {"name": nombre, "new_name": nuevo}, hecho, fallo
        )


__all__ = ["GuardianNombres"]
