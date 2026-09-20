"""Saber si hay una versión nueva de BIMNEMO, y traerla.

Compara el commit instalado con el último de la rama publicada. Nada más, y
por eso vive aparte: el resto de BIMNEMO no tiene por qué saber que existe
git.

## Tres decisiones, con su porqué

**Lo pregunta el servidor, no el navegador.** El servidor es quien sabe qué
commit tiene instalado; el navegador no puede leer el ``.git``.

**Sin credenciales.** El repositorio es público, así que no hace falta token
— y no guardar uno es mejor que guardarlo bien. El límite de GitHub sin
autenticar es de 60 consultas por hora; BIMNEMO pregunta al arrancar y cada
media hora, así que ni se acerca.

**Se cachea la respuesta unos minutos.** Abrir tres ventanas no son tres
consultas, y el estado de una rama no cambia entre pestaña y pestaña.

Si GitHub no contesta —sin internet, cortafuegos— **no pasa nada**: se
informa y se reintenta. Una aplicación de escritorio tiene que funcionar sin
red; lo único que se pierde es el aviso de versiones nuevas.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from lightrag.utils import logger

#: Repositorio publicado. Si alguien bifurca BIMNEMO, esto es lo que cambia.
REPO = "CMEDUCATIVA/BIMNEMO"
RAMA = "main"

#: Cuánto vale una respuesta de GitHub antes de volver a preguntar.
CACHE_SEGUNDOS = 300

#: Tope de espera de la consulta. Corto a propósito: es un adorno informativo,
#: no puede hacer esperar a nadie.
TIMEOUT = 6.0

_cache: dict[str, Any] = {"momento": 0.0, "dato": None}


def raiz() -> Path:
    """Raíz del repositorio instalado."""
    return Path(__file__).resolve().parents[3]


def _git(*args: str, timeout: float = 30.0) -> tuple[int, str]:
    """Ejecuta git en la raíz y devuelve (código, salida)."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(raiz()),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except FileNotFoundError:
        return 127, "git no está instalado"
    except subprocess.TimeoutExpired:
        return 124, "git tardó demasiado"


def es_repositorio() -> bool:
    """¿Está BIMNEMO instalado desde git? Si no, no hay nada que actualizar."""
    codigo, _ = _git("rev-parse", "--is-inside-work-tree", timeout=10.0)
    return codigo == 0


def commit_instalado() -> Optional[str]:
    codigo, salida = _git("rev-parse", "HEAD", timeout=10.0)
    return salida if codigo == 0 and salida else None


def hay_cambios_locales() -> bool:
    """¿Hay ficheros del programa modificados a mano?

    Importa porque ``git reset --hard`` los borraría. Se pregunta **antes** de
    actualizar, no después.
    """
    codigo, salida = _git("status", "--porcelain", timeout=20.0)
    return codigo == 0 and bool(salida)


def _pedir_a_github() -> Optional[dict[str, Any]]:
    """El último commit de la rama publicada, o ``None`` si no se pudo."""
    url = f"https://api.github.com/repos/{REPO}/commits/{RAMA}"
    peticion = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            # GitHub pide identificarse; no es una credencial, es cortesía.
            "User-Agent": "BIMNEMO",
        },
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # Sin internet, con cortafuegos o con GitHub caído. No es un error de
        # BIMNEMO y no debe parecerlo.
        logger.debug("BIMNEMO: no se pudo consultar GitHub: %s", exc)
        return None


def ultimo_publicado(forzar: bool = False) -> Optional[dict[str, Any]]:
    """El último commit publicado, cacheado unos minutos."""
    ahora = time.time()
    if not forzar and _cache["dato"] and ahora - _cache["momento"] < CACHE_SEGUNDOS:
        return _cache["dato"]

    dato = _pedir_a_github()
    if dato is not None:
        _cache["dato"] = dato
        _cache["momento"] = ahora
    return dato


def estrategia() -> str:
    """Cómo puede actualizarse ESTA instalación.

    Dos formas de contestar la misma pregunta —«¿estoy al día?»—, elegidas por
    lo que de verdad hay en el disco:

    - ``"git"``: hay `.git` y git funciona. Es la copia de quien desarrolla.
    - ``"release"``: lo demás. Es lo que instala un cliente con el instalador
      de Windows, que no tiene `.git` —16 MB de historia que no le sirve— ni
      `git.exe`, que es una herramienta de programador.

    La pantalla no se entera de cuál es: mismo botón, misma cortina, mismos
    endpoints. Lo que cambia es de dónde sale la información y cómo llegan los
    ficheros.
    """
    return "git" if es_repositorio() else "release"


def _estado_release(forzar: bool = False) -> dict[str, Any]:
    """Estado comparando contra las versiones publicadas de GitHub."""
    from lightrag.api.bimnemo import paquete

    instalada = paquete.version_instalada(raiz())
    if not instalada:
        return {
            "supported": False,
            "reason": (
                "Esta instalación no dice qué versión tiene, así que no puede "
                "saber si hay una más nueva."
            ),
        }

    ultima = paquete.ultima_version(REPO)
    if ultima is None:
        return {
            "supported": True,
            "reachable": False,
            "installed": instalada,
            "behind": False,
            "reason": "No se pudo consultar GitHub.",
        }

    etiqueta = ultima.get("tag_name") or ""
    return {
        "supported": True,
        "reachable": True,
        "strategy": "release",
        "installed": instalada,
        "latest": etiqueta,
        "behind": bool(etiqueta and etiqueta != instalada),
        # Un cliente no edita el código, así que no hay cambios locales que
        # respetar. Y si los hubiera, el despliegue los sobrescribe sin más:
        # avisar de algo que el usuario no ha hecho sería ruido.
        "dirty": False,
        "message": (ultima.get("name") or etiqueta)[:200],
        "date": ultima.get("published_at"),
        "repo": REPO,
    }


def estado(forzar: bool = False) -> dict[str, Any]:
    """Qué versión hay instalada, cuál es la última, y si hace falta actualizar."""
    if estrategia() == "release":
        return _estado_release(forzar)

    instalado = commit_instalado()
    remoto = ultimo_publicado(forzar=forzar)

    if remoto is None:
        return {
            "supported": True,
            "reachable": False,
            "installed": instalado,
            "behind": False,
            "reason": "No se pudo consultar GitHub.",
        }

    ultimo = remoto.get("sha")
    commit = remoto.get("commit") or {}
    return {
        "supported": True,
        "reachable": True,
        "installed": instalado,
        "latest": ultimo,
        "behind": bool(instalado and ultimo and instalado != ultimo),
        "dirty": hay_cambios_locales(),
        "message": (commit.get("message") or "").split("\n")[0][:200],
        "date": (commit.get("author") or {}).get("date"),
        "repo": REPO,
    }


def aplicar(descartar_cambios: bool = False) -> dict[str, Any]:
    """Trae la versión publicada y deja el disco listo para reiniciar.

    **No reinicia el motor.** Quien llama decide cuándo morir, porque el
    reinicio tiene su propia maquinaria —el hueco de la tubería, el
    supervisor— y duplicarla aquí sería tener dos.

    Devuelve qué se hizo, para poder contarlo.
    """
    if estrategia() == "release":
        from lightrag.api.bimnemo import paquete

        antes = paquete.leer_pyproject(raiz())
        resultado = paquete.traer(REPO, raiz())
        if not resultado.get("ok"):
            return resultado
        resultado["dependencies_changed"] = paquete.pyproject_cambio(raiz(), antes)
        return resultado

    if hay_cambios_locales() and not descartar_cambios:
        return {
            "ok": False,
            "reason": "local_changes",
            "message": (
                "Hay cambios locales en el código. Actualizar los borraría."
            ),
        }

    codigo, salida = _git("fetch", "origin", RAMA, timeout=180.0)
    if codigo != 0:
        return {"ok": False, "reason": "fetch", "message": salida[:400]}

    # Antes de movernos, ¿cambian las dependencias? Se mira comparando el
    # `pyproject.toml` de aquí con el de allá: correr `pip install` siempre
    # añadiría medio minuto a cada actualización para no hacer nada casi
    # nunca.
    codigo_diff, salida_diff = _git(
        "diff", "--name-only", "HEAD", f"origin/{RAMA}", "--", "pyproject.toml"
    )
    dependencias = codigo_diff == 0 and bool(salida_diff.strip())

    codigo, salida = _git("reset", "--hard", f"origin/{RAMA}", timeout=120.0)
    if codigo != 0:
        return {"ok": False, "reason": "reset", "message": salida[:400]}

    return {
        "ok": True,
        "installed": commit_instalado(),
        "dependencies_changed": dependencias,
    }


def instalar_dependencias() -> tuple[bool, str]:
    """``pip install -e .[api]``, solo cuando cambió ``pyproject.toml``."""
    from lightrag.api.bimnemo import paquete

    try:
        proc = subprocess.run(
            [paquete.python_del_entorno(raiz()), "-m", "pip", "install", "-e", ".[api]"],
            cwd=str(raiz()),
            capture_output=True,
            text=True,
            timeout=900.0,
        )
        return proc.returncode == 0, (proc.stdout + proc.stderr)[-600:]
    except subprocess.TimeoutExpired:
        return False, "pip tardó demasiado (más de 15 minutos)."
