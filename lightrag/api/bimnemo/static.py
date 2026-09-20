"""Servido de los ficheros de la interfaz de BIMNEMO.

Existe por un fallo concreto y muy fácil de repetir: ``StaticFiles`` manda
``ETag`` y ``Last-Modified`` pero **no manda ``Cache-Control``**. Sin esa
cabecera el navegador aplica su heurística —habitualmente un 10 % del tiempo
transcurrido desde la última modificación— y decide por su cuenta durante
cuánto rato no vuelve a preguntar.

En una aplicación de escritorio eso se traduce en algo desconcertante: se
actualiza BIMNEMO, el servidor sirve el fichero nuevo, y la ventana sigue
enseñando el anterior sin ningún aviso. Pasó exactamente así con un módulo
de JavaScript.

La respuesta es ``no-cache``, que **no** significa «no guardes»: significa
«guarda, pero pregunta siempre antes de usarlo». El navegador manda su ETag,
el servidor contesta 304 si no ha cambiado y no viaja ningún byte. Contra
127.0.0.1 ese viaje es gratis, y a cambio lo que se ve es siempre lo que hay
en disco.
"""

from __future__ import annotations

from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class RevalidatedStaticFiles(StaticFiles):
    """``StaticFiles`` que obliga al navegador a revalidar cada fichero."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        # También en el 304: si se omitiera ahí, el navegador se quedaría con
        # la política anterior de esa entrada y volvería a saltarse la
        # comprobación en la siguiente carga.
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


__all__ = ["RevalidatedStaticFiles"]
