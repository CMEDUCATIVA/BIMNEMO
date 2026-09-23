"""Una sesión de Claude Code viva, reutilizada entre llamadas.

El binding ``claude_code`` arrancaba un proceso por llamada. Arrancarlo no
es lo caro —el binario tarda 0,05 s en levantarse—, lo caro es lo que hace
después: leer sus ajustes, resolver credenciales y permisos, preparar la
sesión. Son unos tres segundos que se pagan **cada vez**.

Medido con un prompt del tamaño de un contexto de RAG:

===========================  ======================================
proceso nuevo cada vez       7,0 s · 6,5 s      (media 6,7 s)
proceso vivo + ``/clear``    5,4 s · 3,7 s · 3,6 s
===========================  ======================================

Un 46 % menos por llamada, y se nota sobre todo indexando, que son cientos.

## La regla que sostiene esto

**Un proceso vivo recuerda la conversación entera.** Comprobado: se le da un
número en un turno y lo repite en el siguiente. Para un RAG eso no es una
molestia, es un error: la extracción de un fragmento vería el anterior y una
pregunta vería la de antes.

Por eso antes de cada llamada va un ``/clear``, que vacía la conversación
sin cerrar el proceso (0,4 s). Y de ahí la regla:

    Si el ``/clear`` no confirma, se mata el proceso.

Antes perder la velocidad que mezclar contextos. Lo mismo ante cualquier
error, cierre de la salida o espera agotada: se mata, y quien llamaba se va
por el camino de siempre —un proceso suelto—, que sigue existiendo entero.

## Lo que esta clase NO hace

No serializa: eso ya lo hace el semáforo del binding, y tiene que seguir
haciéndolo porque una conversación no admite dos llamadas a la vez.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from typing import Any, Optional

from lightrag.utils import logger

#: Orden de limpieza del CLI. Vacía la conversación sin cerrar el proceso.
LIMPIAR = "/clear"

#: Lo que se espera a que el ``/clear`` conteste. Es local y no llama a la
#: API: si tarda esto, algo va mal y se prefiere matar el proceso.
LIMPIEZA_TIMEOUT = 30.0

#: Variable para apagar esto sin publicar nada, si diera guerra.
INTERRUPTOR = "CLAUDE_CODE_SESION_VIVA"

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def activada() -> bool:
    """¿Se reutiliza la sesión? Encendido salvo que se diga lo contrario."""
    return (os.environ.get(INTERRUPTOR, "1").strip().lower()
            not in ("0", "false", "no", "off"))


def _mensaje(texto: str) -> bytes:
    """Un turno de usuario en el formato que lee ``--input-format stream-json``."""
    return (
        json.dumps(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": texto}],
                },
            }
        )
        + "\n"
    ).encode("utf-8")


class SesionClaude:
    """Un proceso de Claude Code reutilizado, limpio antes de cada llamada.

    No es seguro llamar a :meth:`preguntar` desde dos sitios a la vez: es
    una conversación, y dos turnos entrelazados se leerían el uno al otro.
    Quien la usa ya la serializa.
    """

    def __init__(self, binario: str, modelo: str = "", esfuerzo: str = "") -> None:
        self.binario = binario
        self.modelo = modelo
        self.esfuerzo = esfuerzo
        self._proceso: Optional[asyncio.subprocess.Process] = None

    # -- el proceso ---------------------------------------------------------

    @property
    def viva(self) -> bool:
        return self._proceso is not None and self._proceso.returncode is None

    def _orden(self) -> list[str]:
        orden = [
            self.binario,
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            # `--verbose` no es charlatanería: sin él, el CLI se niega a
            # emitir stream-json con --print.
            "--verbose",
            "--max-turns",
            "1",
            "--permission-mode",
            "plan",
        ]
        if self.modelo:
            orden += ["--model", self.modelo]
        if self.esfuerzo:
            orden += ["--effort", self.esfuerzo]
        return orden

    async def _arrancar(self) -> None:
        self._proceso = await asyncio.create_subprocess_exec(
            *self._orden(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            # La salida de error se descarta: el CLI escribe ahí avisos que
            # no son fallos («este espacio de trabajo no es de confianza») y
            # leerla sin consumirla llenaría la tubería y colgaría el
            # proceso. Lo que importa viene por la salida normal.
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
        )

    async def cerrar(self) -> None:
        """Mata el proceso. Se puede llamar siempre, aunque no haya ninguno."""
        proceso, self._proceso = self._proceso, None
        if proceso is None or proceso.returncode is not None:
            return
        try:
            if proceso.stdin is not None:
                proceso.stdin.close()
            proceso.kill()
            await proceso.wait()
        except (OSError, ProcessLookupError):  # ya se había ido
            pass

    # -- un turno -----------------------------------------------------------

    async def _turno(self, texto: str, timeout: float) -> str:
        """Manda un mensaje y devuelve el texto del ``result``.

        Lanza si el proceso no está, si se cierra la salida o si tarda. Quien
        llama lo traduce en «mata y vete por el otro camino».
        """
        proceso = self._proceso
        if proceso is None or proceso.stdin is None or proceso.stdout is None:
            raise RuntimeError("sesion-sin-proceso")

        proceso.stdin.write(_mensaje(texto))
        await proceso.stdin.drain()

        while True:
            linea = await asyncio.wait_for(proceso.stdout.readline(), timeout=timeout)
            if not linea:
                raise RuntimeError("sesion-cerrada")
            try:
                dato = json.loads(linea)
            except ValueError:
                # Una línea que no es JSON no es motivo para tirar la sesión:
                # se salta y se sigue esperando el resultado.
                continue
            if dato.get("type") != "result":
                continue
            if dato.get("is_error"):
                raise RuntimeError(str(dato.get("result") or "sesion-error"))
            return str(dato.get("result") or "")

    async def preguntar(self, texto: str, timeout: float) -> str:
        """Limpia la conversación, pregunta y devuelve la respuesta.

        Arranca el proceso si hacía falta. Cualquier fallo mata la sesión
        antes de propagarse: una sesión de la que no se sabe qué recuerda no
        se vuelve a usar.
        """
        try:
            if not self.viva:
                await self._arrancar()
            # Primero limpiar, SIEMPRE. Lo que había antes en esta
            # conversación no es de quien pregunta ahora.
            await self._turno(LIMPIAR, LIMPIEZA_TIMEOUT)
            return await self._turno(texto, timeout)
        except (asyncio.TimeoutError, RuntimeError, OSError, ValueError) as exc:
            await self.cerrar()
            logger.debug("claude_code: sesión viva descartada (%s)", exc)
            raise


#: Una sesión por **orden distinta**: binario, modelo y nivel de
#: razonamiento. Los tres van en la línea de arranque, así que dos que no
#: coincidan no pueden compartir proceso. En la práctica son una o dos: la
#: de indexar y la de responder, que suelen llevar niveles distintos.
_SESIONES: dict[tuple[str, str, str], SesionClaude] = {}


def sesion(binario: str, modelo: str, esfuerzo: str = "") -> SesionClaude:
    """La sesión de ese binario, modelo y esfuerzo; se crea si no estaba."""
    clave = (binario, modelo or "", esfuerzo or "")
    viva = _SESIONES.get(clave)
    if viva is None:
        viva = SesionClaude(binario, modelo, esfuerzo)
        _SESIONES[clave] = viva
    return viva


async def cerrar_todas() -> None:
    """Apaga las sesiones abiertas. La llama el motor al cerrar."""
    for viva in list(_SESIONES.values()):
        await viva.cerrar()
    _SESIONES.clear()


__all__ = [
    "INTERRUPTOR",
    "LIMPIAR",
    "SesionClaude",
    "activada",
    "cerrar_todas",
    "sesion",
]
