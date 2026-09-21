"""Qué memoria queda abierta, y los resguardos de los tres diálogos."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.offline

LISTA: dict[str, Any] = {
    "nemos": [
        {"id": "", "name": "General", "protected": True, "live": True},
        {"id": "proyecto-norte", "name": "Proyecto Norte", "protected": False},
        {"id": "obra-sur", "name": "Obra Sur", "protected": False},
    ],
    "default": "",
}


class MotorFalso:
    """Contesta lo que le digan, y apunta a quién le hablaron."""

    def __init__(self) -> None:
        self.base = "http://127.0.0.1:0"
        self.memoria = ""
        self.pedidos: list[tuple[str, str]] = []
        self.respuesta: Any = LISTA
        self.fallo = ""

    def usar_memoria(self, nemo: str) -> None:
        self.memoria = nemo

    def _contestar(self, metodo, ruta, bien, mal):
        self.pedidos.append((metodo, ruta))
        if self.fallo and mal:
            mal(self.fallo)
        elif bien:
            bien(self.respuesta)

    def get(self, ruta, bien=None, mal=None):
        self._contestar("GET", ruta, bien, mal)

    def post(self, ruta, cuerpo=None, bien=None, mal=None):
        self._contestar("POST", ruta, bien, mal)

    def parchear(self, ruta, cuerpo=None, bien=None, mal=None):
        self._contestar("PATCH", ruta, bien, mal)

    def borrar(self, ruta, cuerpo=None, bien=None, mal=None):
        self._contestar("DELETE", ruta, bien, mal)


@pytest.fixture()
def ajustes_aparte(tmp_path, monkeypatch, aplicacion):
    """Los ajustes, en un fichero de usar y tirar.

    Sin esto una prueba escribiría en el registro de Windows de quien la
    ejecuta y le cambiaría la memoria abierta de su BIMNEMO de verdad.
    """
    from PySide6.QtCore import QSettings

    from lightrag.api.bimnemo.nativo import memorias

    guardados = QSettings(str(tmp_path / "bimnemo.ini"), QSettings.IniFormat)
    monkeypatch.setattr(memorias, "ajustes", lambda: guardados)
    return guardados


@pytest.fixture()
def memorias(ajustes_aparte):
    from lightrag.api.bimnemo.nativo.memorias import Memorias

    registro = Memorias(MotorFalso())
    registro.cargar()
    return registro


# --- Cuál queda abierta -----------------------------------------------------


def test_al_arrancar_se_abre_la_de_por_defecto(memorias):
    assert memorias.actual == ""
    assert memorias.nombre() == "General"


def test_elegir_otra_se_lo_dice_al_motor(memorias):
    """El motor es quien enruta: si no se entera, no cambia nada de nada."""
    avisos: list[str] = []
    memorias.cambiada.connect(avisos.append)

    memorias.elegir("obra-sur")

    assert memorias.motor.memoria == "obra-sur"
    assert avisos == ["obra-sur"]


def test_se_recuerda_entre_sesiones(memorias, ajustes_aparte):
    from lightrag.api.bimnemo.nativo.memorias import Memorias

    memorias.elegir("obra-sur")

    otra = Memorias(MotorFalso())
    otra.cargar()
    assert otra.actual == "obra-sur"


def test_una_memoria_recordada_que_ya_no_existe_no_se_cree(memorias, ajustes_aparte):
    """Insistir en una memoria fantasma deja todas las pantallas con errores."""
    from lightrag.api.bimnemo.nativo.memorias import Memorias

    ajustes_aparte.setValue("memoria", "la-que-borro-otro")

    otra = Memorias(MotorFalso())
    otra.cargar()
    assert otra.actual == ""


def test_lo_que_no_esta_en_la_lista_no_tiene_ficha(memorias):
    assert memorias.ficha("no-existe") == {}
    assert memorias.nombre("no-existe") == "—"


# --- Crear ------------------------------------------------------------------


def test_crear_sin_nombre_no_llama_al_motor(ajustes_aparte):
    from lightrag.api.bimnemo.nativo.memorias import DialogoCrear

    motor = MotorFalso()
    dialogo = DialogoCrear(motor)
    dialogo._crear()

    assert dialogo.error.text() == "Escribe un nombre para la memoria."
    assert motor.pedidos == []


def test_crear_enseña_tal_cual_lo_que_diga_el_motor(ajustes_aparte):
    """Un 409 ya explica cuál es el choque; reescribirlo solo quita detalle."""
    from lightrag.api.bimnemo.nativo.memorias import DialogoCrear

    motor = MotorFalso()
    motor.fallo = "Ya existe una memoria «Obra Sur»."
    dialogo = DialogoCrear(motor)
    dialogo.campo.setText("Obra Sur")
    dialogo._crear()

    assert dialogo.error.text() == "Ya existe una memoria «Obra Sur»."
    assert dialogo.aceptar.isEnabled()


# --- Renombrar --------------------------------------------------------------


def test_renombrar_no_deja_guardar_si_nada_cambio(ajustes_aparte):
    """Un botón activo que no va a hacer nada es una promesa que no se cumple."""
    from lightrag.api.bimnemo.nativo.memorias import DialogoRenombrar

    dialogo = DialogoRenombrar(
        MotorFalso(), {"id": "obra-sur", "name": "Obra Sur"}, False
    )
    assert dialogo.aceptar.isEnabled() is False

    dialogo.campo.setText("Obra Sur 2")
    assert dialogo.aceptar.isEnabled() is True


def test_marcar_por_defecto_ya_basta_para_guardar(ajustes_aparte):
    from lightrag.api.bimnemo.nativo.memorias import DialogoRenombrar

    dialogo = DialogoRenombrar(
        MotorFalso(), {"id": "obra-sur", "name": "Obra Sur"}, False
    )
    dialogo.casilla.setChecked(True)
    assert dialogo.aceptar.isEnabled() is True


def test_la_que_ya_es_por_defecto_no_ofrece_desmarcarla(ajustes_aparte):
    """Quitar la marca no es una operación que exista en el motor."""
    from lightrag.api.bimnemo.nativo.memorias import DialogoRenombrar

    dialogo = DialogoRenombrar(MotorFalso(), {"id": "", "name": "General"}, True)
    assert dialogo.casilla.isChecked() is True
    assert dialogo.casilla.isEnabled() is False


def test_renombrar_pide_el_patch_de_esa_memoria(ajustes_aparte):
    from lightrag.api.bimnemo.nativo.memorias import DialogoRenombrar

    motor = MotorFalso()
    dialogo = DialogoRenombrar(motor, {"id": "obra-sur", "name": "Obra Sur"}, False)
    dialogo.campo.setText("Obra Este")
    dialogo._guardar()

    assert ("PATCH", "/bimnemo/nemos?nemo=obra-sur") in motor.pedidos


# --- Borrar -----------------------------------------------------------------


def test_borrar_exige_el_nombre_exacto(ajustes_aparte):
    """Es la única operación irreversible: un «¿seguro?» se contesta sin leer."""
    from lightrag.api.bimnemo.nativo.memorias import DialogoBorrar

    dialogo = DialogoBorrar(MotorFalso(), {"id": "obra-sur", "name": "Obra Sur"})
    assert dialogo.aceptar.isEnabled() is False

    dialogo.campo.setText("obra sur")
    assert dialogo.aceptar.isEnabled() is False

    dialogo.campo.setText("Obra Sur")
    assert dialogo.aceptar.isEnabled() is True


def test_la_memoria_base_se_vacia_y_despues_se_quita(ajustes_aparte):
    """En ese orden: con documentos dentro, el motor se niega a quitarla."""
    from lightrag.api.bimnemo.nativo.memorias import DialogoBorrar

    motor = MotorFalso()
    # Una respuesta para todo: el vaciado mira `status`, y al quitarla del
    # índice solo importa que conteste.
    motor.respuesta = {"status": "success", "message": "vaciada"}
    dialogo = DialogoBorrar(motor, {"id": "", "name": "General", "protected": True})
    dialogo.campo.setText("General")
    dialogo._borrar()

    borrados = [ruta for verbo, ruta in motor.pedidos if verbo == "DELETE"]
    assert borrados == [
        "/documents?delete_parsed_files=true&clear_llm_cache=true",
        "/bimnemo/nemos?nemo=",
    ]
    assert dialogo.borrada is True


def test_si_no_se_puede_vaciar_la_base_no_se_quita(ajustes_aparte):
    """Un vaciado a medias —el motor indexando, por ejemplo— para aquí."""
    from lightrag.api.bimnemo.nativo.memorias import DialogoBorrar

    motor = MotorFalso()
    motor.respuesta = {
        "status": "busy",
        "message": "El motor está procesando documentos.",
    }
    dialogo = DialogoBorrar(motor, {"id": "", "name": "General", "protected": True})
    dialogo.campo.setText("General")
    dialogo._borrar()

    borrados = [ruta for verbo, ruta in motor.pedidos if verbo == "DELETE"]
    assert "/bimnemo/nemos?nemo=" not in borrados
    assert dialogo.borrada is False
    assert dialogo.aceptar.isEnabled()


def test_borrar_manda_el_nombre_como_resguardo(ajustes_aparte):
    from lightrag.api.bimnemo.nativo.memorias import DialogoBorrar

    motor = MotorFalso()
    dialogo = DialogoBorrar(motor, {"id": "obra-sur", "name": "Obra Sur"})
    dialogo.campo.setText("Obra Sur")
    dialogo._borrar()

    assert ("DELETE", "/bimnemo/nemos/obra-sur") in motor.pedidos
    assert dialogo.borrada is True
