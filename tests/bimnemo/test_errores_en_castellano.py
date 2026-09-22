"""Los fallos de los proveedores y de Windows, dichos en castellano y con qué hacer.

Los mensajes son los reales que dejó una memoria de normativas: los
proveedores contestan en inglés, y Windows se queja a su manera de las rutas
largas.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

SIN_SALDO = (
    "C[1/46]: doc-b2db-chunk-001: RateLimitError: Error code: 429 - {'error': "
    "{'message': 'You have no credits remaining. Add credits to continue using "
    "the API at https://platform.openai.com/settings/organization/billing/.', "
    "'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}"
)
LIMITE = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for gpt-5.4-mini "
    "in organization org-X on tokens per min (TPM): Limit 200000, Used 200000, "
    "Requested 4735. Please try again in 1.42s.', 'type': 'tokens', "
    "'code': 'rate_limit_exceeded'}}"
)
_RUTA = (
    "C:\\Users\\Administrador\\AppData\\Local\\Programs\\BIMNEMO\\inputs\\\\"
    "Normativas_BIM\\__parsed__\\7614342-10-bases-estandar-concurso-publico-para-"
    "consultoria-en-general.docx.parsed\\7614342-10-bases-estandar-concurso-publico-"
    "para-consultoria-en-general.blocks.assets"
)
RUTA_206 = f"[WinError 206] El nombre del archivo o la extensión es demasiado largo: '{_RUTA}'"
RUTA_3 = f"[WinError 3] El sistema no puede encontrar la ruta especificada: '{_RUTA}'"


def _explica(raw):
    from lightrag.api.bimnemo.stats import _clean_reason

    return _clean_reason(raw)


def test_sin_saldo_dice_que_recargar_y_donde():
    texto = _explica(SIN_SALDO)
    assert "sin saldo" in texto
    assert "https://platform.openai.com/settings/organization/billing/" in texto
    assert "no se ha perdido" in texto and "Reintentar" in texto
    assert "credits" not in texto


def test_sin_saldo_no_se_confunde_con_ir_demasiado_rapido():
    """Los dos llegan como 429: mandar a «esperar» a una cuenta a cero no sirve."""
    assert "sin saldo" in _explica(SIN_SALDO)
    assert "demasiado rápido" in _explica(LIMITE)
    assert "sin saldo" not in _explica(LIMITE)


@pytest.mark.parametrize("raw", [RUTA_206, RUTA_3])
def test_una_ruta_demasiado_larga_dice_que_se_renombre(raw):
    texto = _explica(raw)
    assert "demasiado largo" in texto and "Renómbralo" in texto


def test_una_ruta_corta_que_no_existe_no_se_toma_por_larga():
    texto = _explica("[Errno 2] No such file or directory: 'C:\\datos\\a.txt'")
    assert "Renómbralo" not in texto


@pytest.mark.parametrize(
    "raw, dice",
    [
        ("Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-abc'}}", "clave de API"),
        ("Error code: 404 - {'error': {'message': 'The model `gpt-9` does not exist', 'code': 'model_not_found'}}", "«gpt-9»"),
        ("APIConnectionError: Connection error.", "No se pudo conectar"),
        ("Error code: 529 - {'type': 'error', 'error': {'type': 'overloaded_error', 'message': 'Overloaded'}}", "saturado"),
    ],
)
def test_otros_fallos_conocidos(raw, dice):
    assert dice in _explica(raw)


def test_lo_que_no_se_reconoce_se_ensena_como_lo_dijo_el_proveedor():
    """Mejor lo que dijo el proveedor que un motivo inventado."""
    raw = "Error code: 400 - {'error': {'message': 'Algo raro que nadie conoce'}}"
    assert _explica(raw) == "Algo raro que nadie conoce"


ANCLA = (
    "Refusing to purge document doc-58125d13ad7e8d50523a1bcc9c95d1f3: recovery "
    "anchor row(s) missing or unusable (full_entities, full_relations) and the "
    "document may already have written to the knowledge graph "
    "(kg_write_state=graph_mutation_started). Purging now would delete its "
    "chunks while leaving unattributable graph objects behind."
)


def test_un_documento_a_medias_en_el_grafo_se_explica_en_castellano():
    """El de la ley atascada: no manda a «Reintentar», que volvería a negarse."""
    from lightrag.api.bimnemo.stats import MAX_REASON, _clean_reason

    dice = _clean_reason(ANCLA)
    assert dice.startswith("Este documento se quedó a medias en el grafo")
    assert "no ha borrado nada" in dice
    assert "Refusing" not in dice
    assert len(dice) <= MAX_REASON