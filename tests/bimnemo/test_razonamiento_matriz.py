"""Auditoría en matriz: el razonamiento, proveedor por proveedor.

Añadir el control a Claude por suscripción toca una lista que **todos** los
proveedores comparten (``BASES``, ``GESTIONADAS``, ``a_variables``). El
riesgo no es que Claude salga mal: es que al cambiar de Claude a OpenAI, o
de DeepSeek a Ollama, quede puesta una variable del anterior y el proveedor
nuevo conteste 400 en cada llamada.

Esto recorre el catálogo entero —cada proveedor con cada uno de sus modelos—
y comprueba las invariantes que no pueden romperse para ninguno.
"""

from __future__ import annotations

import pytest

from lightrag.api.bimnemo import razonamiento
from lightrag.api.bimnemo.provider_catalog import LLM_PROVIDERS

pytestmark = pytest.mark.offline


def _todos() -> list[tuple[str, str]]:
    """Cada (proveedor, modelo) del catálogo, incluidas las suscripciones."""
    pares: list[tuple[str, str]] = []
    for proveedor in LLM_PROVIDERS:
        for p in (proveedor, getattr(proveedor, "subscription", None)):
            if p is None:
                continue
            for modelo in p.models:
                pares.append((p.key, modelo))
    return pares


PARES = _todos()


def test_el_catalogo_no_esta_vacio():
    assert len(PARES) > 40, "si esto baja, la auditoría dejó de auditar"


# --- lo que vale para todos -------------------------------------------------


@pytest.mark.parametrize("proveedor,modelo", PARES)
def test_guardar_limpia_siempre_lo_del_proveedor_anterior(proveedor, modelo):
    """La invariante que protege al resto: **se comentan todas**.

    Sin esto, pasar de DeepSeek a OpenAI dejaría `extra_body={"thinking":…}`
    puesto y OpenAI contestaría 400 en cada llamada.
    """
    cambios = razonamiento.a_variables(
        proveedor, modelo, {"indexar": razonamiento.DEFECTO, "responder": "high"}
    )
    for rol in ("EXTRACT", "KEYWORD", "QUERY"):
        for base in razonamiento.BASES:
            assert f"{rol}_{base}" in cambios, f"{rol}_{base} se queda sin tocar"


@pytest.mark.parametrize("proveedor,modelo", PARES)
def test_lo_que_decida_el_modelo_no_escribe_nada(proveedor, modelo):
    """Es la única opción que no puede romper ningún proveedor."""
    cambios = razonamiento.a_variables(
        proveedor,
        modelo,
        {"indexar": razonamiento.DEFECTO, "responder": razonamiento.DEFECTO},
    )
    assert set(cambios.values()) == {None}


@pytest.mark.parametrize("proveedor,modelo", PARES)
def test_cada_nivel_escribe_solo_variables_conocidas(proveedor, modelo):
    """Una variable fuera de `GESTIONADAS` nadie la limpiaría después."""
    e = razonamiento.esquema(proveedor, modelo)
    for nivel in e.niveles if e else ():
        for base in nivel.variables:
            assert base in razonamiento.BASES, f"{base} no está en BASES"


@pytest.mark.parametrize("proveedor,modelo", PARES)
def test_lo_escrito_se_vuelve_a_leer_igual(proveedor, modelo):
    """Ida y vuelta: lo que guarda la barra es lo que la barra enseña."""
    e = razonamiento.esquema(proveedor, modelo)
    for nivel in e.niveles if e else ():
        cambios = razonamiento.a_variables(
            proveedor, modelo, {"indexar": nivel.id, "responder": nivel.id}
        )
        env = {k: v for k, v in cambios.items() if v is not None}
        leido = razonamiento.leer(env, proveedor, modelo)
        assert leido["indexar"] == nivel.id, f"{proveedor}/{modelo}: {nivel.rotulo}"
        assert leido["responder"] == nivel.id


@pytest.mark.parametrize("proveedor,modelo", PARES)
def test_la_tabla_de_consumo_reconoce_cada_nivel(proveedor, modelo):
    """El camino de vuelta: de las opciones de la llamada al rótulo."""
    e = razonamiento.esquema(proveedor, modelo)
    for nivel in e.niveles if e else ():
        opciones = {
            razonamiento._CAMPO[base]: razonamiento._valor(valor)
            for base, valor in nivel.variables.items()
        }
        assert (
            razonamiento.nivel_de_opciones(proveedor, modelo, opciones) == nivel.rotulo
        )


# --- cambiar de proveedor ---------------------------------------------------

#: Parejas que de verdad se dan al cambiar de idea en la pantalla.
SALTOS = [
    ("claude_suscripcion", "claude-opus-5", "openai", "gpt-5.6-luna"),
    ("claude_suscripcion", "claude-opus-5", "deepseek", "deepseek-v4-pro"),
    ("openai", "gpt-5.6-luna", "claude_suscripcion", "claude-opus-5"),
    ("deepseek", "deepseek-v4-pro", "claude_suscripcion", "claude-haiku-4-5"),
    ("gemini", "gemini-2.5-flash", "claude_suscripcion", "claude-opus-5"),
    ("deepseek", "deepseek-v4-pro", "openai", "gpt-5-nano"),
    ("claude_suscripcion", "claude-opus-5", "anthropic", "claude-opus-5"),
]


@pytest.mark.parametrize("de_p,de_m,a_p,a_m", SALTOS)
def test_cambiar_de_proveedor_no_deja_nada_del_anterior(de_p, de_m, a_p, a_m):
    """Lo que de verdad podría romperse al añadir un proveedor nuevo."""
    e = razonamiento.esquema(de_p, de_m)
    assert e is not None, f"{de_p}/{de_m} debería tener barra"
    alto = next(n for n in e.niveles if n.id)

    # Se elige un nivel con el proveedor viejo…
    antes = razonamiento.a_variables(de_p, de_m, {"indexar": alto.id, "responder": alto.id})
    env = {k: v for k, v in antes.items() if v is not None}
    assert env, "el nivel elegido tiene que escribir algo"

    # …y se guarda con el nuevo, sin tocar las barras.
    despues = razonamiento.a_variables(
        a_p, a_m, {"indexar": razonamiento.DEFECTO, "responder": razonamiento.DEFECTO}
    )
    for clave in env:
        assert despues.get(clave, "sin tocar") is None, (
            f"{clave} sobrevive al pasar de {de_p} a {a_p}"
        )


# --- Claude por suscripción -------------------------------------------------


def test_claude_por_suscripcion_ya_tiene_barra():
    """Su CLI acepta `--effort`, al contrario que la capa OpenAI de Anthropic."""
    e = razonamiento.esquema("claude_suscripcion", "claude-opus-5")
    assert e is not None
    assert [n.rotulo for n in e.niveles] == [
        "Lo que decida el modelo", "Bajo", "Medio", "Alto", "Muy alto", "Máximo"
    ]


def test_claude_por_clave_sigue_sin_barra():
    """Su capa compatible con OpenAI ignora `reasoning_effort` sin avisar.

    No es una incoherencia con el de arriba: son dos caminos distintos al
    mismo modelo, y solo uno lo deja controlar.
    """
    assert razonamiento.esquema("anthropic", "claude-opus-5") is None


def test_el_nivel_de_claude_llega_al_cli_como_effort():
    cambios = razonamiento.a_variables(
        "claude_suscripcion", "claude-opus-5", {"indexar": "low", "responder": "high"}
    )
    assert cambios["EXTRACT_CLAUDE_CODE_LLM_EFFORT"] == "low"
    assert cambios["KEYWORD_CLAUDE_CODE_LLM_EFFORT"] == "low"
    assert cambios["QUERY_CLAUDE_CODE_LLM_EFFORT"] == "high"
    assert razonamiento._CAMPO[razonamiento.CLAUDE] == "effort"


def test_el_lanzador_limpia_tambien_la_variable_nueva():
    """`CONFIGURABLE_ENV_KEYS` se escribe a mano y tiene que ir al día."""
    from lightrag.api.bimnemo.runtime import CONFIGURABLE_ENV_KEYS

    assert razonamiento.GESTIONADAS <= CONFIGURABLE_ENV_KEYS
