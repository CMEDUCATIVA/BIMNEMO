"""BIMNEMO extrae en español cuando nadie ha dicho otra cosa.

El idioma es el único ajuste de la pantalla de Configuración que **no se
arregla después**: las entidades guardadas conservan el idioma con el que se
extrajeron, y para unificarlo hay que vaciar la memoria y reindexarla. Un
inglés silencioso —porque falta una variable en el ``.env``— se paga entero.
"""

from __future__ import annotations

import pytest

from lightrag.api.bimnemo.runtime import IDIOMA_POR_DEFECTO

pytestmark = pytest.mark.offline


def test_el_suelo_de_bimnemo_es_el_espanol():
    assert IDIOMA_POR_DEFECTO == "Spanish"


def test_el_motor_usa_ese_mismo_suelo():
    """Si el motor tuviera otro, la pantalla diría una cosa y pasaría otra."""
    from lightrag.constants import DEFAULT_SUMMARY_LANGUAGE

    assert DEFAULT_SUMMARY_LANGUAGE == IDIOMA_POR_DEFECTO


def test_la_pantalla_ensena_el_mismo_que_se_va_a_usar():
    import importlib
    import sys

    argv = sys.argv[:]
    sys.argv = [sys.argv[0]]
    try:
        importlib.import_module("lightrag.api.routers.document_routes")
        rutas = importlib.import_module(
            "lightrag.api.routers.bimnemo_settings_routes"
        )
    finally:
        sys.argv = argv

    assert rutas.DEFAULT_LANGUAGE == IDIOMA_POR_DEFECTO


def test_el_env_del_ejemplo_ya_lo_trae():
    """Es el que se copia en el primer arranque de toda instalación nueva."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    lineas = (raiz / "env.example").read_text(encoding="utf-8").splitlines()
    puestas = [l for l in lineas if l.strip().startswith("SUMMARY_LANGUAGE=")]
    assert puestas == [f"SUMMARY_LANGUAGE={IDIOMA_POR_DEFECTO}"]


def test_el_env_minimo_de_emergencia_tambien(tmp_path, monkeypatch):
    """Sin `env.example` del que partir, el idioma no puede perderse."""
    from lightrag.api.bimnemo import desktop

    # Sin `env.example` en la raíz falsa, cae en la rama de emergencia.
    monkeypatch.setattr(desktop, "_repo_root", lambda: tmp_path)
    desktop.asegurar_env()

    assert f"SUMMARY_LANGUAGE={IDIOMA_POR_DEFECTO}" in (
        tmp_path / ".env"
    ).read_text(encoding="utf-8")
