"""Una clave de ejemplo no es una clave guardada."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "valor, puesta",
    [
        ("sk-proj-abc123", True),
        ("AIzaSyD-otra", True),
        ("your_api_key", False),  # la de env.example
        ("your-api-key", False),
        ("  YOUR_API_KEY ", False),
        ("", False),
        ("   ", False),
    ],
)
def test_clave_puesta(valor, puesta):
    from lightrag.api.bimnemo.envfile import clave_puesta

    assert clave_puesta(valor) is puesta
