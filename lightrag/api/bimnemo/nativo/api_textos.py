"""Los textos que la pantalla «API» genera: ejemplos e instrucciones.

Todos salen del manifiesto y de las rutas ya resueltas para la memoria
abierta. **Ninguno está escrito a mano con una ruta fija dentro**, y ese es
el punto: un ejemplo que dice `/bimnemo/memory/search` mientras hay abierta
«Obra Sur» funciona al pegarlo y lee otra memoria. Devolver lo que no es,
sin fallar, es peor que fallar.

Los valores de ejemplo —la pregunta, lo que se recuerda— son los mismos que
el manifiesto trae en los cuerpos, y por tanto los mismos que la web. Dos
juegos de ejemplos acaban discrepando, y el que discrepa sin que nadie lo
note es justo el que alguien pegó una vez en una skill.
"""

from __future__ import annotations

import json
from typing import Any

from lightrag.api.bimnemo.manifiesto import PREGUNTA, RECUERDO


def ejemplo_curl(base: str, rutas: dict[str, str], clave: str = "") -> str:
    """Una llamada de ejemplo, lista para pegar en una terminal."""
    cabecera = f'\n  -H "X-API-Key: {clave}" \\' if clave else ""
    cuerpo = json.dumps({"query": PREGUNTA, "mode": "mix"}, ensure_ascii=False)
    return (
        f'curl -X POST "{base}{rutas["buscar"]}" \\{cabecera}\n'
        f'  -H "Content-Type: application/json" \\\n'
        f"  -d '{cuerpo}'"
    )


def ejemplo_python(base: str, rutas: dict[str, str], clave: str = "") -> str:
    """Lo mismo en Python, que es como lo llamará un agente.

    Van las dos mitades —recuperar y guardar— porque son las dos cosas que
    hace una memoria. Con solo la consulta, `remember` queda como una línea
    de una tabla que nadie prueba.
    """
    cabeceras = f'\n    headers={{"X-API-Key": "{clave}"}},' if clave else ""
    buscar = json.dumps({"query": PREGUNTA, "mode": "mix"}, ensure_ascii=False)
    guardar = json.dumps(
        {"text": RECUERDO, "source": "acta-2026-09"}, ensure_ascii=False
    )
    return (
        "import httpx\n\n"
        "# Recuperar contexto SIN gastar el LLM que redacta.\n"
        "respuesta = httpx.post(\n"
        f'    "{base}{rutas["buscar"]}",{cabeceras}\n'
        f"    json={buscar},\n"
        "    timeout=120,\n"
        ")\n"
        'contexto = respuesta.json()["context"]\n\n'
        "# Guardar algo nuevo en la memoria.\n"
        "httpx.post(\n"
        f'    "{base}{rutas["recordar"]}",{cabeceras}\n'
        f"    json={guardar},\n"
        "    timeout=60,\n"
        ")"
    )


def instrucciones(
    base: str,
    memoria: str,
    paneles: list[tuple[str, str, list[dict[str, Any]]]],
    modos: dict[str, str],
    clave: str = "",
) -> str:
    """Todo lo que una IA necesita para usar esta memoria, en texto.

    Se genera de lo que hay en pantalla, así que dice **las rutas de la
    memoria abierta**, no las plantillas del manifiesto. Si mañana hay un
    endpoint más, aparece aquí solo.

    El cuerpo de cada llamada sí va aquí —al revés que en la tabla, donde
    estorbaba—. Quien lee esto es un modelo que tiene que escribir la
    petición entera sin poder preguntar: saber que existe `remember` no le
    dice **qué** mandarle, y sin esa línea acaba en Swagger o inventándoselo.
    """
    lineas = [
        "# BIMNEMO — memoria de conocimiento local",
        "",
        f"Dirección: {base}",
        f"Memoria abierta: {memoria or 'la de por defecto'}",
        "Las rutas de abajo ya apuntan a ella: úsalas tal cual, sin sustituir nada.",
        "Todas las peticiones con cuerpo van en JSON.",
    ]
    if clave:
        lineas.append(f"Cabecera obligatoria: X-API-Key: {clave}")
    else:
        lineas.append(
            "Sin autenticación: cualquier programa de esta máquina puede usarla."
        )
    lineas.append("")

    for _clave, titulo, filas in paneles:
        lineas.append(f"## {titulo}")
        for fila in filas:
            lineas.append(f"{fila.get('method')} {base}{fila.get('ruta')}")
            lineas.append(f"    {fila.get('purpose')}")
            if fila.get("body"):
                lineas.append(
                    "    cuerpo JSON: "
                    + json.dumps(fila["body"], ensure_ascii=False)
                )
        lineas.append("")

    lineas.append("## Modos de recuperación")
    for nombre, explicacion in modos.items():
        lineas.append(f"- {nombre}: {explicacion}")
    return "\n".join(lineas)


__all__ = ["ejemplo_curl", "ejemplo_python", "instrucciones"]
