"""Cambiar el modelo de embeddings no debe dejar BIMNEMO sin abrir.

El caso real: se cambió OpenAI por Gemini en Configuración IA, las memorias
tenían vectores de OpenAI, el motor se negó a arrancar y —sin consola— el
usuario solo vio que BIMNEMO no abría.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lightrag.api.bimnemo import desktop, embedding_anterior
from lightrag.api.bimnemo.envfile import read_env

pytestmark = pytest.mark.offline

OPENAI = (
    "LLM_BINDING=openai\n"
    "EMBEDDING_BINDING=openai\n"
    "EMBEDDING_BINDING_HOST=https://api.openai.com/v1\n"
    "EMBEDDING_MODEL=text-embedding-3-large\n"
    "EMBEDDING_DIM=3072\n"
    "EMBEDDING_BINDING_API_KEY=sk-de-prueba\n"
)
A_GEMINI = {
    "EMBEDDING_BINDING": "gemini",
    "EMBEDDING_BINDING_HOST": "https://generativelanguage.googleapis.com",
    "EMBEDDING_MODEL": "gemini-embedding-001",
    "EMBEDDING_BINDING_API_KEY": "clave-gemini",
}
FALLO = (
    "Traceback (most recent call last):\n"
    '  File "x.py", line 1\n'
    "lightrag.exceptions.VectorSpaceMismatchError: NanoVectorDBStorage refuses "
    "to serve 'C:\\x\\vdb_entities.json': it holds vectors from a different "
    "embedding space (model 'text-embedding-3-large' -> 'gemini-embedding-001').\n"
)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for clave in embedding_anterior.CLAVES:
        monkeypatch.delenv(clave, raising=False)
    fichero = tmp_path / ".env"
    fichero.write_text(OPENAI, encoding="utf-8")
    return fichero


def _el_motor_arranco_con(monkeypatch, env):
    for clave, valor in read_env(env).items():
        monkeypatch.setenv(clave, valor)


def test_al_cambiar_de_modelo_se_apunta_el_que_funcionaba(env, monkeypatch):
    _el_motor_arranco_con(monkeypatch, env)

    assert embedding_anterior.recordar(env, A_GEMINI)
    apuntado = embedding_anterior.anterior(env)
    assert apuntado["EMBEDDING_MODEL"] == "text-embedding-3-large"
    assert apuntado["EMBEDDING_BINDING_API_KEY"] == "sk-de-prueba"


def test_sin_cambiar_de_modelo_no_se_apunta_nada(env, monkeypatch):
    _el_motor_arranco_con(monkeypatch, env)

    assert not embedding_anterior.recordar(env, {"EMBEDDING_BINDING_API_KEY": "otra"})
    assert embedding_anterior.anterior(env) == {}


def test_un_cambio_que_nunca_arranco_no_pisa_el_bueno(env, monkeypatch):
    """OpenAI → Gemini (sin reiniciar) → Voyage: hay que volver a OpenAI."""
    _el_motor_arranco_con(monkeypatch, env)
    embedding_anterior.recordar(env, A_GEMINI)
    env.write_text(env.read_text(encoding="utf-8").replace(
        "text-embedding-3-large", "gemini-embedding-001"), encoding="utf-8")

    assert not embedding_anterior.recordar(env, {"EMBEDDING_MODEL": "voyage-3"})
    assert embedding_anterior.anterior(env)["EMBEDDING_MODEL"] == "text-embedding-3-large"


def test_restaurar_devuelve_el_modelo_y_comenta_lo_que_sobra(env, monkeypatch):
    _el_motor_arranco_con(monkeypatch, env)
    embedding_anterior.recordar(env, A_GEMINI)
    (env.parent / embedding_anterior.NOMBRE).write_text(
        "EMBEDDING_BINDING=openai\nEMBEDDING_MODEL=text-embedding-3-large\n",
        encoding="utf-8",
    )
    from lightrag.api.bimnemo.envfile import write_env

    write_env(env, A_GEMINI)
    embedding_anterior.restaurar(env)

    valores = read_env(env)
    assert valores["EMBEDDING_MODEL"] == "text-embedding-3-large"
    assert valores["EMBEDDING_BINDING"] == "openai"
    assert "EMBEDDING_BINDING_HOST" not in valores  # el de Gemini, comentado
    assert valores["LLM_BINDING"] == "openai"  # lo demás, intacto


def test_se_reconoce_el_fallo_en_el_registro():
    assert embedding_anterior.desajuste(FALLO) == (
        "text-embedding-3-large",
        "gemini-embedding-001",
    )
    assert embedding_anterior.desajuste("OSError: otra cosa") is None


def test_hay_vectores_mira_todas_las_memorias(tmp_path):
    (tmp_path / "vdb_chunks.json").write_text('{"embedding_dim": 3, "data": []}')
    assert not embedding_anterior.hay_vectores(tmp_path)

    (tmp_path / "Normativas").mkdir()
    (tmp_path / "Normativas" / "vdb_entities.json").write_text(
        '{"embedding_dim": 3, "data": [{"__id__": "ent-1"}]}'
    )
    assert embedding_anterior.hay_vectores(tmp_path)


# --- El lanzador ------------------------------------------------------------


@pytest.fixture()
def lanzador(env, monkeypatch):
    """El lanzador con su registro y su `.env` en la carpeta de prueba."""
    monkeypatch.chdir(env.parent)
    monkeypatch.setattr(desktop, "_repo_root", lambda: env.parent)
    estado = SimpleNamespace(contestar=True, dichos=[])

    def dialogo(texto, *, pregunta=False):
        estado.dichos.append(texto)
        return pregunta and estado.contestar

    monkeypatch.setattr(desktop, "_dialogo", dialogo)
    return estado


def test_si_no_arranca_por_el_embedding_ofrece_volver_y_vuelve(lanzador, env, monkeypatch):
    _el_motor_arranco_con(monkeypatch, env)
    embedding_anterior.recordar(env, A_GEMINI)
    from lightrag.api.bimnemo.envfile import write_env

    write_env(env, A_GEMINI)
    desktop.registro_del_motor().write_text(FALLO, encoding="utf-8")

    assert desktop.avisar_fallo_de_arranque() is True
    assert "¿Volver a «text-embedding-3-large»?" in lanzador.dichos[0]
    assert read_env(env)["EMBEDDING_MODEL"] == "text-embedding-3-large"


def test_si_dice_que_no_el_env_se_queda_como_estaba(lanzador, env, monkeypatch):
    _el_motor_arranco_con(monkeypatch, env)
    embedding_anterior.recordar(env, A_GEMINI)
    from lightrag.api.bimnemo.envfile import write_env

    write_env(env, A_GEMINI)
    desktop.registro_del_motor().write_text(FALLO, encoding="utf-8")
    lanzador.contestar = False

    assert desktop.avisar_fallo_de_arranque() is False
    assert read_env(env)["EMBEDDING_MODEL"] == "gemini-embedding-001"


def test_sin_modelo_apuntado_explica_como_arreglarlo(lanzador, env):
    desktop.registro_del_motor().write_text(FALLO, encoding="utf-8")

    assert desktop.avisar_fallo_de_arranque() is False
    assert "EMBEDDING_MODEL" in lanzador.dichos[0]
    assert "gemini-embedding-001" in lanzador.dichos[0]


def test_otro_fallo_dice_la_ultima_linea_y_donde_esta_el_registro(lanzador):
    desktop.registro_del_motor().write_text(
        "INFO: arrancando\nTraceback:\nModuleNotFoundError: No module named 'x'\n"
        "INFO: cerrando\n",
        encoding="utf-8",
    )

    assert desktop.avisar_fallo_de_arranque() is False
    assert "ModuleNotFoundError: No module named 'x'" in lanzador.dichos[0]
    assert desktop.REGISTRO_DEL_MOTOR in lanzador.dichos[0]
