"""El catálogo de categorías, atado a lo que el motor sabe leer.

La regla que se prueba aquí es la del módulo: **una categoría existe si
BIMNEMO, tal y como se instala, puede leer alguno de sus formatos**. Es
comprobable contra el registro de parsers, así que se comprueba en vez de
quedar en una opinión que envejece — que es lo que pasó con «Modelo BIM» y
«Plano CAD», dos tarjetas para formatos que la subida rechaza.

«Tal y como se instala» es la parte fina: `mineru` y `docling` leen
imágenes, pero piden un servicio HTTP aparte que no viaja en el paquete, así
que aquí no cuentan. Una categoría que solo funciona con algo que el usuario
no tiene es la misma promesa incumplida con otro nombre.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline


def _lo_que_lee_bimnemo_sin_nada_mas() -> set[str]:
    """Lo que leen los motores que funcionan solos.

    Se dejan fuera los que piden un servicio externo —`mineru`, `docling`—
    aunque estén en el registro: en la máquina de quien ejecuta esto puede
    haber un `DOCLING_ENDPOINT` puesto, y entonces la prueba mediría otra
    cosa según el ordenador. Lo que tiene que valer es lo que el paquete
    hace al instalarse.
    """
    from lightrag.parser.routing import (
        parser_engine_endpoint_requirement,
        suffix_capabilities,
        supported_parser_engines,
    )

    legibles: set[str] = set()
    for motor in supported_parser_engines():
        if parser_engine_endpoint_requirement(motor):
            continue
        legibles |= {str(e).lower().lstrip(".") for e in suffix_capabilities(motor)}
    return legibles


def test_toda_categoria_tiene_algun_formato_que_el_motor_lea():
    """Una tarjeta para algo que no se puede subir promete lo que no cumple."""
    from lightrag.api.bimnemo.catalog import CATEGORIES, _EXTENSION_MAP

    legibles = _lo_que_lee_bimnemo_sin_nada_mas()
    sin_nada = []
    for categoria in CATEGORIES:
        suyas = {e for e, clave in _EXTENSION_MAP.items() if clave == categoria.key}
        if not suyas & legibles:
            sin_nada.append(categoria.label)

    assert sin_nada == [], (
        "estas categorías no admiten ningún formato con el paquete tal cual se "
        f"instala: {sin_nada}. O se les da un formato que el motor lea solo, o "
        "sobran."
    )


def test_todo_lo_que_el_motor_lee_tiene_categoria():
    """El otro lado: lo que la zona de arrastre anuncia, el panel lo clasifica.

    Sin esto, un formato admitido cae en «Otros» —que ni siquiera cuenta para
    el «N de N» del panel— y la misma pantalla se contradice: arriba dice que
    entra y abajo no sabe dónde ponerlo.
    """
    from lightrag.api.bimnemo.catalog import _EXTENSION_MAP

    huerfanas = sorted(_lo_que_lee_bimnemo_sin_nada_mas() - set(_EXTENSION_MAP))
    assert huerfanas == [], f"admitidas pero sin categoría: {huerfanas}"


def test_lo_que_no_se_puede_indexar_cae_en_otros():
    """Un IFC o un DWG guardados a mano: están, pero no entran en la memoria."""
    from lightrag.api.bimnemo.catalog import UNKNOWN, categorize

    # Y una imagen igual: leerlas es cosa de MinerU o Docling, que piden un
    # servicio que no viene en el paquete.
    for nombre in ("plano.dwg", "modelo.ifc", "maqueta.rvt", "foto.jpg", "captura.png"):
        assert categorize(nombre) is UNKNOWN


def test_una_pista_de_parser_en_el_nombre_no_confunde_la_categoria():
    """`notas.[mineru].md` es texto, no una categoría llamada «[mineru]»."""
    from lightrag.api.bimnemo.catalog import categorize

    assert categorize("notas.[mineru].md").key == "text"


@pytest.mark.parametrize(
    "nombre, categoria",
    [
        ("acta.docx", "document"),
        ("mediciones.xlsx", "spreadsheet"),
        ("charla.pptx", "presentation"),
        ("obra.jpg", "other"),
        ("config.yaml", "data"),
        ("notas.md", "text"),
        ("script.py", "text"),
        ("sin_extension", "other"),
    ],
)
def test_cada_formato_cae_donde_toca(nombre, categoria):
    from lightrag.api.bimnemo.catalog import categorize

    assert categorize(nombre).key == categoria
