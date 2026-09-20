"""Gestor de instancias por NEMO: pereza, reutilización, desalojo y difusión.

Se prueba contra una instancia falsa, no contra ``LightRAG``: lo que hay que
fijar aquí es el ciclo de vida —cuándo se abre, cuándo se reutiliza, cuándo se
cierra— y eso no necesita un motor real. Que dos workspaces no se contaminen
ya lo prueba ``tests/workspace/``.

Lo que estos tests protegen:

* Una NEMO no cuesta nada hasta que se usa.
* Dos peticiones simultáneas sobre la misma NEMO abren UNA instancia, no dos
  escribiendo los mismos ficheros.
* Al desalojar se CIERRA, que es lo que vuelca lo pendiente a disco.
* En una difusión, el fallo de una NEMO no deja sin respuesta a las demás.
"""

from __future__ import annotations

import asyncio

import pytest

from lightrag.api.bimnemo.nemo_manager import NemoManager

pytestmark = pytest.mark.offline


class FakeRag:
    """Lo mínimo que el gestor usa de una instancia de LightRAG."""

    def __init__(self, workspace: str, *, retraso: float = 0.0):
        self.workspace = workspace
        self.retraso = retraso
        self.veces_inicializada = 0
        self.veces_cerrada = 0

    async def initialize_storages(self):
        if self.retraso:
            await asyncio.sleep(self.retraso)
        self.veces_inicializada += 1

    async def finalize_storages(self):
        self.veces_cerrada += 1


def hacer_gestor(max_live: int = 4, retraso: float = 0.0):
    creadas: list[FakeRag] = []

    def factory(workspace: str) -> FakeRag:
        rag = FakeRag(workspace, retraso=retraso)
        creadas.append(rag)
        return rag

    return NemoManager(factory=factory, max_live=max_live), creadas


# --- Pereza y reutilización -------------------------------------------------


@pytest.mark.asyncio
async def test_no_se_construye_nada_hasta_que_se_pide():
    gestor, creadas = hacer_gestor()
    assert creadas == []
    assert gestor.live_ids() == []


@pytest.mark.asyncio
async def test_la_primera_peticion_construye_e_inicializa():
    gestor, creadas = hacer_gestor()

    rag = await gestor.get("Obra")

    assert len(creadas) == 1
    assert rag.workspace == "Obra"
    assert rag.veces_inicializada == 1
    assert gestor.live_ids() == ["Obra"]


@pytest.mark.asyncio
async def test_las_siguientes_peticiones_reutilizan_la_misma():
    gestor, creadas = hacer_gestor()

    primera = await gestor.get("Obra")
    segunda = await gestor.get("Obra")

    assert primera is segunda
    assert len(creadas) == 1
    assert primera.veces_inicializada == 1


@pytest.mark.asyncio
async def test_cada_nemo_recibe_su_propio_workspace():
    gestor, _ = hacer_gestor()

    a = await gestor.get("Obra_A")
    b = await gestor.get("Obra_B")

    assert a is not b
    assert (a.workspace, b.workspace) == ("Obra_A", "Obra_B")


@pytest.mark.asyncio
async def test_la_nemo_base_usa_el_workspace_vacio():
    gestor, _ = hacer_gestor()
    rag = await gestor.get("")
    assert rag.workspace == ""


# --- Concurrencia -----------------------------------------------------------


@pytest.mark.asyncio
async def test_dos_peticiones_a_la_vez_abren_una_sola_instancia():
    """Sin el cerrojo por NEMO se construirían DOS instancias del mismo
    workspace, y las dos escribirían los mismos ficheros."""
    gestor, creadas = hacer_gestor(retraso=0.05)

    a, b = await asyncio.gather(gestor.get("Obra"), gestor.get("Obra"))

    assert a is b
    assert len(creadas) == 1
    assert a.veces_inicializada == 1


@pytest.mark.asyncio
async def test_nemos_distintas_se_abren_en_paralelo():
    gestor, _ = hacer_gestor(max_live=4, retraso=0.05)

    inicio = asyncio.get_event_loop().time()
    await asyncio.gather(gestor.get("A"), gestor.get("B"), gestor.get("C"))
    transcurrido = asyncio.get_event_loop().time() - inicio

    # En serie serían ~0,15 s. Se comprueba que no se serializan, con holgura
    # para no depender de la velocidad de la máquina.
    assert transcurrido < 0.12


# --- Desalojo ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_al_pasar_del_tope_se_desaloja_la_menos_usada():
    gestor, creadas = hacer_gestor(max_live=2)

    await gestor.get("A")
    await gestor.get("B")
    await gestor.get("C")

    assert "A" not in gestor.live_ids()
    assert set(gestor.live_ids()) == {"B", "C"}


@pytest.mark.asyncio
async def test_el_desalojo_cierra_la_instancia():
    """Soltar la referencia sin cerrar dejaría escrituras sin volcar a disco."""
    gestor, creadas = hacer_gestor(max_live=1)

    primera = await gestor.get("A")
    await gestor.get("B")

    assert primera.veces_cerrada == 1


@pytest.mark.asyncio
async def test_usar_una_nemo_la_protege_del_desalojo():
    gestor, _ = hacer_gestor(max_live=2)

    a = await gestor.get("A")
    await gestor.get("B")
    await gestor.get("A")  # A vuelve a ser la más reciente
    await gestor.get("C")

    assert set(gestor.live_ids()) == {"A", "C"}
    assert a.veces_cerrada == 0


@pytest.mark.asyncio
async def test_la_nemo_recien_pedida_nunca_se_desaloja():
    gestor, _ = hacer_gestor(max_live=1)
    await gestor.get("A")
    rag = await gestor.get("B")
    assert gestor.live_ids() == ["B"]
    assert rag.veces_cerrada == 0


@pytest.mark.asyncio
async def test_una_nemo_desalojada_se_reabre_al_volver_a_pedirla():
    gestor, creadas = hacer_gestor(max_live=1)

    await gestor.get("A")
    await gestor.get("B")
    de_nuevo = await gestor.get("A")

    assert de_nuevo.veces_inicializada == 1
    assert len(creadas) == 3  # A, B y A otra vez


# --- Cierre -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_cerrar_una_nemo_suelta_sus_ficheros():
    """El borrado necesita esto: Windows se niega a borrar ficheros abiertos."""
    gestor, _ = hacer_gestor()

    rag = await gestor.get("A")
    await gestor.close("A")

    assert rag.veces_cerrada == 1
    assert gestor.live_ids() == []


@pytest.mark.asyncio
async def test_cerrar_todas_cierra_cada_una_y_bloquea_el_gestor():
    gestor, creadas = hacer_gestor()

    await gestor.get("A")
    await gestor.get("B")
    await gestor.close_all()

    assert all(r.veces_cerrada == 1 for r in creadas)
    assert gestor.live_ids() == []
    with pytest.raises(RuntimeError, match="cerrado"):
        await gestor.get("A")


@pytest.mark.asyncio
async def test_un_fallo_al_cerrar_no_impide_cerrar_las_demas():
    fallonas: list[FakeRag] = []

    def factory(workspace: str) -> FakeRag:
        rag = FakeRag(workspace)
        if workspace == "Rota":

            async def revienta():
                raise OSError("disco ocupado")

            rag.finalize_storages = revienta  # type: ignore[method-assign]
        fallonas.append(rag)
        return rag

    gestor = NemoManager(factory=factory, max_live=4)
    await gestor.get("Rota")
    await gestor.get("Sana")

    await gestor.close_all()

    sana = next(r for r in fallonas if r.workspace == "Sana")
    assert sana.veces_cerrada == 1


# --- Difusión ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_map_ejecuta_sobre_cada_nemo_y_devuelve_por_nemo():
    gestor, _ = hacer_gestor(max_live=4)

    async def accion(nemo_id, rag):
        return f"{nemo_id}:{rag.workspace}"

    resultado = await gestor.map(["A", "B", "C"], accion)

    assert resultado == {"A": "A:A", "B": "B:B", "C": "C:C"}


@pytest.mark.asyncio
async def test_en_una_difusion_el_fallo_de_una_no_tumba_al_resto():
    """Una memoria rota no debe dejar sin respuesta a las otras cinco."""
    gestor, _ = hacer_gestor(max_live=4)

    async def accion(nemo_id, rag):
        if nemo_id == "Rota":
            raise ValueError("índice corrupto")
        return "ok"

    resultado = await gestor.map(["A", "Rota", "B"], accion)

    assert resultado["A"] == "ok"
    assert resultado["B"] == "ok"
    assert isinstance(resultado["Rota"], ValueError)


# --- peek -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_peek_no_abre_nada():
    gestor, creadas = hacer_gestor()

    assert gestor.peek("A") is None
    assert creadas == []

    rag = await gestor.get("A")
    assert gestor.peek("A") is rag


# --- Adopción de la instancia del servidor ----------------------------------


@pytest.mark.asyncio
async def test_adoptar_evita_construir_una_segunda_para_el_mismo_workspace():
    """El servidor ya crea e inicializa la instancia por defecto.

    Sin adopción, el gestor construiría otra para el mismo workspace: dos
    objetos escribiendo los mismos ficheros.
    """
    gestor, creadas = hacer_gestor()
    del_servidor = FakeRag("")

    gestor.adopt("", del_servidor, pinned=True)
    obtenida = await gestor.get("")

    assert obtenida is del_servidor
    assert creadas == []  # la fábrica no se llamó
    assert del_servidor.veces_inicializada == 0  # ya venía inicializada


@pytest.mark.asyncio
async def test_una_nemo_fijada_nunca_se_desaloja():
    gestor, _ = hacer_gestor(max_live=1)
    fijada = FakeRag("")
    gestor.adopt("", fijada, pinned=True)

    await gestor.get("A")
    await gestor.get("B")

    assert "" in gestor.live_ids()
    assert fijada.veces_cerrada == 0


@pytest.mark.asyncio
async def test_las_fijadas_no_consumen_el_tope():
    gestor, _ = hacer_gestor(max_live=2)
    gestor.adopt("", FakeRag(""), pinned=True)

    await gestor.get("A")
    await gestor.get("B")

    assert set(gestor.live_ids()) == {"", "A", "B"}


@pytest.mark.asyncio
async def test_cerrar_todas_no_cierra_la_fijada():
    """La finaliza el `lifespan` del servidor, que es quien la creó.

    Cerrarla aquí dejaría a los routers que la usan por referencia directa
    hablando con almacenes ya cerrados.
    """
    gestor, _ = hacer_gestor()
    fijada = FakeRag("")
    gestor.adopt("", fijada, pinned=True)
    propia = await gestor.get("A")

    await gestor.close_all()

    assert fijada.veces_cerrada == 0
    assert propia.veces_cerrada == 1
