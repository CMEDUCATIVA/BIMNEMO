"""La sesión de Claude Code viva: rápida, pero sin mezclar contextos.

Reutilizar el proceso ahorra los ~3 s que cuesta preparar la sesión en cada
llamada. El peligro es el otro lado de la misma moneda: **un proceso vivo
recuerda la conversación entera**, y en un RAG eso significa que la
extracción de un fragmento vería el anterior.

De ahí la regla que estas pruebas vigilan: antes de cada llamada va un
``/clear``, y si algo no sale como debe la sesión se mata. Antes perder la
velocidad que mezclar contextos.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from lightrag.llm import claude_sesion

pytestmark = pytest.mark.offline


class ProcesoFalso:
    """Habla el protocolo de ``--output-format stream-json``."""

    def __init__(self, respuestas: list[str] | None = None) -> None:
        self.returncode = None
        self.recibidos: list[str] = []
        self._respuestas = list(respuestas or [])
        self._pendientes: list[bytes] = []
        self.matado = False
        self.stdin = self
        self.stdout = self

    # -- stdin --
    def write(self, datos: bytes) -> None:
        texto = json.loads(datos.decode("utf-8"))["message"]["content"][0]["text"]
        self.recibidos.append(texto)
        respuesta = self._respuestas.pop(0) if self._respuestas else ""
        self._pendientes.append(
            (json.dumps({"type": "result", "result": respuesta}) + "\n").encode("utf-8")
        )

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    # -- stdout --
    async def readline(self) -> bytes:
        return self._pendientes.pop(0) if self._pendientes else b""

    # -- proceso --
    def kill(self) -> None:
        self.matado = True
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


def _sesion(proceso, monkeypatch) -> claude_sesion.SesionClaude:
    viva = claude_sesion.SesionClaude("claude.exe", "claude-opus-5")

    async def arrancar():
        viva._proceso = proceso

    monkeypatch.setattr(viva, "_arrancar", arrancar)
    return viva


# --- lo que hace bien -------------------------------------------------------


async def test_limpia_la_conversacion_antes_de_cada_pregunta(monkeypatch):
    """Sin esto, cada llamada vería la anterior."""
    proceso = ProcesoFalso(["", "primera", "", "segunda"])
    viva = _sesion(proceso, monkeypatch)

    assert await viva.preguntar("uno", 30) == "primera"
    assert await viva.preguntar("dos", 30) == "segunda"

    assert proceso.recibidos == [
        claude_sesion.LIMPIAR, "uno", claude_sesion.LIMPIAR, "dos"
    ]


async def test_el_proceso_se_reutiliza(monkeypatch):
    """Es el motivo de todo esto: no volver a preparar la sesión."""
    proceso = ProcesoFalso(["", "a", "", "b"])
    viva = _sesion(proceso, monkeypatch)
    arrancadas = []
    original = viva._arrancar

    async def contar():
        arrancadas.append(1)
        await original()

    monkeypatch.setattr(viva, "_arrancar", contar)

    await viva.preguntar("uno", 30)
    await viva.preguntar("dos", 30)
    assert arrancadas == [1], "una sola vez"


# --- lo que hace cuando algo va mal -----------------------------------------


async def test_si_la_limpieza_no_contesta_se_mata_la_sesion(monkeypatch):
    """Una sesión de la que no se sabe qué recuerda no se vuelve a usar."""

    class SinRespuestaAlClear(ProcesoFalso):
        def write(self, datos):
            texto = json.loads(datos.decode("utf-8"))["message"]["content"][0]["text"]
            self.recibidos.append(texto)
            if texto != claude_sesion.LIMPIAR:
                super().write(datos)

    proceso = SinRespuestaAlClear(["algo"])
    viva = _sesion(proceso, monkeypatch)

    with pytest.raises(RuntimeError):
        await viva.preguntar("uno", 30)

    assert proceso.matado and not viva.viva
    assert "uno" not in proceso.recibidos, "no se pregunta sin limpiar antes"


async def test_una_pregunta_que_se_cuelga_tambien_mata(monkeypatch):
    """Limpia bien y luego el modelo no vuelve: la sesión no se reutiliza."""

    class SeCuelgaAlPreguntar(ProcesoFalso):
        def write(self, datos):
            texto = json.loads(datos.decode("utf-8"))["message"]["content"][0]["text"]
            # Contesta al /clear y se queda callado con la pregunta.
            if texto == claude_sesion.LIMPIAR:
                super().write(datos)
            else:
                self.recibidos.append(texto)

        async def readline(self):
            if self._pendientes:
                return self._pendientes.pop(0)
            await asyncio.sleep(30)
            return b""

    proceso = SeCuelgaAlPreguntar([""])
    viva = _sesion(proceso, monkeypatch)

    with pytest.raises(asyncio.TimeoutError):
        await viva.preguntar("uno", 0.05)
    assert proceso.matado and not viva.viva


async def test_un_error_del_cli_no_deja_la_sesion_en_pie(monkeypatch):
    class ConError(ProcesoFalso):
        def write(self, datos):
            texto = json.loads(datos.decode("utf-8"))["message"]["content"][0]["text"]
            self.recibidos.append(texto)
            fallo = {"type": "result", "is_error": True, "result": "se acabó el saldo"}
            self._pendientes.append((json.dumps(fallo) + "\n").encode("utf-8"))

    proceso = ConError()
    viva = _sesion(proceso, monkeypatch)

    with pytest.raises(RuntimeError, match="saldo"):
        await viva.preguntar("uno", 30)
    assert proceso.matado


async def test_una_linea_que_no_es_json_no_tira_la_sesion(monkeypatch):
    """El CLI intercala cosas; solo importa el `result`."""

    class ConRuido(ProcesoFalso):
        def write(self, datos):
            super().write(datos)
            self._pendientes.insert(0, b"esto no es json\n")

    proceso = ConRuido(["", "bien"])
    viva = _sesion(proceso, monkeypatch)

    assert await viva.preguntar("uno", 30) == "bien"
    assert not proceso.matado


# --- el interruptor y el reparto -------------------------------------------


def test_viene_encendida_y_se_puede_apagar(monkeypatch):
    monkeypatch.delenv(claude_sesion.INTERRUPTOR, raising=False)
    assert claude_sesion.activada()
    for apagado in ("0", "false", "no", "off"):
        monkeypatch.setenv(claude_sesion.INTERRUPTOR, apagado)
        assert not claude_sesion.activada()


def test_cada_modelo_tiene_la_suya():
    """Dos roles con modelos distintos no pueden compartir conversación."""
    try:
        una = claude_sesion.sesion("claude.exe", "claude-opus-5")
        otra = claude_sesion.sesion("claude.exe", "claude-haiku-4-5")
        assert una is not otra
        assert claude_sesion.sesion("claude.exe", "claude-opus-5") is una
    finally:
        claude_sesion._SESIONES.clear()
