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


# --- a qué archivo se carga cada llamada -------------------------------------


def test_la_marca_del_archivo_cruza_la_cola_de_lightrag(registro):
    """Las llamadas pasan por la cola de prioridad del rol; la marca llega igual."""
    from lightrag.utils import priority_limit_async_func_call

    async def llamada(**kwargs):
        kwargs["token_tracker"].add_usage({"prompt_tokens": 10, "completion_tokens": 5})
        return "ok"

    medida = consumo.medir_llm(llamada, "extract", "openai", "gpt-5-nano", "")
    en_cola = priority_limit_async_func_call(2, queue_name="prueba-consumo")(medida)

    async def indexar(nombre):
        consumo.DOCUMENTO.set(nombre)
        return await en_cola()

    async def todo():
        await asyncio.gather(indexar("ley.pdf"), indexar("bases.docx"))
        await en_cola.shutdown()

    asyncio.run(todo())
    archivos = sorted(f["archivo"] for f in registro._filas.values())
    assert archivos == ["bases.docx", "ley.pdf"]


def test_fuera_de_una_indexacion_no_hay_archivo(registro):
    consumo.Contador("llm", "Responder", "gpt-5-nano").add_usage({"prompt_tokens": 1})
    assert _fila(registro, "gpt-5-nano")["archivo"] == ""


def test_el_marcador_pone_el_nombre_del_archivo_mientras_se_procesa(monkeypatch):
    from types import SimpleNamespace

    from lightrag.pipeline import _PipelineMixin

    vistos = []

    async def procesar(self, **kwargs):
        vistos.append(consumo.DOCUMENTO.get())

    monkeypatch.setattr(_PipelineMixin, "process_single_document", procesar)
    consumo.instalar_marcador()
    consumo.instalar_marcador()  # no se envuelve dos veces

    asyncio.run(
        _PipelineMixin.process_single_document(
            object(),
            doc_id="doc-1",
            status_doc=SimpleNamespace(file_path="C:/entrada/Normativas/ley.pdf"),
            parsed_data={},
            ctx=None,
        )
    )
    assert vistos == ["ley.pdf"]
    assert consumo.DOCUMENTO.get() == ""  # y se quita al terminar


# --- el razonamiento de cada llamada ------------------------------------------


def test_apunta_el_nivel_y_los_tokens_de_razonamiento(registro):
    contador = consumo.Contador("llm", "Indexar", "deepseek-flash", "", "Apagado")
    contador.add_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "reasoning_tokens": 20,
        }
    )
    fila = _fila(registro, "deepseek-flash")
    assert (fila["nivel"], fila["razonando"]) == ("Apagado", 20)


def test_en_gemini_el_razonamiento_es_lo_que_sobra_del_total(registro):
    consumo.Contador("llm", "Indexar", "gemini-2.5-flash").add_usage(
        {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 400}
    )
    assert _fila(registro, "gemini-2.5-flash")["razonando"] == 250


def test_niveles_distintos_van_en_filas_distintas(registro):
    for nivel in ("Apagado", "Alto"):
        consumo.Contador("llm", "Indexar", "deepseek-flash", "", nivel).add_usage(
            {"prompt_tokens": 1, "completion_tokens": 1}
        )
    assert len(registro._filas) == 2


@pytest.mark.parametrize(
    "proveedor,modelo,opciones,dice",
    [
        ("deepseek", "deepseek-flash", {}, "Lo que decida el modelo"),
        (
            "deepseek",
            "deepseek-flash",
            {"extra_body": {"thinking": {"type": "disabled"}}},
            "Apagado",
        ),
        (
            "deepseek",
            "deepseek-flash",
            {
                "extra_body": {"thinking": {"type": "enabled"}},
                "reasoning_effort": "high",
            },
            "Alto",
        ),
        ("openai", "gpt-5.6-luna", {"reasoning_effort": "none"}, "Apagado"),
        (
            "gemini",
            "gemini-2.5-flash",
            {"thinking_config": {"thinking_budget": 0}},
            "Apagado",
        ),
        ("ollama", "qwen3:8b", {"think": False}, "Apagado"),
        ("mistral", "mistral-small-latest", {}, "Sin control"),
        ("deepseek", "deepseek-flash", {"extra_body": {"cosa": 1}}, "Ajuste a mano"),
    ],
)
def test_de_las_opciones_de_la_llamada_al_nivel_de_la_barra(
    proveedor, modelo, opciones, dice
):
    from lightrag.api.bimnemo import razonamiento

    assert razonamiento.nivel_de_opciones(proveedor, modelo, opciones) == dice


def test_medir_llm_saca_el_nivel_del_host(registro):
    recibido = {}

    async def llamada(**kwargs):
        recibido.update(kwargs)

    medida = consumo.medir_llm(
        llamada,
        "extract",
        "openai",
        "deepseek-flash",
        "https://api.deepseek.com/v1",
        opciones={"extra_body": {"thinking": {"type": "disabled"}}},
    )
    asyncio.run(medida())
    assert recibido["token_tracker"].nivel == "Apagado"


def test_el_conector_de_openai_pasa_los_tokens_de_razonamiento():
    from types import SimpleNamespace

    from lightrag.llm.openai import _reasoning_tokens

    uso = SimpleNamespace(
        completion_tokens_details=SimpleNamespace(reasoning_tokens=42)
    )
    assert _reasoning_tokens(uso) == 42
    assert _reasoning_tokens(SimpleNamespace()) == 0
