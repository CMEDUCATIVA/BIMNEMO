"""El avance real de cada documento, del motor a la barra.

Dos piezas: ``lightrag/doc_progress.py``, que publica los contadores dentro
de ``pipeline_status``, y ``lightrag/api/bimnemo/avance.py``, que los
convierte en la etiqueta y el porcentaje que enseña una fila.

Lo que se prueba es la promesa que le hicimos a quien mira la pantalla: que
la barra **solo avanza**, que no se inventa números y que el borrado —que
tarda segundos y antes no movía nada— también se ve.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

from lightrag import doc_progress
from lightrag.api.bimnemo import avance


# --- Los contadores del motor ----------------------------------------------


def test_publicar_y_leer_el_avance_de_un_documento():
    estado: dict = {}
    doc_progress.publish(estado, "doc-1", doc_progress.EXTRACT, 3, 7)

    leido = doc_progress.snapshot(estado)["doc-1"]
    assert (leido["phase"], leido["done"], leido["total"]) == ("extract", 3, 7)


def test_avanzar_conserva_fase_y_total():
    """Una fase que suma de uno en uno no tiene por qué repetir el total."""
    estado: dict = {}
    doc_progress.publish(estado, "doc-1", doc_progress.MERGE, 0, 40)
    doc_progress.advance(estado, "doc-1")
    doc_progress.advance(estado, "doc-1")

    leido = doc_progress.snapshot(estado)["doc-1"]
    assert (leido["phase"], leido["done"], leido["total"]) == ("merge", 2, 40)


def test_un_documento_que_termina_deja_de_contarse():
    estado: dict = {}
    doc_progress.publish(estado, "doc-1", doc_progress.PARSE)
    doc_progress.clear(estado, "doc-1")
    assert doc_progress.snapshot(estado) == {}


def test_no_crece_sin_fin():
    """Una ejecución larga no puede inflar el estado de la tubería."""
    estado: dict = {}
    for i in range(doc_progress.MAX_DOCS + 5):
        doc_progress.publish(estado, f"doc-{i}", doc_progress.EXTRACT, i, 10)
    assert len(doc_progress.snapshot(estado)) == doc_progress.MAX_DOCS


def test_escribir_el_avance_nunca_rompe_el_trabajo_que_describe():
    """Contrato heredado de `PipelineStatusLogger`: informar no puede fallar."""

    class Roto(dict):
        def __setitem__(self, clave, valor):
            raise RuntimeError("el gestor se cayó")

    doc_progress.publish(Roto(), "doc-1", doc_progress.EXTRACT, 1, 2)
    doc_progress.advance(Roto(), "doc-1")
    doc_progress.clear(Roto(), "doc-1")
    assert doc_progress.snapshot(None) == {}


# --- De contadores a barra --------------------------------------------------


def test_la_barra_solo_avanza_al_cambiar_de_fase():
    """Cuatro fases con su propio contador, un solo porcentaje que sube.

    Si cada fase pintara 0-100 %, la barra volvería atrás tres veces.
    """
    recorrido = [
        avance.porcentaje(doc_progress.PARSE, 1, 1),
        avance.porcentaje(doc_progress.ANALYZE, 1, 8),
        avance.porcentaje(doc_progress.ANALYZE, 8, 8),
        avance.porcentaje(doc_progress.EXTRACT, 3, 7),
        avance.porcentaje(doc_progress.MERGE, 1, 4),
        avance.porcentaje(doc_progress.MERGE, 4, 4),
    ]
    assert recorrido == sorted(recorrido)
    assert recorrido[-1] == 100


def test_una_fase_sin_total_no_se_inventa_un_numero():
    """Leer un documento no sabe cuánto queda: se devuelve su comienzo."""
    assert avance.porcentaje(doc_progress.PARSE, 0, 0) == 0
    assert avance.porcentaje(doc_progress.EXTRACT, 0, 0) == round(
        avance.COMIENZOS[doc_progress.EXTRACT] * 100
    )


def test_el_borrado_va_de_cero_a_cien_por_su_cuenta():
    """No es una fase de la indexación: no comparte su reparto."""
    assert avance.porcentaje(doc_progress.DELETE, 30, 120) == 25
    assert avance.porcentaje(doc_progress.DELETE, 120, 120) == 100


def test_la_etiqueta_habla_en_castellano_y_con_numeros():
    assert avance.etiqueta(doc_progress.EXTRACT, 3, 7) == "Extrayendo 3/7 fragmentos"
    assert avance.etiqueta(doc_progress.ANALYZE, 0, 0) == "Analizando tablas e imágenes…"


# --- Las filas que lee la pantalla -----------------------------------------


def test_una_fila_por_documento_en_marcha():
    estado: dict = {}
    doc_progress.publish(estado, "doc-1", doc_progress.EXTRACT, 3, 7)
    doc_progress.publish(estado, "doc-2", doc_progress.ANALYZE, 2, 8)

    filas = avance.filas(estado, {"doc-1": "processing", "doc-2": "analyzing"})
    assert [f["doc_id"] for f in filas] == ["doc-1", "doc-2"]
    assert filas[0]["percent"] != filas[1]["percent"], "cada uno el suyo"


def test_un_avance_viejo_no_se_enseña():
    """Dos documentos a la vez pueden pisarse la escritura y dejar restos."""
    estado: dict = {}
    doc_progress.publish(estado, "doc-viejo", doc_progress.EXTRACT, 7, 7)
    assert avance.filas(estado, {"doc-1": "processing"}) == [
        avance.fila("doc-1", {"phase": doc_progress.EXTRACT})
    ]


def test_un_documento_recien_encolado_ya_dice_algo():
    """Sin contador todavía, su estado basta para no dejar la fila muda."""
    (fila,) = avance.filas({}, {"doc-1": "pending"})
    assert fila["label"] == "Leyendo el documento…"


def test_el_borrado_se_enseña_aunque_no_este_en_la_lista_de_activos():
    """Un documento que se está purgando ya no consta como «en marcha»."""
    estado: dict = {}
    doc_progress.publish(estado, "doc-1", doc_progress.DELETE, 30, 120)

    (fila,) = avance.filas(estado, {})
    assert fila["percent"] == 25
    assert "Borrando" in fila["label"]
