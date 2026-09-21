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

from lightrag.api.bimnemo.nativo import iconos


@dataclass(frozen=True)
class Paleta:
    """Un tema completo. Los nombres son los de `tokens.css`."""

    azul: str
    azul_hover: str
    azul_suave: str
    #: El borde del recuadro de la memoria activa, en la barra.
    azul_borde: str

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
    azul_borde="rgba(37, 99, 235, 0.22)",
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
    azul_borde="rgba(59, 130, 246, 0.34)",
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

#: Los ocho colores de categoría del Lookbook, con su fondo suave al 12 %.
#: Son los `--cat-*` de `tokens.css`; la web los resuelve por `data-color` y
#: aquí se buscan por la misma clave que manda `GET /bimnemo/catalog`.
CATEGORIA: dict[str, tuple[str, str]] = {
    "sky": ("#0ea5e9", "rgba(14, 165, 233, 0.12)"),
    "violet": ("#8b5cf6", "rgba(139, 92, 246, 0.12)"),
    "emerald": ("#10b981", "rgba(16, 185, 129, 0.12)"),
    "orange": ("#f97316", "rgba(249, 115, 22, 0.12)"),
    "teal": ("#14b8a6", "rgba(20, 184, 166, 0.12)"),
    "rose": ("#f43f5e", "rgba(244, 63, 94, 0.12)"),
    "amber": ("#f59e0b", "rgba(245, 158, 11, 0.12)"),
    "slate": ("#64748b", "rgba(100, 116, 139, 0.12)"),
}

#: El azul de «trabajando», que comparten los tres estados en los que el
#: motor está leyendo el documento.
_OCUPADO = ("#0ea5e9", "rgba(14, 165, 233, 0.12)")

#: Estados con color propio. Los demás son neutros y dependen de la paleta,
#: así que se resuelven en `color_estado`.
_ESTADOS: dict[str, tuple[str, str]] = {
    "processed": ("#10b981", "rgba(16, 185, 129, 0.12)"),
    "failed": ("#ef4444", "rgba(239, 68, 68, 0.12)"),
    "pending": ("#f59e0b", "rgba(245, 158, 11, 0.12)"),
    "parsing": _OCUPADO,
    "analyzing": _OCUPADO,
    "processing": _OCUPADO,
}


#: La paleta en uso. La fija la ventana al arrancar.
#:
#: Existe porque hay colores que se eligen **en caliente** —la insignia de
#: estado cambia en cada fila de la tabla— y el widget que los elige no
#: recibe la paleta por ningún sitio: las pantallas se construyen con el
#: motor y nada más. La alternativa era un parámetro nuevo en el constructor
#: de cada pantalla para un dato que es el mismo en toda la ventana.
ACTUAL: Paleta = OSCURO


def usar(p: Paleta) -> None:
    """Fija la paleta en uso. La llama la ventana antes de montar nada."""
    global ACTUAL
    ACTUAL = p


def color_categoria(token: str) -> tuple[str, str]:
    """El par (color, fondo) de una categoría. Lo que no conozca, gris."""
    return CATEGORIA.get(token, CATEGORIA["slate"])


def color_estado(estado: str, p: Paleta | None = None) -> tuple[str, str]:
    """El par (color, fondo) de un estado del motor.

    «Borrando» va en gris a propósito, igual que en la web: no es un error
    ni un aviso, es trabajo en marcha que termina con la fila desapareciendo,
    y teñir la tabla de rojo por un borrado que el usuario acaba de pedir
    asusta sin motivo.
    """
    paleta = p or ACTUAL
    if estado in _ESTADOS:
        return _ESTADOS[estado]
    if estado == "deleting":
        return (paleta.texto_2, paleta.terciaria)
    return (paleta.texto_3, paleta.secundaria)


#: Medidas. Las mismas proporciones que la interfaz web.
ANCHO_LATERAL = 232

#: Ancho del carril cuando solo caben los iconos.
ANCHO_LATERAL_ESTRECHO = 60

#: Por debajo de este ancho de ventana, el carril se queda en iconos. Es el
#: punto en el que el contenido empieza a apretarse de verdad: con el carril
#: de 232 píxeles, una ventana de 1.100 deja menos de 870 para lo que importa.
ANCHO_VENTANA_CARRIL_ESTRECHO = 1180
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

    /* La memoria abierta y sus tres acciones van en un recuadro: es un
       grupo, no cuatro controles sueltos que se hubieran quedado juntos.
       El tinte azul lo separa de la marca sin subir el volumen. */
    #grupo-nemo {{
        background: {p.azul_suave};
        border: 1px solid {p.azul_borde};
        border-radius: 10px;
    }}
    /* Dentro del recuadro los botones no llevan borde propio: ya están
       contenidos, y con él el grupo parecía tres cajas dentro de otra. */
    #grupo-nemo QPushButton#icono {{
        background: transparent;
        border-color: transparent;
    }}
    #grupo-nemo QPushButton#icono:hover {{ background: {p.secundaria}; }}
    #grupo-nemo QPushButton#icono:disabled {{ border-color: transparent; }}
    /* El nombre de la memoria, en negrita: es el dato que manda sobre todo
       lo que se ve debajo. */
    #grupo-nemo QComboBox {{
        background: {p.fondo};
        font-weight: 600;
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
    /* Carril estrecho: el botón queda cuadrado, con el icono centrado y
       sin sitio que reservar para un rótulo que ya no está. */
    QPushButton#nav[estrecho="si"] {{
        padding: 9px 0;
        text-align: center;
    }}
    QLabel#nav-cuenta[estrecho="si"] {{
        font-size: 9px;
        padding: 0;
    }}
    QPushButton#nav:checked {{
        background: {p.azul_suave};
        color: {p.azul};
        font-weight: 600;
    }}
    /* El contador del carril: a la derecha del rótulo y en gris. Es un
       dato de apoyo, no compite con el nombre de la pantalla. */
    #nav-cuenta {{
        color: {p.texto_3};
        font-size: 11px;
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
    #subtitulo {{
        color: {p.texto};
        font-size: 15px;
        font-weight: 600;
    }}
    #cifra {{
        color: {p.texto};
        font-size: 26px;
        font-weight: 600;
    }}
    #dato-nombre {{ color: {p.texto_3}; }}
    #dato-valor  {{ color: {p.texto}; }}
    /* Las filas son cajas para colocar, no superficies. Sin esto pintan el
       fondo general **dentro** de la tarjeta y la dejan a rayas. */
    #fila {{ background: transparent; }}

    /* Los tres tonos del aviso. El color lo decide la propiedad `tono`, que
       la pieza cambia en caliente — por eso hay que repintar el estilo a
       mano después, cosa que `Aviso` ya hace. */
    #aviso {{
        border-radius: {RADIO}px;
        padding: 9px 12px;
    }}
    #aviso[tono="info"] {{
        background: {p.azul_suave};
        color: {p.azul};
    }}
    #aviso[tono="bien"] {{
        background: rgba(22, 163, 74, 0.16);
        color: #4ade80;
    }}
    #aviso[tono="mal"] {{
        background: rgba(220, 38, 38, 0.14);
        color: #f87171;
    }}

    QProgressBar {{
        background: {p.secundaria};
        border: none;
        border-radius: 3px;
    }}
    QProgressBar::chunk {{
        background: {p.azul};
        border-radius: 3px;
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
    QComboBox::drop-down {{ border: none; width: 26px; }}
    /* La flecha, con su fichero: en una hoja de Qt una imagen se pide con
       `url(...)`, y sin ella Qt no dibuja ninguna. Un desplegable sin
       flecha no se lee como un desplegable — parece una caja de texto. */
    QComboBox::down-arrow {{
        image: url({iconos.ruta_pintada("desplegar", 11, p.texto_3)});
        height: 11px;
        width: 11px;
    }}

    /* --- Panel y barra del grafo ---------------------------------------- */
    #rotulo-campo {{
        color: {p.texto_3};
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }}
    QPushButton#icono {{
        background: transparent;
        border: 1px solid {p.borde_medio};
        border-radius: {RADIO}px;
        padding: 0;
    }}
    /* El «+» de crear memoria: mismo tamaño que sus vecinos, pero azul.
       Es la acción que añade, y la única de la barra que crea algo. */
    QPushButton#principal-icono {{
        background: {p.azul};
        border: 1px solid {p.azul};
        border-radius: {RADIO}px;
        padding: 0;
    }}
    QPushButton#principal-icono:hover {{ background: {p.azul_hover}; }}
    QPushButton#icono:disabled {{
        border-color: {p.borde};
    }}
    QPushButton#icono:hover {{
        background: {p.secundaria};
        border-color: {p.azul};
    }}

    /* La ficha flotante sobre el lienzo del grafo. Lleva fondo propio y
       borde porque está **encima** del dibujo: sin ellos, el texto se
       mezclaría con los nodos y no se leería ninguno de los dos. */
    #ficha {{
        background: {p.elevada};
        border: 1px solid {p.borde_medio};
        border-radius: 10px;
    }}
    #ficha-nombre {{
        color: {p.texto};
        font-size: 14px;
        font-weight: 600;
    }}
    #ficha-tipo {{
        background: {p.azul_suave};
        border-radius: 5px;
        color: {p.azul};
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 0.8px;
        padding: 3px 8px;
    }}
    #ficha-texto {{ color: {p.texto_2}; }}
    QPushButton#ficha-cerrar {{
        background: transparent;
        border: none;
        border-radius: 12px;
        color: {p.texto_3};
        font-size: 13px;
        padding: 0;
    }}
    QPushButton#ficha-cerrar:hover {{
        background: {p.terciaria};
        color: {p.texto};
    }}

    /* El pie del grafo: leyenda y ayuda. Con fondo y un borde arriba para
       que se lea como pie y no como algo flotando sobre el lienzo. */
    /* **Un solo box.** El lienzo se funde con él —mismo fondo, sin borde ni
       esquinas propias— y lo que separa el dibujo de la leyenda de abajo es
       una línea y un hueco, no un segundo marco. */
    #caja-grafo {{
        background: {p.fondo};
        border: 1px solid {p.borde};
        border-radius: 8px;
    }}
    #separador-grafo {{
        background: {p.borde};
        border: none;
    }}
    #cifra-tarjeta {{
        background: {p.elevada};
        border: 1px solid {p.borde};
        border-radius: 10px;
    }}
    #cifra-rotulo {{
        color: {p.azul};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.8px;
    }}
    #cifra-nota {{
        color: {p.texto_3};
        font-size: 11px;
    }}
    /* El pie del grafo: leyenda y ayuda, dentro de la caja del lienzo.
       **Sin fondo propio**: con uno, dejaba una banda de otro color y, justo
       debajo, el margen de la tarjeta parecía una segunda barra. Una línea
       encima basta para separarlo del dibujo. */
    #pie-grafo {{
        background: transparent;
        border: none;
    }}

    /* --- API ------------------------------------------------------------ */
    #ruta, #codigo {{
        font-family: "Cascadia Mono", Consolas, monospace;
        color: {p.texto};
    }}
    #codigo {{
        background: {p.secundaria};
        border-radius: 6px;
        color: {p.texto_2};
        padding: 6px 9px;
    }}
    QPushButton#copiar-linea {{
        padding: 3px 12px;
        font-size: 12px;
    }}
    #rotulo-ambito {{
        color: {p.texto_3};
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding-top: 8px;
    }}

    /* --- Chat ----------------------------------------------------------- */
    /* La barra de arriba: una tira con su fondo, como en la web. */
    #chat-barra {{
        background: {p.elevada};
        border: 1px solid {p.borde};
        border-radius: 10px;
    }}
    #chat-compositor {{
        background: transparent;
        border: none;
    }}
    /* Botón discreto, para acciones que no son la principal. */
    QPushButton#fantasma {{
        background: transparent;
        border: 1px solid {p.borde_medio};
        color: {p.texto_2};
        padding: 6px 12px;
    }}
    QPushButton#fantasma:hover {{
        background: {p.secundaria};
        color: {p.texto};
    }}
    #conversacion {{
        background: transparent;
        border: none;
    }}
    QLabel#burbuja {{
        background: {p.elevada};
        border: 1px solid {p.borde};
        border-radius: 12px;
        color: {p.texto};
        padding: 12px 14px;
    }}
    QLabel#burbuja-mia {{
        background: {p.azul_suave};
        border: 1px solid {p.azul};
        border-radius: 12px;
        color: {p.texto};
        padding: 12px 14px;
    }}
    QPlainTextEdit#entrada {{
        background: {p.fondo};
        border: 1px solid {p.borde_medio};
        border-radius: {RADIO}px;
        color: {p.texto};
        padding: 8px 10px;
    }}
    QPlainTextEdit#entrada:focus {{ border-color: {p.azul}; }}

    /* --- Zona de arrastre ----------------------------------------------- */
    /* El borde discontinuo es lo que dice «aquí se suelta» sin una palabra.
       Al arrastrar algo por encima se enciende: sin esa respuesta no se sabe
       si el sitio es válido hasta que ya se ha soltado. */
    #zona {{
        background: {p.elevada};
        border: 1px dashed {p.borde_medio};
        border-radius: 12px;
    }}
    #zona[encima="si"] {{
        background: {p.azul_suave};
        border-color: {p.azul};
    }}
    #zona-titulo {{
        color: {p.texto};
        font-size: 14px;
        font-weight: 600;
    }}
    #zona-cuenta {{
        color: {p.texto_2};
        font-size: 12px;
        font-weight: 600;
    }}
    #zona-formatos {{
        color: {p.texto_3};
        font-size: 11px;
    }}

    /* --- Filtros por categoría ------------------------------------------ */
    QPushButton#chip {{
        background: transparent;
        border: 1px solid {p.borde_medio};
        border-radius: 13px;
        color: {p.texto_2};
        font-size: 12px;
        padding: 4px 12px;
    }}
    QPushButton#chip:hover {{ background: {p.secundaria}; }}
    QPushButton#chip:checked {{
        background: {p.azul_suave};
        border-color: {p.azul};
        color: {p.azul};
        font-weight: 600;
    }}

    /* --- Tabla de archivos --------------------------------------------- */
    /* La pista de la cabecera: qué memoria se mira y cuántas filas de
       cuántas, que es lo que cambia al filtrar. */
    #pista {{
        color: {p.texto_3};
        font-size: 12px;
    }}
    /* La barra de avance vive DENTRO de la celda de estado, no en un
       recuadro aparte: es lo que contesta «¿está parado?» justo donde se
       está mirando. Fina y sin número encima; el número va al lado. */
    QProgressBar#avance {{
        background: {p.secundaria};
        border: none;
        border-radius: 2px;
        max-height: 4px;
        min-height: 4px;
    }}
    QProgressBar#avance::chunk {{
        background: {p.azul};
        border-radius: 2px;
    }}
    QProgressBar#avance[parado="si"]::chunk {{ background: {p.texto_3}; }}
    #avance-texto {{
        color: {p.texto_3};
        font-size: 10px;
    }}


    QTableWidget#tabla {{
        background: transparent;
        border: none;
        gridline-color: transparent;
    }}
    /* Poco relleno vertical a propósito: Qt se lo **descuenta** al widget
       que va dentro de una celda. Con 8 px arriba y abajo, el botón de
       borrar recibía 13 px de alto, no cabía y Qt lo dejaba invisible. El
       alto de fila se fija desde el código, que es donde se ve. */
    QTableWidget#tabla::item {{
        border-bottom: 1px solid {p.borde};
        padding: 2px 6px;
    }}
    QTableWidget#tabla::item:selected {{
        background: {p.azul_suave};
        color: {p.texto};
    }}
    QPushButton#borrar-fila {{
        background: transparent;
        border: 1px solid {p.borde_medio};
        color: {p.texto_2};
        padding: 2px 10px;
    }}
    QPushButton#borrar-fila:hover {{
        border-color: #dc2626;
        color: #ef4444;
    }}
    QHeaderView::section {{
        background: transparent;
        border: none;
        border-bottom: 1px solid {p.borde_medio};
        color: {p.texto_3};
        font-weight: 600;
        padding: 6px;
        text-align: left;
    }}

    /* --- Panel: memorias, categorías y tipos ---------------------------- */
    /* Una fila de la tabla de memorias. Es un botón —se pulsa para abrir esa
       memoria— pero no lo parece hasta que el ratón pasa por encima: en una
       tabla, un borde por fila son diez bordes. */
    QPushButton#fila-memoria {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: {RADIO}px;
        text-align: left;
    }}
    QPushButton#fila-memoria:hover {{ background: {p.secundaria}; }}
    QPushButton#fila-memoria:checked {{
        background: {p.azul_suave};
        border-color: {p.azul_borde};
    }}
    #nombre-memoria {{ color: {p.texto}; font-weight: 600; }}
    QPushButton#fila-memoria:checked #nombre-memoria {{ color: {p.azul}; }}
    #cabecera-columna {{
        color: {p.texto_3};
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 0.6px;
    }}

    QPushButton#tarjeta-categoria {{
        background: {p.fondo};
        border: 1px solid {p.borde};
        border-radius: 10px;
        padding: 0;
        text-align: left;
    }}
    QPushButton#tarjeta-categoria:hover {{ border-color: {p.azul}; }}
    /* Vacía: se apaga, no desaparece. El catálogo entero dice lo que
       BIMNEMO sabe clasificar, y eso también informa. */
    QPushButton#tarjeta-categoria[vacia="si"] {{ background: transparent; }}
    QPushButton#tarjeta-categoria[vacia="si"] #nombre-categoria,
    QPushButton#tarjeta-categoria[vacia="si"] #cifra-categoria {{
        color: {p.texto_3};
    }}
    #nombre-categoria {{ color: {p.texto}; font-weight: 600; }}
    #cifra-categoria {{ color: {p.texto}; font-size: 20px; font-weight: 600; }}
    /* La extensión, en monoespaciada y con su cajita: es un código, no una
       palabra. */
    #extension {{
        background: {p.secundaria};
        border-radius: 5px;
        color: {p.texto_2};
        font-family: "Cascadia Mono", Consolas, monospace;
        font-size: 11px;
        padding: 2px 0;
    }}

    /* --- Diálogos ------------------------------------------------------- */
    QDialog {{ background: {p.elevada}; }}
    /* El rótulo de un campo, encima de su caja. */
    #rotulo-campo {{
        color: {p.texto_2};
        font-size: 12px;
        font-weight: 600;
    }}
    #error {{ color: #f87171; font-size: 12px; }}
    /* El rótulo de un campo dentro de un diálogo. En minúsculas, al
       contrario que los de la barra del grafo: aquí es una etiqueta de
       formulario, no un encabezado de sección. */
    #rotulo-dialogo {{
        color: {p.texto_2};
        font-size: 12px;
        font-weight: 600;
    }}
    /* Sin fondo propio: dentro de un diálogo, una casilla con el color
       general del fondo deja una banda oscura de lado a lado. */
    QCheckBox {{ background: transparent; color: {p.texto_2}; spacing: 8px; }}
    QCheckBox::indicator {{
        background: {p.fondo};
        border: 1px solid {p.borde_medio};
        border-radius: 4px;
        height: 15px;
        width: 15px;
    }}
    QCheckBox::indicator:checked {{
        background: {p.azul};
        border-color: {p.azul};
    }}
    QCheckBox:disabled {{ color: {p.texto_3}; }}

    QScrollBar:vertical {{
        background: transparent; width: 10px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {p.terciaria}; border-radius: 5px; min-height: 30px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    """
