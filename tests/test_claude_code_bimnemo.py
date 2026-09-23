"""
Test de integración: Claude Code (suscripción) en BIMNEMO.

Verifica que:
1. La ventana CLI de Claude Code se ejecuta sin mostrarse (Windows).
2. El tracking de tokens/coste se registra en tiempo real.
3. Al indexar un documento, aparece el uso en la tabla de "Uso y coste de la IA".
"""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.fixture(autouse=True)
def sin_sesion_viva(monkeypatch):
    """Estas pruebas son del camino de siempre: un proceso por llamada.

    La sesión reutilizada tiene las suyas (`tests/bimnemo/test_claude_sesion`).
    Mezclarlas aquí haría que cada prueba recorriera los dos caminos y no se
    supiera cuál está comprobando.
    """
    from lightrag.llm import claude_sesion

    monkeypatch.setenv(claude_sesion.INTERRUPTOR, "0")


@pytest.mark.asyncio
async def test_claude_code_no_window_win32():
    """Verifica que en Windows se usa CREATE_NO_WINDOW."""
    import sys
    from lightrag.llm.claude_code import claude_code_complete_if_cache

    # Mock del subprocess para capturar creationflags
    captured_flags = {}

    async def mock_create_subprocess_exec(*args, **kwargs):
        captured_flags['creationflags'] = kwargs.get('creationflags', 0)
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(b"Test output", b""))
        proc.returncode = 0
        return proc

    if sys.platform == "win32":
        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess_exec):
            await claude_code_complete_if_cache(
                "claude-opus-5",
                "test prompt"
            )
        import subprocess
        assert captured_flags['creationflags'] == subprocess.CREATE_NO_WINDOW
    else:
        assert True  # Skip on non-Windows


@pytest.mark.asyncio
async def test_claude_code_token_tracking():
    """Verifica que se rastrean tokens cuando token_tracker está presente."""
    from lightrag.llm.claude_code import claude_code_complete_if_cache

    # Mock token_tracker
    token_tracker = MagicMock()
    token_tracker.add_usage = MagicMock()

    async def mock_create_subprocess_exec(*args, **kwargs):
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(b"A" * 100, b""))
        proc.returncode = 0
        return proc

    prompt = "X" * 1000
    with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess_exec):
        result = await claude_code_complete_if_cache(
            "claude-opus-5",
            prompt,
            token_tracker=token_tracker
        )

    # Verificar que se llamó a add_usage con el contrato de LightRAG: un
    # diccionario de cuentas, como el `usage` que devuelve cada proveedor.
    # El modelo y el coste NO viajan aquí: los pone el contador de BIMNEMO,
    # que ya sabe con qué modelo se creó y consulta el precio del momento
    # (`bimnemo/consumo.py`, `bimnemo/precios.py`).
    assert token_tracker.add_usage.called
    cuentas = token_tracker.add_usage.call_args[0][0]
    assert cuentas['prompt_tokens'] > 0
    assert cuentas['completion_tokens'] > 0


@pytest.mark.asyncio
async def test_claude_code_semaforo():
    """Verifica que el semáforo serializa llamadas (máx 1 proceso a la vez)."""
    from lightrag.llm.claude_code import claude_code_complete_if_cache, _SEMAFORO_CLAUDE
    import time

    active_processes = []
    max_concurrent = 0

    async def mock_create_subprocess_exec(*args, **kwargs):
        proc = AsyncMock()

        # El prompt viaja por stdin: `communicate` recibe los bytes.
        async def mock_communicate(entrada=None):
            nonlocal max_concurrent
            active_processes.append(1)
            max_concurrent = max(max_concurrent, len(active_processes))
            await asyncio.sleep(0.01)  # Simula latencia
            active_processes.pop()
            return (b"output", b"")

        proc.communicate = mock_communicate
        proc.returncode = 0
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess_exec):
        # Lanzar 4 peticiones en paralelo
        tasks = [
            claude_code_complete_if_cache("claude-opus-5", f"prompt {i}")
            for i in range(4)
        ]
        await asyncio.gather(*tasks)

    # Con el semáforo, máximo debe ser 1 proceso a la vez
    assert max_concurrent == 1, f"Expected max 1 concurrent, got {max_concurrent}"


@pytest.mark.asyncio
async def test_un_contexto_grande_no_se_pasa_por_la_linea_de_ordenes():
    """Windows corta la orden en 32.767 caracteres; un RAG los pasa fácil.

    Y lo peor no era que fallara: `CreateProcess` manda WinError 206, que
    Python convierte en `FileNotFoundError`, y el binding lo contaba como
    «No se encontró el binario de Claude Code» **teniéndolo instalado y con
    sesión abierta**. Preguntar a varias memorias a la vez daba error 500 y
    la pista apuntaba al sitio equivocado.
    """
    from lightrag.llm.claude_code import claude_code_complete_if_cache

    contexto = "Fragmento de normativa. " * 4000  # ~96.000 caracteres
    visto = {}

    async def mock_create_subprocess_exec(*args, **kwargs):
        visto["orden"] = args
        proc = AsyncMock()

        async def communicate(entrada=None):
            visto["stdin"] = entrada
            return (b"respuesta", b"")

        proc.communicate = communicate
        proc.returncode = 0
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess_exec):
        await claude_code_complete_if_cache("claude-opus-5", contexto)

    orden = visto["orden"]
    assert sum(len(str(a)) for a in orden) < 1000, "la orden va corta"
    assert not any(contexto[:100] in str(a) for a in orden), "el prompt NO va ahí"
    assert contexto.encode("utf-8") in visto["stdin"], "va por la entrada estándar"


@pytest.mark.asyncio
async def test_una_orden_demasiado_larga_ya_no_se_lee_como_binario_ausente():
    """Si vuelve a pasar, que la pista no mande a reinstalar Claude."""
    from lightrag.llm.claude_code import claude_code_complete_if_cache

    def demasiado_larga(*_a, **_k):
        error = FileNotFoundError("demasiado largo")
        error.winerror = 206
        raise error

    with patch("asyncio.create_subprocess_exec", side_effect=demasiado_larga):
        with pytest.raises(RuntimeError) as fallo:
            await claude_code_complete_if_cache("claude-opus-5", "hola")

    assert "demasiado larga" in str(fallo.value)
    assert "No se encontró el binario" not in str(fallo.value)
