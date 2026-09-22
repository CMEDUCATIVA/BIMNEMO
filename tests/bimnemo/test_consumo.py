"""El contador de consumo: tokens reales, coste en el momento, sin romper nada."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

import pytest

from lightrag.api.bimnemo import consumo, precios


@pytest.fixture
def registro(tmp_path, monkeypatch):
    nuevo = consumo._Registro()
    nuevo.iniciar(tmp_path)
    monkeypatch.setattr(consumo, "REGISTRO", nuevo)
    return nuevo


def _fila(registro, modelo):
    return next(f for f in registro._filas.values() if f["modelo"] == modelo)


def test_cuenta_lo_que_devuelve_el_proveedor(registro):
    contador = consumo.Contador("llm", "Indexar", "gpt-5.6-luna")
    contador.add_usage(
        {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
    )
    contador.add_usage(
        {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
    )

    fila = _fila(registro, "gpt-5.6-luna")
    assert (fila["llamadas"], fila["entrada"], fila["salida"]) == (2, 2000, 1000)
    # 2000 × 0,20 + 1000 × 1,20, por millón
    assert fila["coste"] == pytest.approx(0.0016)


def test_el_pensamiento_de_gemini_se_cobra_aunque_no_venga_en_completion(registro):
    """Gemini deja los tokens de pensar fuera de `candidates`, pero en el total."""
    consumo.Contador("llm", "Indexar", "gemini-2.5-flash").add_usage(
        {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 400}
    )
    assert _fila(registro, "gemini-2.5-flash")["salida"] == 300


def test_un_modelo_sin_precio_se_mide_igual(registro):
    consumo.Contador("llm", "Responder", "modelo-raro").add_usage(
        {"prompt_tokens": 10, "completion_tokens": 5}
    )
    fila = _fila(registro, "modelo-raro")
    assert fila["entrada"] == 10 and fila["sin_precio"] is True


def test_lo_local_no_cuesta(registro):
    consumo.Contador("llm", "Indexar", "qwen3:8b", "http://localhost:11434").add_usage(
        {"prompt_tokens": 10_000, "completion_tokens": 5_000}
    )
    fila = _fila(registro, "qwen3:8b")
    assert fila["coste"] == 0 and fila["sin_precio"] is False


def test_deepseek_cobra_el_doble_en_hora_punta():
    punta = datetime(2026, 9, 22, 3, 30, tzinfo=timezone.utc)  # martes 03:30 UTC
    valle = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)
    finde = datetime(2026, 9, 26, 3, 30, tzinfo=timezone.utc)  # sábado
    assert precios.precio("llm", "deepseek-v4-pro", "", punta).salida == 3.96
    assert precios.precio("llm", "deepseek-v4-pro", "", valle).salida == 1.98
    assert precios.precio("llm", "deepseek-v4-pro", "", finde).salida == 1.98


def test_el_prefijo_del_proveedor_no_impide_encontrar_el_precio():
    assert precios.precio("llm", "deepseek/deepseek-flash") is not None
    assert precios.precio("llm", "anthropic.claude-haiku-4-5") is not None
    assert precios.precio("embedding", "text-embedding-3-large").entrada == 0.13


def test_sobrevive_a_un_reinicio(tmp_path):
    primero = consumo._Registro()
    primero.iniciar(tmp_path)
    primero.anotar("embedding", "Embeddings", "text-embedding-3-large", "", 1000, 0)

    segundo = consumo._Registro()
    segundo.iniciar(tmp_path)
    assert _fila(segundo, "text-embedding-3-large")["entrada"] == 1000


def test_un_fichero_roto_no_impide_arrancar(tmp_path):
    (tmp_path / consumo.NOMBRE_FICHERO).write_text("{roto", encoding="utf-8")
    registro = consumo._Registro()
    registro.iniciar(tmp_path)
    assert registro.resumen()["rows"] == []


def test_resumen_por_periodos(registro):
    hoy = date(2026, 9, 22)
    registro.anotar(
        "llm",
        "Indexar",
        "gpt-5-nano",
        "",
        1_000_000,
        0,
        datetime(2026, 9, 22, 15, tzinfo=timezone.utc),
    )
    registro.anotar(
        "llm",
        "Indexar",
        "gpt-5-nano",
        "",
        1_000_000,
        0,
        datetime(2026, 9, 10, 15, tzinfo=timezone.utc),
    )
    resumen = registro.resumen(30, hoy=hoy)
    assert resumen["totals"]["month"]["coste"] == pytest.approx(0.10)
    assert resumen["totals"]["week"]["coste"] == pytest.approx(0.05)
    assert len(resumen["rows"]) == 2


def test_medir_llm_pasa_el_contador_solo_a_quien_lo_acepta(registro):
    recibido = {}

    async def llamada(prompt, **kwargs):
        recibido.update(kwargs)
        kwargs["token_tracker"].add_usage({"prompt_tokens": 7, "completion_tokens": 3})
        return "ok"

    medida = consumo.medir_llm(llamada, "extract", "openai", "gpt-5-nano", "")
    assert asyncio.run(medida("hola")) == "ok"
    assert isinstance(recibido["token_tracker"], consumo.Contador)
    assert _fila(registro, "gpt-5-nano")["tarea"] == "Indexar"

    # Azure no acepta token_tracker: pasárselo sería un TypeError.
    assert consumo.medir_llm(llamada, "extract", "azure_openai", "x", "") is llamada


def test_si_contar_falla_la_llamada_sigue(registro, monkeypatch):
    def rompe(*a, **k):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(registro, "anotar", rompe)
    consumo.Contador("llm", "Indexar", "gpt-5-nano").add_usage({"prompt_tokens": 1})
