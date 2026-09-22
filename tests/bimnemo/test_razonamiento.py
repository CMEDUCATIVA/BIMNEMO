"""La barra de razonamiento escribe lo que cada modelo admite, y nada más."""

from __future__ import annotations

import json

import pytest

from lightrag.api.bimnemo import razonamiento as r
from lightrag.api.bimnemo.envfile import read_env, write_env
from lightrag.api.bimnemo.runtime import CONFIGURABLE_ENV_KEYS


def _ids(proveedor, modelo):
    e = r.esquema(proveedor, modelo)
    return [n.id for n in e.niveles] if e else None


# --- qué admite cada modelo -------------------------------------------------


def test_cada_modelo_de_openai_tiene_sus_niveles_y_no_los_de_otro():
    """`minimal` es un 400 en gpt-5.6 y `none` un 400 en gpt-5-nano."""
    assert _ids("openai", "gpt-5-nano") == ["", "minimal", "low", "medium", "high"]
    assert "minimal" not in _ids("openai", "gpt-5.6-luna")
    assert "none" in _ids("openai", "gpt-5.6-luna")
    assert "none" not in _ids("openai", "gpt-6-astra")
    assert _ids("openai", "gpt-4o") is None


def test_la_primera_posicion_nunca_escribe_nada():
    for proveedor, modelo in (
        ("openai", "gpt-5.6-luna"),
        ("deepseek", "deepseek-flash"),
        ("qwen", "qwen3.7-flash"),
        ("gemini", "gemini-2.5-flash-lite"),
        ("ollama", "qwen3:8b"),
    ):
        primero = r.esquema(proveedor, modelo).niveles[0]
        assert primero.id == r.DEFECTO and primero.variables == {}


@pytest.mark.parametrize(
    "proveedor,modelo",
    [
        ("anthropic", "claude-sonnet-5"),  # la capa compatible lo ignora
        ("mistral", "mistral-small-2506"),
        ("zhipu", "glm-4-flash"),  # solo GLM-4.5 y posteriores
        ("ollama", "llama3.1:8b"),  # Ollama no arrancaría
        ("xai", "grok-4.3"),
        ("groq", "llama-3.3-70b-versatile"),
    ],
)
def test_sin_control_no_hay_barra(proveedor, modelo):
    assert r.esquema(proveedor, modelo) is None


def test_gemini_de_la_serie_3_usa_nivel_y_la_25_presupuesto():
    apagado = r.esquema("gemini", "gemini-2.5-flash-lite").niveles[1]
    assert json.loads(apagado.variables[r.GEMINI]) == {"thinking_budget": 0}
    assert "minimal" not in _ids("gemini", "gemini-3.8-flash")
    assert "minimal" in _ids("gemini", "gemini-3.5-flash-lite")
    assert "0" not in _ids("gemini", "gemini-2.5-pro")  # no se puede apagar


# --- de la barra al .env y vuelta -------------------------------------------


def test_apagar_en_deepseek_solo_al_extraer():
    cambios = r.a_variables(
        "deepseek", "deepseek-flash", {"indexar": "off", "responder": ""}
    )
    esperado = json.dumps({"thinking": {"type": "disabled"}}, separators=(",", ":"))
    assert cambios["EXTRACT_OPENAI_LLM_EXTRA_BODY"] == esperado
    assert cambios["KEYWORD_OPENAI_LLM_EXTRA_BODY"] == esperado
    assert cambios["QUERY_OPENAI_LLM_EXTRA_BODY"] is None


def test_guardar_comenta_todas_las_gestionadas_antes_de_escribir():
    """Pasar de DeepSeek a OpenAI no puede dejar `thinking` puesto."""
    cambios = r.a_variables("openai", "gpt-5.6-luna", {"indexar": "none"})
    assert set(cambios) == set(r.GESTIONADAS)
    assert cambios["EXTRACT_OPENAI_LLM_REASONING_EFFORT"] == "none"
    assert cambios["EXTRACT_OPENAI_LLM_EXTRA_BODY"] is None
    assert not any(v == "" for v in cambios.values())


def test_un_ajuste_a_mano_no_se_toca():
    cambios = r.a_variables("openai", "gpt-5.6-luna", {"indexar": r.MANUAL})
    assert not any(k.startswith(("EXTRACT_", "KEYWORD_")) for k in cambios)


def test_un_nivel_que_el_modelo_no_admite_no_se_escribe():
    cambios = r.a_variables("openai", "gpt-5.6-luna", {"indexar": "minimal"})
    assert all(v is None for v in cambios.values())


def test_ida_y_vuelta_por_el_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text("LLM_MODEL=deepseek-flash\n", encoding="utf-8")
    write_env(
        env,
        r.a_variables(
            "deepseek", "deepseek-flash", {"indexar": "off", "responder": "high"}
        ),
    )
    leido = r.leer(read_env(env), "deepseek", "deepseek-flash")
    assert leido == {"indexar": "off", "responder": "high"}


def test_lo_que_escribe_lo_entiende_el_motor(tmp_path, monkeypatch):
    """python-dotenv y las opciones por rol de LightRAG leen un dict, no texto."""
    from dotenv import dotenv_values

    from lightrag.llm.binding_options import OpenAILLMOptions

    env = tmp_path / ".env"
    write_env(env, r.a_variables("qwen", "qwen3.7-flash", {"indexar": "off"}))
    valores = dotenv_values(env)
    for clave, valor in valores.items():
        monkeypatch.setenv(clave, valor)

    class Args:
        pass

    opciones = OpenAILLMOptions.options_dict_for_role(Args(), "extract", True)
    assert opciones["extra_body"] == {"enable_thinking": False}


def test_algo_puesto_a_mano_se_lee_como_manual():
    valores = {"EXTRACT_OPENAI_LLM_EXTRA_BODY": '{"cosa":1}'}
    assert r.leer(valores, "deepseek", "deepseek-flash")["indexar"] == r.MANUAL


def test_la_lista_blanca_del_lanzador_las_incluye_todas():
    """`runtime.py` las escribe a mano porque no puede importar nada."""
    assert r.GESTIONADAS <= CONFIGURABLE_ENV_KEYS


def test_el_catalogo_lleva_los_niveles_de_cada_modelo():
    from lightrag.api.bimnemo.providers import catalog_payload

    openai = next(p for p in catalog_payload()["llm"] if p["key"] == "openai")
    assert "gpt-5-nano" in openai["models"]
    assert "gpt-5-nano" in openai["reasoning"]
    assert openai["reasoning"]["gpt-5-nano"]["levels"][0]["id"] == ""


def test_los_modelos_nuevos_estan_en_el_catalogo():
    from lightrag.api.bimnemo.providers import catalog_payload

    modelos = {p["key"]: p["models"] for p in catalog_payload()["llm"]}
    assert "gpt-5-nano" in modelos["openai"]
    assert "gemini-2.5-flash-lite" in modelos["gemini"]
    assert "qwen3.7-flash" in modelos["qwen"]
