"""Qué del repositorio va al ordenador de un cliente y qué no.

BIMNEMO se construye dentro del repositorio de LightRAG, y hasta ahora el
paquete se armaba con todo lo que git versiona. El resultado era que al
cliente se le instalaba **una copia del repositorio de desarrollo**: al abrir
su carpeta encontraba `docker-compose.podman.yml`, `k8s-deploy\\`, 652
ficheros de pruebas, el código fuente de una interfaz que no usa y un
`CLAUDE.md`. Y en medio de todo eso, ningún fichero que se llamara BIMNEMO.

Esa es la lista de lo que sobra.

## Por qué vive aquí y no en el guion de empaquetado

Porque hay **dos caminos** por los que llegan ficheros a la máquina del
cliente, y los dos tienen que filtrar igual:

1. el instalador, que arma el paquete con `scripts/release/empaquetar.py`;
2. el actualizador, que se descarga el repositorio publicado y lo copia
   encima (`paquete.desplegar`).

Si solo filtrara el primero, la carpeta quedaría limpia al instalar y se
volvería a llenar con la primera actualización. Una lista en dos sitios es
una lista que un día discrepa.

## Criterio

Sobra lo que **solo sirve para desarrollar o desplegar en servidor**. En la
duda se queda: dejar un fichero de más es feo, quitar uno que hacía falta
rompe el programa en un ordenador al que no tenemos acceso.

Por eso siguen viajando cosas que podrían parecer prescindibles:

- ``pyproject.toml`` — el actualizador lo compara para saber si hay que
  instalar dependencias nuevas
- ``env.example`` — de ahí sale el `.env` en el primer arranque
- ``como_actualizar.md`` — tiene un acceso directo en el menú de inicio
- ``docs/`` — documentación del producto, que sí es para quien lo usa
"""

from __future__ import annotations

#: Carpetas de primer nivel que no pintan nada en una instalación.
CARPETAS = (
    ".claude",  # instrucciones para el asistente de programación
    ".clinerules",
    ".github",  # integración continua
    "assets",  # imágenes del README
    "README.assets",
    "examples",  # ejemplos de uso de la biblioteca
    "installer",  # el instalador no se instala a sí mismo
    "k8s-deploy",  # despliegue en Kubernetes
    "lightrag_webui",  # fuente de la interfaz de LightRAG; BIMNEMO usa la suya
    "prompts",  # plantillas de referencia, no se leen en ejecución
    "reproduce",  # guiones de reproducción de experimentos
    "scripts",  # herramientas de quien desarrolla
    "tests",  # 652 ficheros de pruebas
)

#: Ficheros sueltos de la raíz que son de desarrollo o de despliegue.
FICHEROS = (
    ".dockerignore",
    ".gitattributes",
    ".git-blame-ignore-revs",
    ".gitignore",
    ".pre-commit-config.yaml",
    "AGENTS.md",
    "CLAUDE.md",
    "Makefile",
    "MANIFEST.in",
    "SECURITY.md",
    "uv.lock",
    "env.docker-compose-full",
    "lightrag.service.example",  # unidad de systemd, para servidores Linux
    # Cómo se construye el instalador: es para quien mantiene BIMNEMO, no
    # para quien lo usa. (`como_actualizar.md` sí viaja: lo abre el acceso
    # «Cómo actualizar» del menú Inicio.)
    "instalador_bimnemo.md",
)

#: Por dónde empiezan los ficheros de Docker y los de dependencias fijadas.
#: Se filtran por prefijo porque son varios y aparecen otros con el tiempo.
PREFIJOS = (
    "docker",
    "Dockerfile",
    "requirements-offline",
    # `README-id.md`, `README-ja.md`, `README-zh.md`. El guion es lo que los
    # distingue del `README.md`, que sí se queda.
    "README-",
)


def sobra_en_cliente(relativo: str) -> bool:
    """¿Este fichero del repositorio se queda fuera de la instalación?

    ``relativo`` es la ruta dentro del repositorio, con barras normales o
    invertidas, tal como la dan tanto ``git ls-files`` como un `zip`.
    """
    ruta = relativo.replace("\\", "/").strip("/")
    if not ruta:
        return False

    partes = ruta.split("/")
    if partes[0] in CARPETAS:
        return True

    if len(partes) == 1:
        nombre = partes[0]
        if nombre in FICHEROS:
            return True
        if any(nombre.startswith(p) for p in PREFIJOS):
            return True

    return False


__all__ = ["CARPETAS", "FICHEROS", "PREFIJOS", "sobra_en_cliente"]
