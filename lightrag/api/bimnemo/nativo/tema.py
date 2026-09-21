"""Los colores de BIMNEMO, para la ventana nativa.

**No hay ningún color inventado aquí.** Todos salen de
``lightrag/api/bimnemo/ui/css/tokens.css``, que es de donde los toma la
interfaz web. La ventana nativa y la web tienen que ser el mismo producto, y
la única forma de que no se separen con el tiempo es que compartan la tabla.

Se escribe como una hoja de estilo de Qt (`QSS`) generada desde esa tabla y
no a mano widget por widget: un color a mano es un color que un día se queda
viejo y nadie encuentra.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Paleta:
    """Un tema completo. Los nombres son los de `tokens.css`."""

    azul: str
    azul_hover: str
    azul_suave: str

    fondo: str
    elevada: str
    secundaria: str
    terciaria: str

    texto: str
    texto_2: str
    texto_3: str

    borde: str
    borde_medio: str

    #: Para el texto que va **encima** del azul.
    sobre_azul: str = "#ffffff"


CLARO = Paleta(
    azul="#2563eb",
    azul_hover="#1d4ed8",
    azul_suave="rgba(37, 99, 235, 0.10)",
    fondo="#ffffff",
    elevada="#f8fafc",
    secundaria="#f1f5f9",
    terciaria="#e2e8f0",
    texto="#0f172a",
    texto_2="#334155",
    texto_3="#64748b",
    borde="#e2e8f0",
    borde_medio="#cbd5e1",
)

OSCURO = Paleta(
    azul="#3b82f6",
    azul_hover="#60a5fa",
    azul_suave="rgba(59, 130, 246, 0.16)",
    fondo="#020617",
    elevada="#0f172a",
    secundaria="#1e293b",
    terciaria="#334155",
    texto="#f1f5f9",
    texto_2="#cbd5e1",
    texto_3="#94a3b8",
    borde="#1e293b",
    borde_medio="#334155",
)

#: Medidas. Las mismas proporciones que la interfaz web.
ANCHO_LATERAL = 232
ALTO_BARRA = 56
RADIO = 8


def hoja(p: Paleta) -> str:
    """La hoja de estilo de Qt para una paleta.

    Se apoya en los nombres de objeto (`setObjectName`) en vez de en la clase
    del widget: así dos `QFrame` con papeles distintos pueden verse distinto
    sin heredar ni inventar subclases para cambiar un color.
    """
    return f"""
    QWidget {{
        background: {p.fondo};
        color: {p.texto};
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 13px;
    }}

    /* Las etiquetas no pintan fondo. Sin esto heredan el general y, encima
       de la barra o del lateral —que son de otro color—, dejan recuadros
       oscuros alrededor de cada texto. */
    QLabel {{ background: transparent; }}

    /* --- Barra superior ------------------------------------------------ */
    #barra {{
        background: {p.elevada};
        border-bottom: 1px solid {p.borde};
    }}
    /* La marca sí lleva fondo: es el cuadrado azul. Va después de la regla
       de `QLabel` para ganarle. */
    QLabel#marca {{
        background: {p.azul};
        border-radius: 6px;
    }}
    #nombre {{
        color: {p.texto};
        font-size: 15px;
        font-weight: 600;
    }}
    #lema {{
        color: {p.texto_3};
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}

    /* --- Navegación lateral -------------------------------------------- */
    #lateral {{
        background: {p.elevada};
        border-right: 1px solid {p.borde};
    }}
    #rotulo {{
        color: {p.texto_3};
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding: 16px 16px 6px 16px;
    }}
    QPushButton#nav {{
        background: transparent;
        border: none;
        border-radius: {RADIO}px;
        color: {p.texto_2};
        padding: 9px 12px;
        text-align: left;
    }}
    QPushButton#nav:hover {{
        background: {p.secundaria};
        color: {p.texto};
    }}
    QPushButton#nav:checked {{
        background: {p.azul_suave};
        color: {p.azul};
        font-weight: 600;
    }}
    #version {{
        color: {p.texto_3};
        font-size: 11px;
        padding: 10px 16px;
    }}

    /* --- Contenido ------------------------------------------------------ */
    #titulo {{
        color: {p.texto};
        font-size: 24px;
        font-weight: 600;
    }}
    #descripcion {{
        color: {p.texto_3};
        font-size: 13px;
    }}
    #tarjeta {{
        background: {p.elevada};
        border: 1px solid {p.borde};
        border-radius: 12px;
    }}

    /* --- Controles ------------------------------------------------------ */
    QPushButton {{
        background: {p.secundaria};
        border: 1px solid {p.borde_medio};
        border-radius: {RADIO}px;
        color: {p.texto};
        padding: 7px 14px;
    }}
    QPushButton:hover {{ background: {p.terciaria}; }}
    QPushButton#principal {{
        background: {p.azul};
        border-color: {p.azul};
        color: {p.sobre_azul};
        font-weight: 600;
    }}
    QPushButton#principal:hover {{ background: {p.azul_hover}; }}
    QPushButton#peligro {{
        background: transparent;
        border-color: #dc2626;
        color: #ef4444;
    }}
    QPushButton#peligro:hover {{ background: rgba(220, 38, 38, 0.12); }}

    QComboBox, QLineEdit {{
        background: {p.fondo};
        border: 1px solid {p.borde_medio};
        border-radius: {RADIO}px;
        padding: 6px 10px;
        color: {p.texto};
    }}
    QComboBox:focus, QLineEdit:focus {{ border-color: {p.azul}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}

    QScrollBar:vertical {{
        background: transparent; width: 10px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {p.terciaria}; border-radius: 5px; min-height: 30px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    """
