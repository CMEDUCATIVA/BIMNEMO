"""Dibuja el icono de BIMNEMO y lo deja en ``installer/bimnemo.ico``.

El icono **no se inventa**: es la misma marca que lleva la aplicación en su
encabezado —el cuadrado azul con el glifo `network`— copiada de donde ya
estaba definida, para que lo que se ve en la barra de tareas y lo que se ve
dentro del programa sean la misma cosa.

    color   `--oe-blue` de `ui/css/tokens.css`
    glifo   `icons.js`, entrada `network`, rejilla de 24×24

El `.ico` resultante **sí** se versiona —el instalador lo necesita para
compilar y no puede depender de que alguien se acuerde de generarlo— pero se
genera desde aquí para que se pueda rehacer: cambiar el color de marca y
volver a lanzarlo es un segundo. El binario en git es el resultado, no la
fuente; la fuente es este fichero.

Uso:

    python scripts/release/icono.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "installer" / "bimnemo.ico"

#: El azul de la marca, de `--oe-blue` en el tema claro.
AZUL = (37, 99, 235, 255)
BLANCO = (255, 255, 255, 255)

#: Se dibuja grande y se reduce: a 16 píxeles, dibujar directamente deja el
#: trazo hecho trizas, mientras que reducir con Lanczos lo conserva legible.
LADO = 1024

#: Los tamaños que Windows pide en cada sitio: 16 en la barra de título y el
#: Administrador de tareas, 32 en el escritorio, 256 en la vista de iconos
#: grandes del Explorador.
TAMANOS = (16, 24, 32, 48, 64, 128, 256)

#: Proporción del glifo dentro del cuadrado. Por debajo de 0.55 se ve
#: perdido; por encima de 0.65 toca las esquinas redondeadas.
PROPORCION_GLIFO = 0.58

#: Radio del cuadrado, en proporción al lado. Es el mismo aire que tiene
#: `--radius-md` sobre la marca de 1.75rem del encabezado.
RADIO = 0.22


def _dibujar(lado: int):
    """El icono a tamaño completo, sobre fondo transparente."""
    from PIL import Image, ImageDraw

    lienzo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    pincel = ImageDraw.Draw(lienzo)

    pincel.rounded_rectangle(
        (0, 0, lado - 1, lado - 1), radius=int(lado * RADIO), fill=AZUL
    )

    # El glifo viene de una rejilla de 24×24, que es el `viewBox` del SVG.
    escala = lado * PROPORCION_GLIFO / 24.0
    margen = (lado - 24 * escala) / 2.0
    grosor = max(1, int(round(2 * escala)))  # `stroke-width: 2`

    def p(x: float, y: float) -> tuple[float, float]:
        return (margen + x * escala, margen + y * escala)

    # Las tres cajas: dos abajo y una arriba.
    for x, y in ((16, 16), (2, 16), (9, 2)):
        pincel.rounded_rectangle(
            (p(x, y), p(x + 6, y + 6)),
            radius=escala,
            outline=BLANCO,
            width=grosor,
        )

    # El bus que une la caja de arriba con las dos de abajo. En el SVG son
    # curvas de radio 1; a este tamaño una polilínea con uniones redondeadas
    # es indistinguible, y no hay que calcular arcos.
    pincel.line(
        [p(5, 16), p(5, 12), p(19, 12), p(19, 16)],
        fill=BLANCO,
        width=grosor,
        joint="curve",
    )
    pincel.line([p(12, 12), p(12, 8)], fill=BLANCO, width=grosor)

    # `joint="curve"` redondea las uniones pero **no los extremos**, que
    # quedan cortados a escuadra y se notan. Se rematan a mano.
    radio = grosor / 2.0
    for punto in (p(5, 16), p(19, 16), p(12, 12), p(12, 8)):
        x, y = punto
        pincel.ellipse((x - radio, y - radio, x + radio, y + radio), fill=BLANCO)

    return lienzo


def generar(destino: Path = DESTINO) -> Path:
    """Escribe el `.ico` con todos los tamaños dentro."""
    from PIL import Image

    grande = _dibujar(LADO)
    # Se reduce una vez por tamaño con Lanczos en vez de dejar que el
    # escritor del `.ico` lo haga con su remuestreo por defecto, que a 16
    # píxeles deja el trazo sucio.
    capas = [
        grande.resize((lado, lado), Image.Resampling.LANCZOS) for lado in TAMANOS
    ]

    destino.parent.mkdir(parents=True, exist_ok=True)
    medidas = [(lado, lado) for lado in TAMANOS]

    # La imagen base tiene que ser **la mayor**. Pillow nunca amplía: si se
    # le da la de 16 como base, descarta en silencio todos los tamaños por
    # encima y escribe un `.ico` de un solo icono diminuto que en el
    # escritorio se ve borroso.
    try:
        capas[-1].save(
            destino, format="ICO", sizes=medidas, append_images=capas[:-1]
        )
    except (TypeError, ValueError):
        # Pillow antiguo: sin `append_images` reduce él solo desde el mayor.
        capas[-1].save(destino, format="ICO", sizes=medidas)
    return destino


def main() -> int:
    try:
        import PIL  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Hace falta Pillow para dibujar el icono:\n"
            "    .venv\\Scripts\\python.exe -m pip install pillow"
        )

    ruta = generar()
    print(f"Icono escrito en {ruta}")
    print(f"  tamaños  {', '.join(str(t) for t in TAMANOS)}")
    print(f"  {ruta.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
