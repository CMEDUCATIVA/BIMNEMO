"""Nombres de archivo que caben en la ruta de Windows, y renombrar los que no."""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
importlib.import_module("lightrag.api.routers.document_routes")
sys.argv = _argv

from fastapi import HTTPException  # noqa: E402

from lightrag.api.bimnemo import nombres, stats  # noqa: E402
from lightrag.base import DocStatus  # noqa: E402

pytestmark = pytest.mark.offline

#: La carpeta real de la memoria donde fallaron las bases estándar.
RAIZ = (
    len(
        r"C:\Users\Administrador\AppData\Local\Programs\BIMNEMO\inputs\Normativas_BIM\__parsed__"
    )
    + 1
)
BASES_16 = (
    "7614342-16-bases-estandar-concurso-publico-abreviado-para-la-contratacion-"
    "de-expertos-y-gerentes-de-proyectos.docx"
)


def test_el_limite_cuadra_con_lo_que_paso_de_verdad():
    """57 caracteres se indexaron; 61 fallaron. En esa memoria caben 57."""
    limite = nombres.maximo(RAIZ, ".docx")
    assert limite == 57
    ok = "7614342-5-bases-estandar-licitacion-publica-de-obras.docx"
    mal = "7614342-5-bases-estandar-licitacion-publica-de-obras (1).docx"
    assert nombres.problemas(ok, limite) == []
    assert nombres.problemas(mal, limite)


def test_una_carpeta_mas_larga_deja_menos_sitio():
    assert nombres.maximo(RAIZ + 20, ".docx") < nombres.maximo(RAIZ, ".docx")


@pytest.mark.parametrize(
    "nombre,dice",
    [
        ("acta: final.docx", "no admite"),
        ("CON.docx", "reservado"),
        ("informe .docx", ""),  # un espacio antes de la extensión sí vale
        ("informe..", "punto"),
        ("   .docx", "vacío"),
    ],
)
def test_lo_que_windows_no_admite(nombre, dice):
    fallos = " ".join(nombres.problemas(nombre, 57))
    assert dice in fallos if dice else fallos == ""


def test_un_nombre_repetido_no_sirve():
    assert nombres.problemas("a.docx", 57, frozenset({"A.docx"}))


def test_la_sugerencia_conserva_el_codigo_y_lo_que_distingue():
    """El principio se repite en toda la familia; lo que la distingue va al final."""
    propuesta = nombres.sugerir(BASES_16, 57)
    assert propuesta.startswith("7614342-16")
    assert "expertos" in propuesta and "gerentes" in propuesta
    assert propuesta.endswith(".docx")
    assert nombres.problemas(propuesta, 57) == []


def test_la_sugerencia_no_choca_con_uno_que_ya_existe():
    original = "7614342-5-bases-estandar-licitacion-publica-de-obras.docx"
    propuesta = nombres.sugerir(original, 57, frozenset({original}))
    assert propuesta != original and not nombres.problemas(
        propuesta, 57, frozenset({original})
    )


def test_un_nombre_que_cabe_se_deja_como_esta():
    assert nombres.sugerir("Informe final.docx", 57) == "Informe final.docx"


# --- el aviso del Panel dice cuáles son --------------------------------------

LARGO = (
    "[WinError 206] El nombre del archivo o la extensión es demasiado largo: "
    "'C:\\\\Users\\\\x\\\\" + "a" * 250 + "'"
)


def _doc(nombre, error):
    return SimpleNamespace(
        status=DocStatus.FAILED,
        error_msg=error,
        file_path=nombre,
        chunks_count=0,
        content_length=0,
    )


def test_el_panel_nombra_los_archivos_de_nombre_largo():
    documentos = {f"d{i}": _doc(f"bases-{i}.docx", LARGO) for i in range(4)}
    rag = SimpleNamespace(doc_status=_DocStatus(documentos))
    resumen = asyncio.run(stats.summarize_memory(rag))
    aviso = resumen["failed_reason"]
    assert "4 archivos" in aviso
    assert "«bases-0.docx»" in aviso and "y 2 más" in aviso
    assert "Renombrar" in aviso


def test_cada_fila_sabe_si_se_arregla_renombrando():
    assert stats.nombre_demasiado_largo(LARGO)
    assert not stats.nombre_demasiado_largo("RateLimitError: insufficient_quota")


# --- la ruta de renombrar ----------------------------------------------------


class _DocStatus:
    def __init__(self, registros):
        self.registros = registros

    async def get_docs_by_statuses(self, estados, strict=False):
        return dict(self.registros)

    async def get_by_id(self, doc_id):
        return self.registros.get(doc_id)


def _ruta(tmp_path, registros, monkeypatch):
    import lightrag.api.routers.document_routes as dr
    from lightrag.api.routers.bimnemo_nombres_routes import (
        create_bimnemo_nombres_routes,
    )

    rag = SimpleNamespace(workspace="obra", doc_status=_DocStatus(registros))
    indexados: list[Path] = []

    async def indexar(_rag, ruta, *a, **k):
        indexados.append(ruta)

    async def reservar(*a, **k):
        return True, None

    async def soltar(*a, **k):
        return None

    async def borrar(_rag, _gestor, ids, *a, **k):
        for doc_id in ids:
            registros.pop(doc_id, None)

    monkeypatch.setattr(dr, "pipeline_index_file", indexar)
    monkeypatch.setattr(dr, "_acquire_destructive_busy", reservar)
    monkeypatch.setattr(dr, "_release_destructive_busy", soltar)
    monkeypatch.setattr(dr, "background_delete_documents", borrar)

    async def resolver(_nemo):
        return rag, tmp_path, None

    manager = SimpleNamespace(base_input_dir=tmp_path)
    router = create_bimnemo_nombres_routes(manager, resolver, None)
    ruta = next(r for r in router.routes if r.path == "/files/rename")
    return ruta.endpoint, indexados


def _pedir(endpoint, viejo, nuevo):
    from lightrag.api.routers.bimnemo_nombres_routes import RenameRequest

    async def todo():
        tareas: set = set()
        respuesta = await endpoint(
            nemo=None, request=RenameRequest(name=viejo, new_name=nuevo), tareas=tareas
        )
        await asyncio.gather(*tareas)
        return respuesta

    return asyncio.run(todo())


def test_renombra_un_fallido_borra_su_registro_y_lo_vuelve_a_leer(
    tmp_path, monkeypatch
):
    (tmp_path / BASES_16).write_bytes(b"docx")
    registros = {"doc-16": _doc(BASES_16, LARGO)}
    endpoint, indexados = _ruta(tmp_path, registros, monkeypatch)

    respuesta = _pedir(endpoint, BASES_16, "BE-16 expertos.docx")

    assert respuesta.status == "renaming"
    assert registros == {}
    assert (tmp_path / "BE-16 expertos.docx").is_file()
    assert not (tmp_path / BASES_16).exists()
    assert indexados == [tmp_path / "BE-16 expertos.docx"]


@pytest.mark.parametrize(
    "nuevo,codigo",
    [
        ("otra-extension.pdf", 400),
        ("x" * 300 + ".docx", 400),
        ("../fuera.docx", 400),
    ],
)
def test_lo_que_no_se_deja_renombrar(tmp_path, monkeypatch, nuevo, codigo):
    (tmp_path / "a.docx").write_bytes(b"docx")
    endpoint, indexados = _ruta(tmp_path, {}, monkeypatch)
    with pytest.raises(HTTPException) as fallo:
        _pedir(endpoint, "a.docx", nuevo)
    assert fallo.value.status_code == codigo
    assert (tmp_path / "a.docx").is_file() and indexados == []


def test_uno_ya_indexado_no_se_toca(tmp_path, monkeypatch):
    (tmp_path / "a.docx").write_bytes(b"docx")
    hecho = SimpleNamespace(status=DocStatus.PROCESSED, file_path="a.docx")
    endpoint, _ = _ruta(tmp_path, {"d": hecho}, monkeypatch)
    with pytest.raises(HTTPException) as fallo:
        _pedir(endpoint, "a.docx", "b.docx")
    assert fallo.value.status_code == 409
