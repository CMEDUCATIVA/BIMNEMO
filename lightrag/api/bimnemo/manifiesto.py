"""Qué le contamos a una IA que quiere usar esta memoria.

Es **datos, no rutas**: la lista de endpoints que el manifiesto publica, con
para qué sirve cada uno y qué cuerpo espera. Vive aparte de
``bimnemo_routes.py`` porque aquél ya rozaba el tope de líneas y porque esto
se toca por un motivo distinto —añadir una capacidad— que el fichero de rutas.

## Por qué existe la lista, y por qué no son todos

El servidor expone **32** rutas de BIMNEMO/NEMO. Aquí no están todas, y la
ausencia es deliberada.

Fuera quedan ``/bimnemo/restart``, ``/bimnemo/settings``, ``/bimnemo/access``,
``DELETE /bimnemo/nemos/{id}``, ``providers``, ``catalog``, ``engine`` y
``app-build``. Eso no es la memoria: es **el panel de mandos de la
aplicación**. Anunciárselo a un agente sería invitarle a reiniciar el motor,
cambiarte el proveedor o borrar una memoria entera porque le pareció
razonable. Un agente que se equivoca borrando un documento pierde un
documento; borrando una memoria pierde el trabajo de meses.

Siguen existiendo y están en Swagger. Lo que se decide aquí es a qué se le da
publicidad en el descriptor que lee una IA.

## Los grupos

``consultar`` · ``explorar`` · ``guardar`` · ``borrar``. Sirven para dos
cosas: agrupar el texto que el usuario copia en su skill, y dejar a la vista
qué está concediendo al pegarlo.

## El cuerpo de ejemplo

Saber que existe ``/nemo/{nemo}/memory/remember`` no dice **qué** hay que
mandarle. Sin el cuerpo, el manifiesto no ahorra ir a Swagger — que es la
única razón por la que existe.
"""

from __future__ import annotations

from typing import Any

#: Endpoints que el manifiesto publica, en el orden en que se leen bien.
#:
#: Cada entrada lleva ``group`` para agruparla y ``body`` con el cuerpo mínimo
#: que hay que mandar (``None`` cuando no lleva cuerpo).
ENDPOINTS: list[dict[str, Any]] = [
    # -- Consultar ---------------------------------------------------------
    {
        "method": "POST",
        "path": "/bimnemo/memory/search",
        "group": "consultar",
        "scope": "esta",
        "purpose": (
            "Recuperar contexto de la memoria activa SIN generar respuesta. "
            "No gasta el LLM que redacta: es lo que quiere un agente que ya "
            "tiene su propio modelo."
        ),
        "body": {"query": "<la pregunta>", "mode": "mix"},
    },
    {
        "method": "POST",
        "path": "/nemo/{nemo}/memory/search",
        "group": "consultar",
        "scope": "esta",
        "purpose": (
            "Recuperar contexto de esta memoria SIN generar respuesta. No "
            "gasta el LLM que redacta: es lo que quiere un agente que ya tiene "
            "su propio modelo."
        ),
        "body": {"query": "<la pregunta>", "mode": "mix"},
    },
    {
        "method": "POST",
        "path": "/bimnemo/memory/search-all",
        "group": "consultar",
        "scope": "todas",
        "purpose": (
            "Buscar en TODAS las memorias a la vez. Útil cuando no se sabe en "
            "cuál está la respuesta."
        ),
        "body": {"query": "<la pregunta>", "mode": "mix"},
    },
    {
        "method": "POST",
        "path": "/bimnemo/memory/ask-all",
        "group": "consultar",
        "scope": "todas",
        "purpose": "Preguntar a todas las memorias y que el motor redacte la respuesta.",
        "body": {"query": "<la pregunta>", "mode": "mix"},
    },
    {
        "method": "POST",
        "path": "/query",
        "group": "consultar",
        "scope": "motor",
        "purpose": "Pregunta y respuesta completa generada por el motor (gasta LLM).",
        "body": {"query": "<la pregunta>", "mode": "mix"},
    },
    {
        "method": "POST",
        "path": "/query/stream",
        "group": "consultar",
        "scope": "motor",
        "purpose": "Igual que /query, en streaming NDJSON.",
        "body": {"query": "<la pregunta>", "mode": "mix"},
    },
    # -- Explorar ----------------------------------------------------------
    {
        "method": "GET",
        "path": "/bimnemo/nemos",
        "group": "explorar",
        "scope": "todas",
        "purpose": (
            "Qué memorias existen, con el identificador de cada una. Se pide "
            "para trabajar con una memoria distinta de la de estas rutas."
        ),
        "body": None,
    },
    {
        "method": "GET",
        "path": "/bimnemo/stats",
        "group": "explorar",
        "scope": "esta",
        "purpose": "Qué hay almacenado: archivos, tamaño, categorías, fragmentos.",
        "body": None,
    },
    {
        "method": "GET",
        "path": "/bimnemo/files",
        "group": "explorar",
        "scope": "esta",
        "purpose": (
            "Los documentos de esta memoria, con su estado y su doc_id. El "
            "doc_id es lo que hace falta para borrar."
        ),
        "body": None,
    },
    {
        "method": "GET",
        "path": "/bimnemo/graph",
        "group": "explorar",
        "scope": "esta",
        "purpose": "Entidades y relaciones del grafo. Acepta ?label=, ?max_depth=, ?max_nodes=.",
        "body": None,
    },
    # -- Guardar -----------------------------------------------------------
    {
        "method": "POST",
        "path": "/bimnemo/memory/remember",
        "group": "guardar",
        "scope": "esta",
        "purpose": "Guardar un texto en la memoria activa. Se indexa como un documento más.",
        "body": {"text": "<lo que hay que recordar>", "source": "<de dónde sale>"},
    },
    {
        "method": "POST",
        "path": "/nemo/{nemo}/memory/remember",
        "group": "guardar",
        "scope": "esta",
        "purpose": (
            "Guardar un texto en esta memoria. Se indexa como un documento más."
        ),
        "body": {"text": "<lo que hay que recordar>", "source": "<de dónde sale>"},
    },
    {
        "method": "POST",
        "path": "/nemo/{nemo}/documents/upload",
        "group": "guardar",
        "scope": "esta",
        "purpose": (
            "Subir un fichero a esta memoria. multipart/form-data con el campo "
            "`file`. Admite 41 formatos."
        ),
        "body": None,
    },
    # -- Borrar ------------------------------------------------------------
    {
        "method": "DELETE",
        "path": "/bimnemo/documents",
        "group": "borrar",
        "scope": "esta",
        "purpose": (
            "Borrar documentos de esta memoria CON lo que el motor aprendió de "
            "ellos: sus fragmentos y sus entidades. No se puede deshacer."
        ),
        "body": {"doc_ids": ["<doc_id>"], "delete_file": True},
    },
    {
        "method": "DELETE",
        "path": "/bimnemo/files",
        "group": "borrar",
        "scope": "esta",
        "purpose": "Borrar un archivo que todavía no llegó a indexarse. No afecta al grafo.",
        "body": None,
    },
]

#: Sobre qué actúa cada endpoint. Es el eje que ORDENA la vista, porque es lo
#: que hay que decidir al copiar una ruta: ¿esto toca la memoria que tengo
#: abierta, todas, o el motor?
#:
#: El grupo —consultar, guardar, borrar— se queda como etiqueta dentro de cada
#: ámbito: sigue siendo lo que le dice a un agente qué se le está permitiendo.
AMBITOS: dict[str, str] = {
    "esta": "Esta memoria",
    "todas": "Todas las memorias",
    "motor": "El motor",
}

#: Qué significa cada grupo, para quien lea la instrucción.
GRUPOS: dict[str, str] = {
    "consultar": "Leer la memoria",
    "explorar": "Saber qué hay dentro",
    "guardar": "Añadir a la memoria",
    "borrar": "Quitar de la memoria (no se puede deshacer)",
}

#: Modos de recuperación, con cuándo usar cada uno.
MODOS: dict[str, str] = {
    "mix": "Grafo + vectores. El recomendado, y el que viene por defecto.",
    "hybrid": "Combina local y global.",
    "local": "Entidades concretas y su contexto inmediato.",
    "global": "Relaciones y temas amplios.",
    "naive": "Solo búsqueda vectorial, sin grafo.",
}
