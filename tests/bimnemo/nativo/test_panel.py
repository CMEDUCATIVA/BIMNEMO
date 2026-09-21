"""El panel: reparto del disco, memorias, categorías y tipos de archivo.

Lo que se prueba aquí es **de qué memoria habla cada bloque** y qué pasa al
pulsarlos, que es donde estaba la confusión: tres bloques suman todas las
memorias y uno es de la abierta.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.offline


def _categoria(clave, rotulo, icono, color, cuantos, octetos):
    return {
        "key": clave,
        "label": rotulo,
        "icon": icono,
        "color": color,
        "files": cuantos,
        "size_bytes": octetos,
    }


def stats_de(memoria: str) -> dict[str, Any]:
    """Lo que contesta `/bimnemo/stats` según la memoria abierta."""
    if memoria == "":
        return {
            "storage": {
                "total_files": 3,
                "total_bytes": 1000,
                "categories_in_use": 2,
                "categories_available": 3,
                "categories": [
                    _categoria("document", "Documento", "file-text", "sky", 2, 900),
                    _categoria("photo", "Foto", "image", "emerald", 1, 100),
                    _categoria("data", "Datos", "database", "amber", 0, 0),
                ],
                "types": [
                    {"type": "DOCX", "files": 2, "size_bytes": 900},
                    {"type": "PNG", "files": 1, "size_bytes": 100},
                ],
            },
            "memory": {"total_documents": 3, "total_chunks": 12},
        }
    # La otra memoria: otra cosa distinta, que es lo que hay que ver.
    return {
        "storage": {
            "total_files": 1,
            "total_bytes": 400,
            "categories_in_use": 1,
            "categories_available": 3,
            "categories": [
                _categoria("document", "Documento", "file-text", "sky", 0, 0),
                _categoria("photo", "Foto", "image", "emerald", 0, 0),
                _categoria("data", "Datos", "database", "amber", 1, 400),
            ],
            "types": [{"type": "CSV", "files": 1, "size_bytes": 400}],
        },
        "memory": {"total_documents": 1, "total_chunks": 4},
    }


@pytest.fixture()
def panel(ventana):
    """El panel, contestando según la memoria abierta en cada momento."""
    ventana.motor.respuestas["/bimnemo/stats"] = lambda: stats_de(ventana.motor.memoria)
    pantalla = ventana.contenido.widget(0)
    pantalla.refrescar()
    return pantalla


# --- Cuentas ----------------------------------------------------------------


def test_por_debajo_del_uno_por_ciento_no_es_cero():
    """No es lo mismo nada que poco, y en un disco esa diferencia importa."""
    from lightrag.api.bimnemo.nativo.panel_piezas import porcentaje_texto

    assert porcentaje_texto(0, 1000) == "0%"
    assert porcentaje_texto(3, 1000) == "<1%"
    assert porcentaje_texto(905, 1000) == "91%"
    # Sin total no se divide: un panel recién abierto no debe reventar.
    assert porcentaje_texto(5, 0) == "0%"


def test_el_reparto_ordena_por_peso_y_salta_lo_vacio():
    from lightrag.api.bimnemo.nativo.panel_piezas import ocupadas

    categorias = stats_de("")["storage"]["categories"]
    assert [c["key"] for c in ocupadas(categorias)] == ["document", "photo"]


# --- Almacenamiento por categoría -------------------------------------------


def test_el_reparto_es_el_de_la_memoria_abierta(panel):
    from PySide6.QtWidgets import QLabel

    assert panel.pista_almacenado.text() == "1000 B"
    textos = [e.text() for e in panel.leyenda.findChildren(QLabel)]
    assert "Documento" in textos
    assert "90%" in textos
    # Y la barra: un trozo por categoría con algo dentro, proporcional.
    assert panel.medidor._trozos == [("sky", 90.0), ("emerald", 10.0)]


def test_el_reparto_cambia_al_cambiar_de_memoria(panel, ventana):
    """Era lo que no pasaba: el disco se repartía sumando todas las memorias."""
    from PySide6.QtWidgets import QLabel

    ventana.barra._elegida(ventana.barra.selector.findData("obra-sur"))

    assert panel.pista_almacenado.text() == "400 B"
    textos = [e.text() for e in panel.leyenda.findChildren(QLabel)]
    assert "Datos" in textos
    assert "Documento" not in textos
    assert panel.medidor._trozos == [("amber", 100.0)]


# --- Categorías -------------------------------------------------------------


def test_el_catalogo_entero_sale_aunque_este_vacio(panel):
    """Lo que BIMNEMO sabe clasificar también informa: se apaga, no se va."""
    tarjetas = panel.rejilla_categorias._tarjetas
    assert set(tarjetas) == {"document", "photo", "data"}
    assert tarjetas["data"].property("vacia") == "si"
    assert tarjetas["document"].property("vacia") == ""


def test_cada_categoria_dice_cuantos_y_cuanto(panel):
    tarjeta = panel.rejilla_categorias._tarjetas["document"]
    assert tarjeta.cuantos.text() == "2"
    assert tarjeta.unidad.text() == "archivos"
    assert tarjeta.parte.text() == "90%"


def test_una_sola_no_dice_archivos_en_plural(panel):
    assert panel.rejilla_categorias._tarjetas["photo"].unidad.text() == "archivo"


def test_las_categorias_son_las_de_la_memoria_abierta(panel, ventana):
    """Lo que se pidió: el catálogo cuenta lo que hay en ESTA memoria."""
    tarjetas = panel.rejilla_categorias._tarjetas
    assert tarjetas["document"].cuantos.text() == "2"
    assert tarjetas["data"].property("vacia") == "si"

    ventana.barra._elegida(ventana.barra.selector.findData("obra-sur"))

    tarjetas = panel.rejilla_categorias._tarjetas
    assert tarjetas["document"].cuantos.text() == "0"
    assert tarjetas["document"].property("vacia") == "si"
    assert tarjetas["data"].cuantos.text() == "1"
    assert panel.pista_categorias.text() == "1 de 3 en uso"


def test_pulsar_una_categoria_lleva_a_archivos_filtrado(panel, ventana):
    panel.rejilla_categorias._tarjetas["photo"].click()

    archivos = ventana.contenido.widget(1)
    assert ventana.contenido.currentIndex() == 1
    assert archivos.filtros.activa == "photo"


# --- Tipos de archivo -------------------------------------------------------


def test_los_tipos_son_de_la_memoria_abierta(panel):
    """Como todo lo demás del panel."""
    from PySide6.QtWidgets import QLabel

    assert panel.pista_tipos.text() == "2 tipos"
    textos = [e.text() for e in panel.lista_tipos.findChildren(QLabel)]
    assert "DOCX" in textos
    assert "2 · 900 B" in textos


def test_sin_tipos_se_dice_en_vez_de_dejar_el_hueco(panel):
    from PySide6.QtWidgets import QLabel

    panel.lista_tipos.poner([], 0)
    textos = [e.text() for e in panel.lista_tipos.findChildren(QLabel)]
    assert textos == ["Todavía no hay archivos que clasificar."]


# --- La rueda del ratón -----------------------------------------------------


def _rueda(grafo):
    """Una vuelta de rueda sobre el centro del lienzo."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    centro = QPointF(grafo.width() / 2, grafo.height() / 2)
    evento = QWheelEvent(
        centro,
        grafo.mapToGlobal(centro.toPoint()).toPointF(),
        QPoint(0, 0),
        QPoint(0, -360),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(grafo, evento)
    return evento.isAccepted()


def test_pasar_por_encima_del_grafo_no_le_da_la_rueda(panel):
    """Bajando por el panel, el puntero cruza el lienzo sin remedio.

    Si el grafo se quedara la rueda, el panel se pararía en seco y el grafo
    daría un salto de zoom que nadie pidió. Al no aceptar el evento, este
    sigue su camino hasta el área que desplaza.
    """
    grafo = panel.grafo
    grafo.clearFocus()
    zoom = grafo._vista[2]

    assert _rueda(grafo) is False
    assert grafo._vista[2] == zoom


def test_pulsando_dentro_el_grafo_si_se_queda_la_rueda(panel, ventana):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    grafo = panel.grafo
    # Pulsar es lo que se la da: esa es la política de foco del lienzo.
    assert grafo.focusPolicy() == Qt.ClickFocus

    # El foco solo existe dentro de una ventana abierta; con la ventana
    # cerrada, `setFocus` no hace nada y la prueba mediría otra cosa.
    ventana.show()
    QApplication.processEvents()
    grafo.setFocus()
    assert grafo.hasFocus() is True

    zoom = grafo._vista[2]
    acepta = _rueda(grafo)
    ventana.hide()

    assert acepta is True
    assert grafo._vista[2] != zoom


# --- El pliegue -------------------------------------------------------------


def test_la_primera_seccion_es_el_grafo_a_cualquier_ancho(ventana):
    """El grafo es a lo que se viene: primera sección, él solo y entero.

    Antes compartía la pantalla con la columna de cifras y, al encoger, la
    ventana sacaba barra horizontal porque la barra de controles del grafo
    pedía más ancho del que había. Ahora esos controles saltan de línea y el
    grafo se queda con lo que haya.
    """
    from PySide6.QtWidgets import QApplication

    ventana.show()
    panel = ventana.contenido.widget(0)

    for ancho, alto in ((1600, 1000), (1100, 800), (980, 620)):
        ventana.resize(ancho, alto)
        QApplication.processEvents()

        hueco = panel.area.viewport()
        # Ocupa el hueco visible menos el encabezado, o su mínimo si la
        # ventana es más baja que eso.
        assert panel.primera_seccion.height() >= min(hueco.height() - 120, 520)
        assert panel.primera_seccion.width() >= hueco.width() - 80
        assert panel.area.horizontalScrollBar().isVisible() is False

    ventana.hide()


def test_la_primera_seccion_ocupa_una_pantalla(ventana):
    """El grafo es a lo que se viene: los demás bloques empiezan debajo.

    Amontonados en la misma pantalla, cada bloque nuevo le robaba alto al
    grafo hasta dejarlo en una franja.
    """
    from PySide6.QtWidgets import QApplication

    ventana.resize(1500, 950)
    ventana.show()
    # Que Qt reparta de verdad: el alto se fija al redimensionarse el hueco
    # visible, y eso llega como un evento, no al volver de `show`.
    QApplication.processEvents()
    panel = ventana.contenido.widget(0)
    ventana.hide()

    hueco = panel.area.viewport().height()
    # La primera sección ocupa el hueco visible menos el encabezado.
    assert hueco - 120 < panel.primera_seccion.height() <= hueco
    # Y queda contenido por debajo al que llegar bajando.
    assert panel.area.widget().height() > hueco
