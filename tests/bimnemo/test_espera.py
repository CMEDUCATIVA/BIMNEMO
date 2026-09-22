"""Reintentar o renombrar con otro documento indexándose: se apunta, no se niega."""

from __future__ import annotations

import asyncio

import pytest

from lightrag.api.bimnemo import espera

pytestmark = pytest.mark.offline


def _correr(corrutina):
    return asyncio.run(corrutina)


def test_prueba_hasta_que_la_memoria_queda_libre():
    intentos = []

    async def intento():
        intentos.append(1)
        return len(intentos) >= 3  # ocupada dos veces, libre a la tercera

    async def todo():
        tareas: set = set()
        espera.apuntar(tareas, "obra-a", "ley.pdf", intento, intervalo=0.01)
        assert espera.en_espera("obra-a") == {"ley.pdf"}
        await asyncio.gather(*tareas)

    _correr(todo())
    assert len(intentos) == 3
    assert espera.en_espera("obra-a") == frozenset()


def test_atiende_por_orden_de_llegada_y_de_una_en_una():
    orden = []

    def hacer(nombre):
        async def intento():
            orden.append(nombre)
            return True

        return intento

    async def todo():
        tareas: set = set()
        for nombre in ("a.docx", "b.docx", "c.docx"):
            espera.apuntar(tareas, "obra-b", nombre, hacer(nombre), intervalo=0.01)
        await asyncio.gather(*tareas)

    _correr(todo())
    assert orden == ["a.docx", "b.docx", "c.docx"]


def test_un_error_abandona_la_accion_y_no_reintenta_sin_fin():
    intentos = []

    async def intento():
        intentos.append(1)
        raise RuntimeError("disco lleno")

    async def todo():
        tareas: set = set()
        espera.apuntar(tareas, "obra-c", "x.docx", intento, intervalo=0.01)
        await asyncio.gather(*tareas)

    _correr(todo())
    assert intentos == [1]
    assert espera.en_espera("obra-c") == frozenset()


def test_cada_memoria_tiene_su_fila():
    assert espera.en_espera("otra") == frozenset()


def test_renombrar_con_la_memoria_ocupada_queda_apuntado(tmp_path, monkeypatch):
    """Antes contestaba «renómbralo cuando termine»; ahora se hace solo."""
    import importlib
    import sys

    _argv = sys.argv[:]
    sys.argv = [sys.argv[0]]
    importlib.import_module("lightrag.api.routers.document_routes")
    sys.argv = _argv

    import lightrag.api.routers.document_routes as dr
    import tests.bimnemo.test_nombres as base

    monkeypatch.setattr(espera, "INTERVALO", 0.01)
    (tmp_path / base.BASES_16).write_bytes(b"docx")
    registros = {"doc-16": base._doc(base.BASES_16, base.LARGO)}
    endpoint, indexados = base._ruta(tmp_path, registros, monkeypatch)

    ocupada = {"veces": 2}

    async def reservar(*a, **k):
        if ocupada["veces"]:
            ocupada["veces"] -= 1
            return False, "busy"
        return True, None

    monkeypatch.setattr(dr, "_acquire_destructive_busy", reservar)
    original = espera.apuntar
    monkeypatch.setattr(
        espera,
        "apuntar",
        lambda t, e, n, i, intervalo=0.01: original(t, e, n, i, intervalo),
    )

    async def todo():
        from lightrag.api.routers.bimnemo_nombres_routes import RenameRequest

        tareas: set = set()
        respuesta = await endpoint(
            nemo=None,
            request=RenameRequest(name=base.BASES_16, new_name="BE-16.docx"),
            tareas=tareas,
        )
        assert respuesta.status == "waiting"
        while tareas:
            await asyncio.gather(*list(tareas))

    _correr(todo())
    assert (tmp_path / "BE-16.docx").is_file()
    assert indexados == [tmp_path / "BE-16.docx"]
