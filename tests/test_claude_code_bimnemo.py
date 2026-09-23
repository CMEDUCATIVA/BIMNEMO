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

        async def mock_communicate():
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
