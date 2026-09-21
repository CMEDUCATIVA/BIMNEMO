"""Publica una versión de BIMNEMO en GitHub, con o sin instalador adjunto.

    .venv\\Scripts\\python.exe scripts/release/publicar.py v1.4.5 notas.md
    .venv\\Scripts\\python.exe scripts/release/publicar.py v1.4.5 notas.md installer\\salida\\BIMNEMO-1.4.5-instalador.exe

Antes hay que haber subido la etiqueta (`git push origin main vX.Y.Z`): la
versión se crea sobre una etiqueta que ya exista en GitHub.

## La credencial

Es la que git ya guarda para subir (el administrador de credenciales de
Windows). Se le pide a git en memoria con ``git credential fill`` y **no se
escribe ni se imprime en ningún sitio**. No hay token en este fichero ni en
ningún `.env`: el repositorio es público.

## Por qué Python y no `curl`

En esta máquina `curl` falló dos veces con `HTTP 000` subiendo el instalador
(~96 MB) a GitHub. `urllib` con un plazo largo no ha fallado nunca.

Ver `como_actualizar.md`, apartado «Publicar una versión».
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "CMEDUCATIVA/BIMNEMO"


def _credencial() -> str:
    salida = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for linea in salida.splitlines():
        if linea.startswith("password="):
            return linea.split("=", 1)[1]
    raise SystemExit("git no tiene guardada ninguna credencial de GitHub.")


def _pedir(token: str, url: str, datos: bytes | None = None, tipo: str = "application/json"):
    peticion = urllib.request.Request(
        url,
        data=datos,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "BIMNEMO",
            "Content-Type": tipo,
        },
    )
    with urllib.request.urlopen(peticion, timeout=900) as respuesta:
        return json.loads(respuesta.read() or b"null")


def main(argumentos: list[str]) -> int:
    if len(argumentos) < 2:
        print(__doc__)
        return 2
    etiqueta = argumentos[0]
    notas = Path(argumentos[1]).read_text(encoding="utf-8")
    instalador = Path(argumentos[2]) if len(argumentos) > 2 else None

    token = _credencial()
    version = _pedir(
        token,
        f"https://api.github.com/repos/{REPO}/releases",
        json.dumps(
            {
                "tag_name": etiqueta,
                "name": f"BIMNEMO {etiqueta}",
                "body": notas,
                # Ni borrador ni preliminar: `releases/latest`, que es lo que
                # consultan los clientes, no ve ninguna de las dos cosas.
                "draft": False,
                "prerelease": False,
            }
        ).encode("utf-8"),
    )
    print("publicada:", version["html_url"])

    if instalador:
        subida = version["upload_url"].split("{")[0] + f"?name={instalador.name}"
        adjunto = _pedir(
            token,
            subida,
            instalador.read_bytes(),
            "application/vnd.microsoft.portable-executable",
        )
        print("instalador adjunto:", adjunto["name"], adjunto["size"], "bytes")

    ultima = _pedir(token, f"https://api.github.com/repos/{REPO}/releases/latest")
    print("la última publicada es ahora:", ultima["tag_name"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
