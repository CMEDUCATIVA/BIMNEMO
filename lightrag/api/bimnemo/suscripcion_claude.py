"""Gestión de la suscripción de Claude (Claude Code) para BIMNEMO.

La suscripción de Claude Pro/Max no es una clave de API: se autentica con
``claude auth login`` (OAuth en el navegador) y Claude Code guarda sus
credenciales en ``~/.claude``. Este módulo da a la pantalla de configuración
lo que necesita para el modo «por suscripción»:

* **estado** — si hay una sesión iniciada (CLI o fichero de credenciales).
* **iniciar_sesion / cerrar_sesion** — login y logout OAuth oficiales.
* **probar** — petición real, sin herramientas, para comprobar la suscripción.
* **iniciar_descarga / progreso_descarga** — instalar el binario en segundo
  plano e informar del avance para la barra de la ventana.

La descarga corre en un hilo aparte y expone su estado en
:func:`progreso_descarga`; así la ventana enseña una barra de avance y cambia
de etapa cuando termina, sin bloquearse.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from lightrag.utils import logger

#: Plazo del ``claude auth status``. Es una llamada local y rápida.
STATUS_TIMEOUT = 15.0

#: Plazo del login OAuth. El usuario tiene que terminar en el navegador.
LOGIN_TIMEOUT = 600.0

#: Plazo de la prueba de conexión.
PROBE_TIMEOUT = 60.0

#: Plazo de la descarga/instalación del binario. Depende de la red.
INSTALL_TIMEOUT = 900.0

#: Texto que debe devolver la prueba de conexión para darla por buena.
PROBE_PALABRA = "KUN_AUTH_OK"

#: Patrón para recortar el token OAuth si apareciera en un mensaje de error.
TOKEN_OAUTH = re.compile(r"sk-ant-oat[\w-]+")

#: ANSI/emojis de la salida del CLI no aportan nada a un aviso de la ventana.
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _candidatos() -> list[Path]:
    """Los sitios donde el instalador oficial deja el binario.

    El PATH del motor **no cambia** después de instalar: si el instalador lo
    añade al PATH del usuario, el proceso en marcha no lo ve. Por eso, además
    de ``claude`` en el PATH, se miran las ubicaciones de instalación directas.
    """
    home = Path.home()
    nombre = "claude.exe" if os.name == "nt" else "claude"
    candidatos = [
        home / ".local" / "bin" / nombre,
        home / ".claude" / "local" / nombre,
    ]
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidatos.append(Path(appdata) / "npm" / "claude.cmd")
    return candidatos


def binario() -> str:
    """El ejecutable de Claude Code, o ``"claude"`` si no se encuentra.

    Orden: ``CLAUDE_CODE_BIN`` (ruta explícita), ``claude`` en el PATH y, por
    último, los sitios del instalador oficial.
    """
    explicito = os.environ.get("CLAUDE_CODE_BIN", "").strip()
    if explicito and Path(explicito).is_file():
        return explicito
    del_path = shutil.which("claude")
    if del_path:
        return del_path
    for candidato in _candidatos():
        if candidato.is_file():
            return str(candidato)
    return "claude"


def _hay_binario() -> bool:
    return binario() != "claude"


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
    """Ejecuta un comando y devuelve ``(código, stdout, stderr)``."""
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
    # CLIs más antiguos.
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


def cerrar_sesion() -> dict[str, Any]:
    """Cierra la sesión OAuth de Claude Code."""
    codigo, salida, error = _ejecutar([binario(), "auth", "logout"], STATUS_TIMEOUT * 4)
    if codigo == 0:
        return {"ok": True, "message": ""}
    if codigo == -1 and error == "claude-cli-no-encontrado":
        return {"ok": False, "message": "claude-cli-no-encontrado"}
    # Aunque el CLI no confirme, si ya no queda fichero de credenciales, la
    # sesión está cerrada de hecho.
    if not credenciales().is_file():
        return {"ok": True, "message": ""}
    return {"ok": False, "message": _limpiar(error or salida) or "no-se-pudo-cerrar"}


def probar() -> dict[str, Any]:
    """Hace una petición real sin herramientas para probar la suscripción."""
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


# -- descarga en segundo plano ----------------------------------------------

#: Estado de la descarga. ``state`` ∈ inactivo | descargando | instalado | error.
_descarga: dict[str, str] = {"state": "inactivo", "message": ""}
_descarga_hilo: threading.Thread | None = None


def _instalador() -> list[str]:
    """El comando del instalador oficial de Claude Code, por plataforma."""
    if os.name == "nt":
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "irm https://claude.ai/install.ps1 | iex",
        ]
    return ["bash", "-lc", "curl -fsSL https://claude.ai/install.sh | bash"]


def _correr_descarga() -> None:
    """El cuerpo del hilo de descarga: instala y actualiza el estado."""
    global _descarga
    _descarga = {"state": "descargando", "message": ""}
    codigo, salida, error = _ejecutar(_instalador(), INSTALL_TIMEOUT)
    if _hay_binario():
        _descarga = {"state": "instalado", "message": ""}
        logger.info("BIMNEMO: binario de Claude Code instalado")
    else:
        detalle = _limpiar(error or salida)
        _descarga = {
            "state": "error",
            "message": detalle or f"instalacion-exit-{codigo}",
        }
        logger.warning("BIMNEMO: no se pudo instalar Claude Code: %s", _descarga["message"])


def iniciar_descarga() -> dict[str, Any]:
    """Arranca la instalación si no está en curso y devuelve el estado actual.

    No bloquea: el instalador corre en un hilo y la ventana consulta
    :func:`progreso_descarga` para pintar la barra.
    """
    global _descarga, _descarga_hilo
    if _descarga["state"] == "descargando":
        return {"started": False, "state": "descargando"}
    if _hay_binario():
        _descarga = {"state": "instalado", "message": ""}
        return {"started": False, "state": "instalado"}
    _descarga = {"state": "descargando", "message": ""}
    _descarga_hilo = threading.Thread(target=_correr_descarga, daemon=True)
    _descarga_hilo.start()
    return {"started": True, "state": "descargando"}


def progreso_descarga() -> dict[str, Any]:
    """El estado de la instalación: inactivo, descargando, instalado o error."""
    return dict(_descarga)


__all__ = [
    "binario",
    "cerrar_sesion",
    "credenciales",
    "estado",
    "iniciar_descarga",
    "iniciar_sesion",
    "probar",
    "progreso_descarga",
]
