"""Traer una versión publicada de BIMNEMO sin git por medio.

Es la mitad «cliente» del actualizador: quien instaló BIMNEMO con el
instalador de Windows no tiene `.git` —pesa 16 MB de historia que no le
sirve— ni `git.exe`, que es una herramienta de programador.

## Lo que se descarga

El **zipball de la versión publicada**: exactamente lo que el repositorio
versiona. Y eso deja fuera, *por construcción*, lo único que nunca debe
tocarse en el ordenador de un cliente:

- ``.env`` — su configuración y sus claves
- ``inputs/`` — sus documentos
- ``rag_storage/`` — sus memorias
- ``.venv/`` — el intérprete y las dependencias

No hay una lista de exclusiones que mantener. No están en el paquete porque
están en `.gitignore`, y esa es la garantía: una lista explícita es algo que
alguien olvida actualizar el día que añade una carpeta nueva.

## Por qué no hace falta un actualizador externo

En Windows no se puede sobrescribir un fichero en uso, y eso suele obligar a
cerrar la aplicación para actualizarla. Aquí no, y el motivo es concreto: el
paquete **no contiene el entorno virtual**, así que `python.exe` y las DLL
—lo único que Windows bloquea de verdad— no se tocan nunca. Los ``.py`` no
quedan bloqueados después de importarse: se reemplazan en caliente y el
reinicio carga el código nuevo.

Es lo mismo que lleva haciendo la estrategia de git todo el día.

## Se despliega solo lo que está completo

Se descarga entero a un temporal, se comprueba que es un zip legible y que
trae lo que tiene que traer, y **solo entonces** se copia. Un corte de red a
mitad deja el disco del cliente exactamente como estaba.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Optional

from lightrag.api.bimnemo.reparto import sobra_en_cliente
from lightrag.utils import logger

#: Cuánto se espera a GitHub. Generoso: aquí sí se descarga de verdad.
TIMEOUT_DESCARGA = 300.0
TIMEOUT_CONSULTA = 10.0

#: Señas de que el zip es lo que decimos. Si faltan, no se despliega nada.
SENALES = ("pyproject.toml", "lightrag")


def _pedir_json(url: str) -> Optional[dict[str, Any]]:
    peticion = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "BIMNEMO"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_CONSULTA) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.debug("BIMNEMO: no se pudo consultar GitHub: %s", exc)
        return None


def numeros(version: str) -> Optional[tuple[int, ...]]:
    """``v1.4.0-nativa`` → ``(1, 4, 0)``. ``None`` si no es una versión.

    El sufijo tras el guion se ignora al ordenar: ``1.4.0-nativa`` y
    ``1.4.0`` son la misma versión para decidir si hay otra más nueva.
    """
    limpio = (version or "").strip().lstrip("vV").split("-", 1)[0]
    partes = limpio.split(".")
    if not limpio or not all(p.isdigit() for p in partes):
        return None
    return tuple(int(p) for p in partes)


def es_mas_nueva(publicada: str, instalada: str) -> bool:
    """¿Es ``publicada`` posterior a ``instalada``?

    **No vale con que sean distintas.** Comparando con ``!=``, quien tenía la
    1.4 veía la 1.2.3 publicada como «versión nueva» y la actualización le
    devolvía a una versión vieja —la de la interfaz web—. Si alguna de las dos
    no se entiende como versión, se contesta que no: ofrecer una
    actualización dudosa es peor que no ofrecer ninguna.
    """
    a, b = numeros(publicada), numeros(instalada)
    if a is None or b is None:
        return False
    largo = max(len(a), len(b))
    return a + (0,) * (largo - len(a)) > b + (0,) * (largo - len(b))


def ultima_version(repo: str) -> Optional[dict[str, Any]]:
    """La última versión publicada, o ``None`` si no se pudo preguntar."""
    return _pedir_json(f"https://api.github.com/repos/{repo}/releases/latest")


def version_instalada(raiz: Path) -> Optional[str]:
    """Lo que dice el fichero ``VERSION``, que escribe el instalador."""
    fichero = raiz / "VERSION"
    try:
        texto = fichero.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return texto or None


def escribir_version(raiz: Path, version: str) -> None:
    (raiz / "VERSION").write_text(version.strip() + "\n", encoding="utf-8")


def _descargar(url: str, destino: Path) -> bool:
    peticion = urllib.request.Request(url, headers={"User-Agent": "BIMNEMO"})
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_DESCARGA) as r:
            with destino.open("wb") as salida:
                shutil.copyfileobj(r, salida)
        return True
    except (urllib.error.URLError, OSError) as exc:
        logger.error("BIMNEMO: falló la descarga de la versión: %s", exc)
        return False


def _raiz_del_zip(zf: zipfile.ZipFile) -> Optional[str]:
    """La carpeta que GitHub mete por encima de todo, p. ej. ``CMEDUCATIVA-BIMNEMO-a1b2c3/``.

    Devuelve ``None`` si el zip no tiene la forma esperada: mejor no desplegar
    que desplegar mal.
    """
    nombres = zf.namelist()
    if not nombres:
        return None
    primera = nombres[0].split("/")[0]
    if not primera or any(not n.startswith(primera + "/") for n in nombres):
        return None
    return primera


def _es_lo_que_decimos(zf: zipfile.ZipFile, raiz_zip: str) -> bool:
    dentro = {n[len(raiz_zip) + 1 :].split("/")[0] for n in zf.namelist()}
    return all(s in dentro for s in SENALES)


def desplegar(zip_path: Path, destino: Path) -> tuple[bool, str]:
    """Copia el contenido del paquete sobre la instalación.

    Solo escribe lo que el paquete trae. Lo que no viene —datos del usuario,
    entorno virtual— ni se mira.
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            raiz_zip = _raiz_del_zip(zf)
            if raiz_zip is None:
                return False, "El paquete no tiene la forma esperada."
            if not _es_lo_que_decimos(zf, raiz_zip):
                return False, "El paquete no parece una versión de BIMNEMO."

            with tempfile.TemporaryDirectory(prefix="bimnemo-upd-") as tmp:
                # Solo se extrae lo que le toca al cliente. El zip trae el
                # repositorio entero —pruebas, despliegues de Kubernetes,
                # ficheros de Docker— y sin este filtro la primera
                # actualización volvería a llenar una carpeta que el
                # instalador había dejado limpia.
                miembros = [
                    n for n in zf.namelist()
                    if not sobra_en_cliente(n[len(raiz_zip) + 1 :])
                ]
                zf.extractall(tmp, members=miembros)
                origen = Path(tmp) / raiz_zip
                # `dirs_exist_ok` reemplaza fichero a fichero sin borrar antes:
                # si algo falla a mitad, lo peor que queda es una instalación
                # mezclada, no una vacía.
                shutil.copytree(origen, destino, dirs_exist_ok=True)
        return True, "Desplegado."
    except (zipfile.BadZipFile, OSError) as exc:
        return False, f"No se pudo desplegar el paquete: {exc}"


def traer(repo: str, raiz: Path) -> dict[str, Any]:
    """Descarga la última versión publicada y la despliega.

    **No reinicia el motor**: quien llama decide cuándo morir, porque el
    reinicio tiene su propia maquinaria y duplicarla aquí sería tener dos.
    """
    version = ultima_version(repo)
    if version is None:
        return {"ok": False, "reason": "github", "message": "No se pudo consultar GitHub."}

    etiqueta = version.get("tag_name") or ""
    url = version.get("zipball_url")
    if not etiqueta or not url:
        return {"ok": False, "reason": "release", "message": "La versión publicada está incompleta."}

    # Segunda barrera, aquí y no solo en la pantalla: este es el sitio que
    # escribe en disco, y bajar de versión encima de una instalación mezcla
    # ficheros de dos épocas distintas.
    instalada = version_instalada(raiz) or ""
    if not es_mas_nueva(etiqueta, instalada):
        return {
            "ok": False,
            "reason": "older",
            "message": (
                f"La versión publicada ({etiqueta}) no es más nueva que la "
                f"instalada ({instalada or 'desconocida'})."
            ),
        }

    with tempfile.TemporaryDirectory(prefix="bimnemo-zip-") as tmp:
        paquete = Path(tmp) / "bimnemo.zip"
        if not _descargar(url, paquete):
            return {
                "ok": False,
                "reason": "download",
                "message": "No se pudo descargar la versión. Comprueba la conexión.",
            }

        ok, mensaje = desplegar(paquete, raiz)
        if not ok:
            return {"ok": False, "reason": "deploy", "message": mensaje}

    escribir_version(raiz, etiqueta)
    logger.info("BIMNEMO: desplegada la versión %s", etiqueta)
    return {"ok": True, "installed": etiqueta}


def pyproject_cambio(raiz: Path, antes: Optional[bytes]) -> bool:
    """¿Cambió ``pyproject.toml`` con el despliegue?

    Se compara el contenido de antes con el de ahora en vez de mirar fechas:
    copiar un fichero idéntico también cambia su fecha, y correr `pip` por eso
    añadiría un minuto a cada actualización para no hacer nada.
    """
    if antes is None:
        return True
    try:
        return (raiz / "pyproject.toml").read_bytes() != antes
    except OSError:
        return True


def leer_pyproject(raiz: Path) -> Optional[bytes]:
    try:
        return (raiz / "pyproject.toml").read_bytes()
    except OSError:
        return None


def python_del_entorno(raiz: Path) -> str:
    """El intérprete del `.venv` instalado, o el que está corriendo.

    En una instalación de cliente `sys.executable` ya es el del `.venv`, pero
    no cuando BIMNEMO se arranca de otra forma; preferir el del `.venv` evita
    instalar las dependencias en el Python equivocado.
    """
    import sys

    # El instalador trae un Python portable en `python/`; una copia clonada
    # para desarrollar, un entorno virtual. Se mira el portable primero porque
    # es el caso del cliente, que es quien usa esto.
    for candidato in (
        raiz / "python" / "python.exe",
        raiz / ".venv" / "Scripts" / "python.exe",
        raiz / ".venv" / "bin" / "python",
    ):
        if candidato.is_file():
            return str(candidato)
    return sys.executable


__all__ = [
    "desplegar",
    "es_mas_nueva",
    "numeros",
    "escribir_version",
    "leer_pyproject",
    "python_del_entorno",
    "pyproject_cambio",
    "traer",
    "ultima_version",
    "version_instalada",
]
