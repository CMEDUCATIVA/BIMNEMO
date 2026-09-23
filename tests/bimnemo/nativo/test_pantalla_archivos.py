"""La pantalla «Archivos» de la ventana nativa enseña lo mismo que la web.

Las ocho columnas, los estados en castellano, los filtros por categoría y la
barra de avance dentro de la celda de estado. La pantalla se alimenta aquí
con las respuestas ya hechas del motor: lo que se prueba es qué pinta con
ellas, no el transporte HTTP, que es de `motor.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.offline


class MotorFalso:
    """Un motor que solo apunta lo que le piden, sin tocar la red.

    La pantalla dispara cuatro peticiones al construirse. Con el motor de
    verdad, esas peticiones quedarían pendientes durante toda la prueba y su
    respuesta llegaría —o no— en mitad de otra.
    """

    def __init__(self) -> None:
        self.base = "http://127.0.0.1:0"
        self.pedidos: list[tuple[str, str]] = []

    def get(self, ruta: str, bien=None, mal=None) -> None:
        self.pedidos.append(("GET", ruta))

    def post(self, ruta: str, cuerpo=None, bien=None, mal=None) -> None:
        self.pedidos.append(("POST", ruta))

    def borrar(self, ruta: str, cuerpo=None, bien=None, mal=None) -> None:
        self.pedidos.append(("DELETE", ruta))

    def subir(self, ruta: str, fichero: str, bien=None, mal=None, avance=None) -> None:
        self.pedidos.append(("UPLOAD", ruta))


CATALOGO: dict[str, Any] = {
    "categories": [
        {"key": "document", "label": "Documento", "icon": "file-text", "color": "sky"},
        {
            "key": "presentation",
            "label": "Presentación",
            "icon": "presentation",
            "color": "rose",
        },
        {"key": "photo", "label": "Foto", "icon": "image", "color": "emerald"},
    ],
    "known_extensions": ["pdf", "docx", "pptx"],
    "ingestible_extensions": ["docx", "pdf", "pptx", "txt"],
}

FICHEROS: dict[str, Any] = {
    "files": [
        {
            "name": "manual.docx",
            "size_bytes": 5138022,
            "modified_at": 1758410460.0,
            "category": "document",
            "type": "DOCX",
            "status": "processed",
            "chunks_count": 7,
            "doc_id": "doc-1",
        },
        {
            "name": "charla.pptx",
            "size_bytes": 500736,
            "modified_at": 1758410520.0,
            "category": "presentation",
            "type": "PPTX",
            "status": "processing",
            "chunks_count": 12,
            "doc_id": "doc-2",
        },
        {
            "name": "roto.pdf",
            "size_bytes": 1048576,
            "modified_at": 1758200000.0,
            "category": "document",
            "type": "PDF",
            "status": "failed",
            "chunks_count": None,
            "doc_id": "doc-3",
            "error_msg": "El modelo no respondió",
        },
    ],
    "total": 3,
    "returned": 3,
    "scan_error": None,
}

PROGRESO: dict[str, Any] = {
    "busy": True,
    "working": 1,
    "chunk_done": 9,
    "chunk_total": 20,
    "revision": "r1",
    "stalled": False,
    # Avance por documento: es lo que pinta cada barra. `charla.pptx` es
    # `doc-2`, el que de verdad está extrayendo.
    "docs": [
        {
            "doc_id": "doc-2",
            "phase": "extract",
            "done": 9,
            "total": 20,
            "label": "Extrayendo 9/20 fragmentos",
            "percent": 63,
        }
    ],
}


@pytest.fixture()
def pantalla(aplicacion):
    """Una pantalla ya alimentada con catálogo, ficheros y avance."""
    from lightrag.api.bimnemo.nativo.pantalla_archivos import PantallaArchivos

    p = PantallaArchivos(MotorFalso())
    p._catalogo = list(CATALOGO["categories"])
    p._extensiones = list(CATALOGO["ingestible_extensions"])
    p.zona.formatos(p._extensiones)
    p.barras.recordar(dict(PROGRESO))
    p._recibir(dict(FICHEROS))
    return p


def _texto(widget, indice: int = 0) -> str:
    from PySide6.QtWidgets import QLabel

    return widget.findChildren(QLabel)[indice].text()


def _botones(widget) -> list:
    from PySide6.QtWidgets import QPushButton

    return widget.findChildren(QPushButton)


def _barras(widget) -> list:
    from PySide6.QtWidgets import QProgressBar

    return widget.findChildren(QProgressBar)


# --- Las columnas ----------------------------------------------------------


def test_son_las_ocho_columnas_de_la_web(pantalla):
    """Ocho, con los mismos rótulos. Fueron cinco y sin nombrar la última."""
    from lightrag.api.bimnemo.nativo.pantalla_archivos import COLUMNAS

    assert COLUMNAS == (
        "Archivo",
        "Categoría",
        "Tipo",
        "Tamaño",
        "Estado",
        "Fragmentos",
        "Modificado",
        "Acciones",
    )
    rotulos = [
        pantalla.tabla.horizontalHeaderItem(i).text()
        for i in range(pantalla.tabla.columnCount())
    ]
    assert rotulos == list(COLUMNAS)


def test_la_fila_lleva_todo_lo_que_manda_el_motor(pantalla):
    """Categoría, fragmentos y fecha llegaban en el JSON y se tiraban."""
    from lightrag.api.bimnemo.nativo.pantalla_archivos import (
        ARCHIVO,
        CATEGORIA,
        FRAGMENTOS,
        MODIFICADO,
        TAMANO,
        TIPO,
    )

    assert pantalla.tabla.item(0, ARCHIVO).text() == "manual.docx"
    assert _texto(pantalla.tabla.cellWidget(0, CATEGORIA)) == "Documento"
    assert pantalla.tabla.item(0, TIPO).text() == "DOCX"
    assert pantalla.tabla.item(0, TAMANO).text() == "4.9 MB"
    assert pantalla.tabla.item(0, FRAGMENTOS).text() == "7"
    assert pantalla.tabla.item(0, MODIFICADO).text().startswith("20/09/")


def test_sin_fragmentos_una_raya_y_no_un_cero(pantalla):
    """`chunks_count` a `None` es «no se sabe», no «ninguno»."""
    from lightrag.api.bimnemo.nativo.pantalla_archivos import FRAGMENTOS

    assert pantalla.tabla.item(2, FRAGMENTOS).text() == "—"


# --- Estados ---------------------------------------------------------------


def test_los_estados_se_dicen_en_castellano(pantalla):
    """`parsing` salía tal cual: la tabla solo traducía cuatro estados."""
    from lightrag.api.bimnemo.nativo import formato

    assert formato.estado("parsing") == "Extrayendo"
    assert formato.estado("analyzing") == "Analizando"
    assert formato.estado("preprocessed") == "Preprocesado"
    assert formato.estado("failed") == "Fallido"
    assert formato.estado(None) == "Sin indexar"
    # Un estado que el motor añada mañana se enseña tal cual, no en blanco.
    assert formato.estado("teleportando") == "teleportando"


def test_borrandose_manda_sobre_lo_que_diga_el_motor(pantalla):
    """La fila lo dice desde que se pide, no cuando el motor termina."""
    from lightrag.api.bimnemo.nativo.pantalla_archivos import ACCIONES, ESTADO

    pantalla._borrandose.add("manual.docx")
    pantalla._repintar()

    assert "Borrando" in _texto(pantalla.tabla.cellWidget(0, ESTADO))
    borrar = _botones(pantalla.tabla.cellWidget(0, ACCIONES))[-1]
    assert borrar.isEnabled() is False


def test_la_marca_de_borrado_se_olvida_cuando_la_fila_desaparece(pantalla):
    """Sin esto, otro fichero con el mismo nombre nacería «Borrando…»."""
    pantalla._borrandose.add("manual.docx")
    pantalla._recibir({"files": [], "total": 0})
    assert pantalla._borrandose == set()


# --- Acciones --------------------------------------------------------------


def test_solo_lo_fallido_ofrece_reintentar(pantalla):
    """Es la acción que faltaba justo donde se ve el fallo."""
    from lightrag.api.bimnemo.nativo.pantalla_archivos import ACCIONES

    assert len(_botones(pantalla.tabla.cellWidget(0, ACCIONES))) == 1
    assert len(_botones(pantalla.tabla.cellWidget(2, ACCIONES))) == 2


def test_reindexar_llama_al_endpoint_de_la_web(pantalla):
    """El botón «Reindexar pendientes» no existía en la ventana nativa."""
    pantalla._reindexar()
    assert ("POST", "/documents/scan") in pantalla.motor.pedidos


def test_reintentar_manda_solo_el_documento_de_la_fila(pantalla):
    """El botón está en una fila: reintenta ese, no todos los fallidos."""
    pantalla._reintentar("doc-3")
    assert ("POST", "/bimnemo/documents/retry?doc_id=doc-3") in pantalla.motor.pedidos


def test_el_boton_de_la_fila_lleva_su_propio_doc_id(pantalla):
    from lightrag.api.bimnemo.nativo.pantalla_archivos import ACCIONES

    reintentar = _botones(pantalla.tabla.cellWidget(2, ACCIONES))[0]
    reintentar.click()
    assert ("POST", "/bimnemo/documents/retry?doc_id=doc-3") in pantalla.motor.pedidos


# --- Zona de arrastre ------------------------------------------------------


def test_la_zona_dice_cuantos_formatos_admite_el_motor(pantalla):
    """Y los enseña **todos**: una lista recortada no se puede consultar."""
    assert pantalla.zona.cuenta.text() == "Admite 4 formatos"
    for extension in CATALOGO["ingestible_extensions"]:
        assert extension in pantalla.zona.lista.text()


def test_sin_formatos_no_se_acusa_a_la_conexion(pantalla):
    """«No admite nada» y «no pude preguntar» no son lo mismo."""
    pantalla.zona.formatos([])
    assert "no declara ningún formato" in pantalla.zona.lista.text()

    pantalla.zona.no_se_pudo("El motor no responde.")
    assert pantalla.zona.lista.text() == "El motor no responde."


def test_el_dialogo_filtra_por_lo_que_el_motor_admite(pantalla):
    """Elegir un `.exe` que el motor va a rechazar es un error que llega tarde."""
    filtro = pantalla._filtro()
    assert "*.docx" in filtro and "*.pdf" in filtro
    # La escotilla sigue estando: hay quien sabe lo que hace.
    assert "Todos los archivos (*.*)" in filtro


# --- Filtros ---------------------------------------------------------------


def test_los_chips_cuentan_por_categoria(pantalla):
    rotulos = [b.text() for b in pantalla.filtros._grupo.buttons()]
    assert rotulos[0] == "Todos  3"
    assert "Documento  2" in rotulos
    assert "Presentación  1" in rotulos
    # Una categoría sin ficheros no ocupa sitio.
    assert not any(r.startswith("Foto") for r in rotulos)


def test_filtrar_deja_solo_su_categoria_y_lo_dice_en_la_pista(pantalla):
    pantalla.filtros._elegir("presentation")
    assert pantalla.tabla.rowCount() == 1
    assert "1 de 3" in pantalla.pista.text()


# --- Contador del carril ---------------------------------------------------


def test_avisa_de_cuantos_ficheros_hay(pantalla):
    """El carril enseña ese número junto a «Archivos»."""
    visto: list[int] = []
    pantalla.cuenta.connect(visto.append)

    pantalla._recibir({"files": FICHEROS["files"][:2], "total": 2})
    assert visto == [2]

    # Mismo número: no se vuelve a avisar.
    pantalla._recibir({"files": FICHEROS["files"][:2], "total": 2})
    assert visto == [2]


def test_el_contador_es_el_total_y_no_lo_que_deja_ver_el_filtro(pantalla):
    """Filtrar cambia la tabla, no cuántos ficheros hay en la memoria."""
    visto: list[int] = []
    pantalla.cuenta.connect(visto.append)

    pantalla.filtros._elegir("presentation")
    assert pantalla.tabla.rowCount() == 1
    assert visto == []


def test_si_la_categoria_elegida_desaparece_se_vuelve_a_todas(pantalla):
    """Dejar la tabla filtrada por algo que ya no existe la deja en blanco."""
    pantalla.filtros._elegir("presentation")
    sin_presentaciones = {
        "files": [f for f in FICHEROS["files"] if f["category"] != "presentation"],
        "total": 2,
    }
    pantalla._recibir(sin_presentaciones)
    assert pantalla.filtros.activa == ""
    assert pantalla.tabla.rowCount() == 2


# --- Avance ----------------------------------------------------------------


def test_cada_fila_lleva_el_avance_de_su_documento(pantalla):
    """El motor publica avance por documento; la fila busca el suyo.

    Antes solo había un recuento para toda la tubería: la única fila que
    podía enseñar un número era la que estuviera extrayendo, y con dos
    documentos en cola eso dejaba casi toda la tabla con una barra que iba
    y venía sin decir nada.
    """
    from lightrag.api.bimnemo.nativo.pantalla_archivos import ESTADO

    celda = pantalla.tabla.cellWidget(1, ESTADO)
    barra = _barras(celda)[0]
    assert barra.value() == 63
    assert "Extrayendo" in _texto(celda, 1)
    # La frase entera del motor, donde sí cabe.
    assert "9/20" in celda.toolTip()

    # La fila terminada no lleva barra: una al 100 % permanente es ruido.
    assert _barras(pantalla.tabla.cellWidget(0, ESTADO)) == []


def test_dos_documentos_a_la_vez_no_comparten_porcentaje(pantalla):
    """Cada uno el suyo: antes el segundo heredaba el número del primero."""
    from lightrag.api.bimnemo.nativo.pantalla_archivos import ESTADO

    ficheros = {
        "files": [
            dict(FICHEROS["files"][1], name="uno.pptx", doc_id="doc-2"),
            dict(FICHEROS["files"][1], name="dos.pptx", doc_id="doc-9"),
        ],
        "total": 2,
    }
    pantalla.barras.recordar(
        dict(
            PROGRESO,
            docs=PROGRESO["docs"]
            + [
                {
                    "doc_id": "doc-9",
                    "phase": "analyze",
                    "done": 2,
                    "total": 8,
                    "label": "Analizando tablas e imágenes 2/8",
                    "percent": 17,
                }
            ],
        )
    )
    pantalla._recibir(ficheros)

    assert _barras(pantalla.tabla.cellWidget(0, ESTADO))[0].value() == 63
    assert _barras(pantalla.tabla.cellWidget(1, ESTADO))[0].value() == 17
    assert "Tablas" in _texto(pantalla.tabla.cellWidget(1, ESTADO), 1)


def test_borrar_un_documento_tambien_mueve_su_barra(pantalla):
    """Purgar el grafo lleva segundos y antes no se veía nada moverse."""
    from lightrag.api.bimnemo.nativo.pantalla_archivos import ESTADO

    pantalla._borrandose.add("manual.docx")
    pantalla.barras.recordar(
        dict(
            PROGRESO,
            docs=[
                {
                    "doc_id": "doc-1",
                    "phase": "delete",
                    "done": 30,
                    "total": 120,
                    "label": "Borrando 30/120 entidades y relaciones",
                    "percent": 25,
                }
            ],
        )
    )
    pantalla._repintar()

    celda = pantalla.tabla.cellWidget(0, ESTADO)
    assert _barras(celda)[0].value() == 25
    assert "Borrando" in _texto(celda, 1)


def test_sin_avance_publicado_la_barra_no_se_inventa_un_numero(pantalla):
    """Indeterminada es honesto; un porcentaje ajeno, no."""
    from lightrag.api.bimnemo.nativo.pantalla_archivos import ESTADO

    pantalla.barras.recordar(dict(PROGRESO, docs=[]))
    pantalla._repintar()

    barra = _barras(pantalla.tabla.cellWidget(1, ESTADO))[0]
    assert (barra.minimum(), barra.maximum()) == (0, 0)


def test_parado_mucho_rato_lo_dice(pantalla):
    """«¿Está bloqueado?» es la pregunta que la pantalla no sabía contestar."""
    from time import monotonic

    from lightrag.api.bimnemo.nativo.archivos_avance import PACIENCIA
    from lightrag.api.bimnemo.nativo.pantalla_archivos import ESTADO

    pantalla.barras.recordar(dict(PROGRESO, stalled=True, busy=False))
    # Como si llevara parado más de la cuenta.
    pantalla.barras._parado_desde = monotonic() - PACIENCIA * 2
    pantalla._repintar()

    assert _texto(pantalla.tabla.cellWidget(1, ESTADO), 1) == "Sin avanzar"


def test_un_parpadeo_de_parada_no_alarma(pantalla):
    """Recién encolado y nadie trabajando es normal durante un instante."""
    from time import monotonic

    from lightrag.api.bimnemo.nativo.pantalla_archivos import ESTADO

    pantalla.barras.recordar(dict(PROGRESO, stalled=True, busy=False))
    pantalla.barras._parado_desde = monotonic()
    pantalla._repintar()

    assert _texto(pantalla.tabla.cellWidget(1, ESTADO), 1) != "Sin avanzar"


# --- Huecos ----------------------------------------------------------------


def test_la_tabla_vacia_explica_por_que(pantalla):
    """Sin explicación, una tabla en blanco se lee como un fallo de carga."""
    pantalla._recibir({"files": [], "total": 0})
    assert "Todavía no hay archivos" in pantalla.vacio.text()
    assert pantalla.vacio.isHidden() is False

    pantalla._recibir(dict(FICHEROS))
    pantalla.filtros._elegir("photo")
    assert "Nada en esta categoría" in pantalla.vacio.text()


# -- copias repetidas -------------------------------------------------------


def test_una_copia_repetida_se_ve_como_copia_y_solo_ofrece_borrarla(pantalla):
    from lightrag.api.bimnemo.nativo.pantalla_archivos import ACCIONES, ESTADO

    copia = {
        "name": "Error OIR.txt", "size_bytes": 1332, "modified_at": 1758410600.0,
        "category": "text", "type": "TXT", "status": "failed",
        "chunks_count": 0, "doc_id": "doc-copia",
        "error_msg": "«Error OIR.txt» tiene exactamente el mismo contenido que «OIR FB.txt»…",
        "duplicate_of": "OIR FB.txt",
    }
    pantalla._recibir({"files": [copia], "total": 1})

    celda = pantalla.tabla.cellWidget(0, ESTADO)
    assert "Copia repetida" in _texto(celda)
    assert "OIR FB.txt" in celda.toolTip()

    botones = _botones(pantalla.tabla.cellWidget(0, ACCIONES))
    assert len(botones) == 1, "reintentar una copia no sirve de nada"
    assert "original sigue" in botones[0].toolTip()


def test_un_fallo_de_verdad_dice_su_motivo_al_pasar_el_raton(pantalla):
    from lightrag.api.bimnemo.nativo.pantalla_archivos import ESTADO

    fila = [f["name"] for f in FICHEROS["files"]].index("roto.pdf")
    celda = pantalla.tabla.cellWidget(fila, ESTADO)
    assert "Fallido" in _texto(celda)
    assert "El modelo no respondió" in celda.toolTip()


# -- pausa ------------------------------------------------------------------


def test_lo_que_se_indexa_se_puede_pausar_y_lo_pausado_reanudar(aplicacion):
    from lightrag.api.bimnemo.nativo import formato

    assert "processing" in formato.PAUSABLES and "deleting" not in formato.PAUSABLES
    assert formato.estado("pausado") == "En pausa"


def test_pausar_llama_a_la_ruta_de_la_memoria(pantalla):
    pantalla._pausar()
    assert ("POST", "/bimnemo/documents/pause") in pantalla.motor.pedidos


def test_un_documento_pausado_no_sale_como_fallido(pantalla):
    from lightrag.api.bimnemo.nativo.archivos_tabla import estado_de

    archivo = {"name": "ley.pdf", "status": "failed", "paused": True, "doc_id": "d"}
    assert estado_de(archivo, "ley.pdf", {}, set()) == "pausado"

# --- nombres demasiado largos -------------------------------------------------

LARGO_16 = (
    "7614342-16-bases-estandar-concurso-publico-abreviado-para-la-contratacion-"
    "de-expertos-y-gerentes-de-proyectos.docx"
)


class _DialogoFalso:
    """Acepta con lo propuesto, o cancela, sin abrir ninguna ventana."""

    acepta = True
    vistos: list = []

    def __init__(self, padre, originales, limite_de, existentes, **_):
        from lightrag.api.bimnemo import nombres

        _DialogoFalso.vistos = list(originales)
        self._nuevos = {o: nombres.sugerir(o, limite_de(o)) for o in originales}

    def exec(self):
        from PySide6.QtWidgets import QDialog

        return QDialog.Accepted if _DialogoFalso.acepta else QDialog.Rejected

    def resultado(self):
        return self._nuevos


def test_solo_preguntan_los_que_no_caben(pantalla):
    pantalla.nombres.raiz = 87  # la carpeta real de Normativas_BIM
    pantalla.nombres.dialogo = _DialogoFalso
    _DialogoFalso.acepta = True

    listos = pantalla.nombres.preparar(["C:/docs/corto.docx", f"C:/docs/{LARGO_16}"])

    assert _DialogoFalso.vistos == [LARGO_16]
    assert listos[0] == ("C:/docs/corto.docx", "corto.docx")
    assert listos[1][0] == f"C:/docs/{LARGO_16}" and len(listos[1][1]) <= 57


def test_cancelar_no_sube_esos_pero_si_los_demas(pantalla):
    pantalla.nombres.raiz = 87
    pantalla.nombres.dialogo = _DialogoFalso
    _DialogoFalso.acepta = False

    listos = pantalla.nombres.preparar(["C:/docs/corto.docx", f"C:/docs/{LARGO_16}"])
    assert listos == [("C:/docs/corto.docx", "corto.docx")]


def test_sin_saber_el_limite_no_se_frena_nada(pantalla):
    pantalla.nombres.raiz = None
    assert pantalla.nombres.preparar([f"C:/{LARGO_16}"]) == [(f"C:/{LARGO_16}", LARGO_16)]


def test_la_fila_de_nombre_largo_ofrece_renombrar_y_no_reintentar(pantalla):
    from lightrag.api.bimnemo.nativo.pantalla_archivos import ACCIONES

    datos = dict(FICHEROS)
    datos["files"] = [
        dict(FICHEROS["files"][2], name=LARGO_16, name_too_long=True)
    ]
    pantalla._recibir(datos)
    botones = _botones(pantalla.tabla.cellWidget(0, ACCIONES))
    assert [b.toolTip() for b in botones][0] == "Renombrar y volver a leer"
    assert not any("Reintentar" in b.toolTip() for b in botones)


def test_el_aviso_cuenta_en_vivo_y_no_deja_seguir_si_no_cabe(aplicacion):
    from PySide6.QtWidgets import QWidget

    from lightrag.api.bimnemo.nativo.nombres_dialogo import DialogoNombres

    padre = QWidget()  # que no lo recoja el recolector con el diálogo dentro
    dialogo = DialogoNombres(padre, [LARGO_16], lambda _n: 57, frozenset())
    fila = dialogo.filas[0]
    assert dialogo.boton_seguir.isEnabled()  # la propuesta ya cabe
    assert fila.contador.text().endswith("/ 57")

    fila.campo.setText("x" * 80)
    assert not dialogo.boton_seguir.isEnabled()
    assert "caben 57" in fila.fallos.text()

    fila.campo.setText("acta: final")
    assert "no admite" in fila.fallos.text()

    fila.campo.setText("BE-16 expertos")
    assert dialogo.boton_seguir.isEnabled()
    assert dialogo.resultado() == {LARGO_16: "BE-16 expertos.docx"}

def test_la_fila_elegida_se_lee_tambien_sin_foco(pantalla):
    """Al hacer clic fuera, Qt usaba el resaltado inactivo del sistema (casi
    blanco en Windows) y la fila con texto blanco dejaba de leerse."""
    from PySide6.QtGui import QPalette

    from lightrag.api.bimnemo.nativo import tema

    pantalla.window().setStyleSheet(tema.hoja(tema.OSCURO))
    paleta = pantalla.tabla.palette()
    activa = paleta.color(QPalette.Active, QPalette.Highlight)
    inactiva = paleta.color(QPalette.Inactive, QPalette.Highlight)
    assert inactiva == activa
    assert paleta.color(QPalette.Inactive, QPalette.HighlightedText).name() == (
        tema.OSCURO.texto
    )