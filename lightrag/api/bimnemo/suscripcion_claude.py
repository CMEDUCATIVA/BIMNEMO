"""Gestión de la suscripción de Claude (Claude Code) para BIMNEMO.

La suscripción de Claude Pro/Max no es una clave de API: se autentica con
``claude auth login`` (OAuth en el navegador) y Claude Code guarda sus
credenciales en ``~/.claude``. Este módulo da a la pantalla de configuración
lo que necesita para el modo «por suscripción»:

* **estado** — si hay una sesión iniciada (CLI o fichero de credenciales).
* **iniciar_sesion** — abre el login OAuth oficial y espera a que termine.
* **probar** — hace una petición real, sin herramientas, para comprobar que la
  suscripción responde de verdad.
* **descargar** — instala el binario de Claude Code con el instalador oficial.

Todo aquí es código síncrono con ``subprocess``; los endpoints lo ejecutan en
un hilo (``asyncio.to_thread``) para no bloquear el bucle del motor.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from lightrag.utils import logger

#: Plazo del ``claude auth status``. Es una llamada local y rápida.
STATUS_TIMEOUT = 15.0

#: Plazo del login OAuth. El usuario tiene que terminar en el navegador.
LOGIN_TIMEOUT = 600.0

#: Plazo de la prueba de conexión. Una llamada real de Claude Code en frío
#: puede tardar varios segundos; treinta es un margen razonable.
PROBE_TIMEOUT = 60.0

#: Plazo de la descarga/instalación del binario. Depende de la red.
INSTALL_TIMEOUT = 900.0

#: Texto que debe devolver la prueba de conexión para darla por buena.
PROBE_PALABRA = "KUN_AUTH_OK"

#: Patrón para recortar el token OAuth si apareciera en un mensaje de error.
TOKEN_OAUTH = re.compile(r"sk-ant-oat[\w-]+")

#: ANSI/emojis de la salida del CLI no aportan nada a un aviso de la ventana.
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def binario() -> str:
    """El ejecutable de Claude Code, con la ruta explícita ganando al PATH."""
    explicito = os.environ.get("CLAUDE_CODE_BIN", "").strip()
    if explicito:
        return explicito
    return shutil.which("claude") or "claude"


def credenciales() -> Path:
    """El fichero donde el CLI oficial guarda la sesión OAuth."""
    return Path.home() / ".claude" / ".credentials.json"


def _limpiar(texto: str) -> str:
    """Quita ANSI y tokens, colapsa espacios y acota la longitud."""
    limpio = ANSI.sub("", texto)
    limpio = TOKEN_OAUTH.sub("<redactado>", limpio)
    limpio = re.sub(r"\s+", " ", limpio).strip()
    return limpio[-500:]


def _ejecutar(orden: list[str], timeout: float) -> tuple[int, str, str]:
    """Ejecuta un comando y devuelve ``(código, stdout, stderr)``.

    La salida se captura entera pero el módulo solo la usa de forma acotada y
    redactada. ``FileNotFoundError`` se normaliza a un mensaje legible.
    """
    try:
        resultado = subprocess.run(
            orden,
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except FileNotFoundError:
        return -1, "", "claude-cli-no-encontrado"
    except subprocess.TimeoutExpired:
        return -1, "", "claude-cli-timeout"
    except OSError as exc:
        return -1, "", str(exc)
    return (
        resultado.returncode,
        resultado.stdout.decode("utf-8", errors="replace"),
        resultado.stderr.decode("utf-8", errors="replace"),
    )


def estado() -> dict[str, Any]:
    """¿Hay una sesión de Claude iniciada? Fuente y mensaje para la ventana."""
    codigo, salida, error = _ejecutar([binario(), "auth", "status", "--json"], STATUS_TIMEOUT)
    if codigo == 0:
        try:
            datos = json.loads(salida)
        except (ValueError, TypeError):
            datos = {}
        if datos.get("loggedIn") is True:
            return {"logged_in": True, "source": "cli", "message": ""}
        return {
            "logged_in": False,
            "source": "cli",
            "message": _limpiar(datos.get("message") or "") or "sin sesión",
        }

    # El CLI no contesta: el fichero de credenciales sirve de respaldo con
    # CLIs más antiguos, igual que hace la app de escritorio de Kun.
    if credenciales().is_file():
        return {"logged_in": True, "source": "credentials-file", "message": ""}

    if codigo == -1 and error == "claude-cli-no-encontrado":
        return {"logged_in": False, "source": "none", "message": "claude-cli-no-encontrado"}
    return {
        "logged_in": False,
        "source": "none",
        "message": _limpiar(error or salida) or "sin sesión",
    }


def iniciar_sesion() -> dict[str, Any]:
    """Abre el login OAuth oficial y espera a que el usuario lo termine.

    ``--claudeai`` fuerza el camino de claude.ai (suscripción) en vez del
    prompt interactivo que pregunta entre claude.ai y la consola de Anthropic.
    El proceso queda esperando a que el navegador complete el OAuth; aquí se
    deja correr hasta que cierre o se agote el plazo, y luego se relee el
    estado real.
    """
    if estado()["logged_in"]:
        return {"ok": True, "message": "ya-hay-sesion"}

    codigo, salida, error = _ejecutar(
        [binario(), "auth", "login", "--claudeai"], LOGIN_TIMEOUT
    )
    if estado()["logged_in"]:
        return {"ok": True, "message": ""}

    detalle = _limpiar(error or salida)
    if codigo == -1 and error == "claude-cli-no-encontrado":
        return {"ok": False, "message": "claude-cli-no-encontrado"}
    return {"ok": False, "message": detalle or "login-incompleto"}


def probar() -> dict[str, Any]:
    """Hace una petición real sin herramientas para probar la suscripción.

    Un código de salida 0 prueba que la autenticación funciona de verdad
    contra el backend, no solo que existe una credencial en disco.
    """
    inicio = time.monotonic()
    orden = [
        binario(),
        "-p",
        f"Reply exactly {PROBE_PALABRA}",
        "--output-format",
        "text",
        "--max-turns",
        "1",
        "--no-session-persistence",
        "--permission-mode",
        "plan",
    ]
    codigo, salida, error = _ejecutar(orden, PROBE_TIMEOUT)
    latencia = int((time.monotonic() - inicio) * 1000)

    if codigo == 0:
        return {"ok": True, "latency_ms": latencia, "message": ""}

    detalle = _limpiar(error or salida)
    if codigo == -1 and error == "claude-cli-no-encontrado":
        return {"ok": False, "latency_ms": latencia, "message": "claude-cli-no-encontrado"}
    return {
        "ok": False,
        "latency_ms": latencia,
        "message": detalle or f"claude-probe-exit-{codigo}",
    }


def descargar() -> dict[str, Any]:
    """Instala el binario de Claude Code con el instalador oficial.

    Se usa la vía oficial de Anthropic por plataforma. Es una operación de red
    larga; el endpoint la corre en un hilo y la ventana enseña su propio
    estado de «descargando» mientras tanto.
    """
    if binario() != "claude" and shutil.which(binario()):
        return {"ok": True, "message": "ya-instalado"}

    plataforma = os.name
    if plataforma == "nt":
        orden = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "irm https://claude.ai/install.ps1 | iex",
        ]
    else:
        orden = ["bash", "-lc", "curl -fsSL https://claude.ai/install.sh | bash"]

    logger.info("BIMNEMO: instalando Claude Code (%s)", "powershell" if plataforma == "nt" else "curl")
    codigo, salida, error = _ejecutar(orden, INSTALL_TIMEOUT)

    if shutil.which("claude") or (
        "CLAUDE_CODE_BIN" in os.environ and Path(os.environ["CLAUDE_CODE_BIN"]).is_file()
    ):
        return {"ok": True, "message": ""}
    detalle = _limpiar(error or salida)
    return {"ok": False, "message": detalle or f"instalacion-exit-{codigo}"}


__all__ = [
    "binario",
    "credenciales",
    "descargar",
    "estado",
    "iniciar_sesion",
    "probar",
]
