"""Los textos que la pantalla «API» genera: ejemplos e instrucciones.

Todos salen del manifiesto y de las rutas ya resueltas para la memoria
abierta. **Ninguno está escrito a mano con una ruta fija dentro**, y ese es
el punto: un ejemplo que dice `/bimnemo/memory/search` mientras hay abierta
«Obra Sur» funciona al pegarlo y lee otra memoria. Devolver lo que no es,
sin fallar, es peor que fallar.
"""

from __future__ import annotations

import json
from typing import Any


def ejemplo_curl(base: str, rutas: dict[str, str], clave: str = "") -> str:
    """Una llamada de ejemplo, lista para pegar en una terminal."""
    cabecera = f' \\\n  -H "X-API-Key: {clave}"' if clave else ""
    cuerpo = json.dumps(
        {"query": "¿Qué acuerdos se tomaron?", "mode": "mix"},
        ensure_ascii=False,
    )
    return (
        f'curl -X POST "{base}{rutas["buscar"]}" \\\n'
        f'  -H "Content-Type: application/json"{cabecera} \\\n'
        f"  -d '{cuerpo}'"
    )


def ejemplo_python(base: str, rutas: dict[str, str], clave: str = "") -> str:
    """Lo mismo en Python, que es como lo llamará un agente."""
    cabeceras = '{"Content-Type": "application/json"'
    if clave:
        cabeceras += f', "X-API-Key": "{clave}"'
    cabeceras += "}"

    return (
        "import requests\n\n"
        f'BASE = "{base}"\n\n'
        "respuesta = requests.post(\n"
        f'    BASE + "{rutas["buscar"]}",\n'
        f"    headers={cabeceras},\n"
        '    json={"query": "¿Qué acuerdos se tomaron?", "mode": "mix"},\n'
        "    timeout=120,\n"
        ")\n"
        "print(respuesta.json())"
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
    """
    lineas = [
        "# BIMNEMO — memoria de conocimiento local",
        "",
        f"Dirección: {base}",
        f"Memoria abierta: {memoria or 'la de por defecto'}",
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
                    "    cuerpo: " + json.dumps(fila["body"], ensure_ascii=False)
                )
        lineas.append("")

    lineas.append("## Modos de recuperación")
    for nombre, explicacion in modos.items():
        lineas.append(f"- {nombre}: {explicacion}")
    return "\n".join(lineas)


__all__ = ["ejemplo_curl", "ejemplo_python", "instrucciones"]
