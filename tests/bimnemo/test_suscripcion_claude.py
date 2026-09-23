"""El estado de la suscripción de Claude mira el disco, no la memoria.

`progreso_descarga` recordaba solo lo que había hecho el proceso en marcha, y
ese recuerdo arranca en «inactivo» en cada reinicio del motor: quien instaló
Claude Code ayer volvía a ver «Descarga el binario» hoy, con el binario
puesto y sin forma de iniciar sesión desde la pantalla.
"""

from __future__ import annotations

import pytest

from lightrag.api.bimnemo import suscripcion_claude as claude

pytestmark = pytest.mark.offline


@pytest.fixture
def sin_recuerdo(monkeypatch):
    """Como recién arrancado el motor: no se ha descargado nada desde aquí."""
    monkeypatch.setattr(claude, "_descarga", {"state": "inactivo", "message": ""})


def _hay(monkeypatch, ruta: str = "C:/Users/yo/.local/bin/claude.exe") -> None:
    monkeypatch.setattr(claude, "_hay_binario", lambda: bool(ruta))
    monkeypatch.setattr(claude, "binario", lambda: ruta or "claude")


def test_un_binario_instalado_antes_se_ve_igual(sin_recuerdo, monkeypatch):
    """El caso del usuario: instalado ayer, motor reiniciado hoy."""
    _hay(monkeypatch)

    estado = claude.progreso_descarga()
    assert estado["state"] == "instalado"
    assert estado["path"].endswith("claude.exe"), "saber dónde está es la mitad"


def test_sin_binario_sigue_siendo_inactivo(sin_recuerdo, monkeypatch):
    _hay(monkeypatch, "")
    assert claude.progreso_descarga()["state"] == "inactivo"


def test_una_instalacion_en_curso_manda_sobre_el_disco(monkeypatch):
    """El binario todavía no está: la ventana tiene que seguir con la barra."""
    monkeypatch.setattr(claude, "_descarga", {"state": "descargando", "message": ""})
    _hay(monkeypatch, "")
    assert claude.progreso_descarga()["state"] == "descargando"


def test_un_fallo_de_instalacion_conserva_su_motivo(monkeypatch):
    monkeypatch.setattr(claude, "_descarga", {"state": "error", "message": "no hay red"})
    _hay(monkeypatch, "")

    estado = claude.progreso_descarga()
    assert estado["state"] == "error" and estado["message"] == "no hay red"


def test_borrado_desde_fuera_vuelve_a_inactivo(monkeypatch):
    """Se instaló desde aquí y alguien lo borró por su cuenta."""
    monkeypatch.setattr(claude, "_descarga", {"state": "instalado", "message": ""})
    _hay(monkeypatch, "")
    assert claude.progreso_descarga()["state"] == "inactivo"


def test_sin_binario_el_estado_de_sesion_lo_dice_sin_llamar_a_nadie(monkeypatch):
    """Llamar a un ejecutable que no está solo da un error que no informa."""
    _hay(monkeypatch, "")

    def no_llamar(*_a, **_k):
        raise AssertionError("no hay binario que ejecutar")

    monkeypatch.setattr(claude, "_ejecutar", no_llamar)

    estado = claude.estado()
    assert estado == {
        "logged_in": False,
        "installed": False,
        "path": "",
        "source": "none",
        "message": "claude-cli-no-encontrado",
    }


def test_con_binario_y_sesion_se_dice_cual_y_dónde(monkeypatch):
    _hay(monkeypatch)
    monkeypatch.setattr(
        claude, "_ejecutar", lambda *_a, **_k: (0, '{"loggedIn": true}', "")
    )

    estado = claude.estado()
    assert estado["logged_in"] is True and estado["installed"] is True
    assert estado["path"].endswith("claude.exe")


def test_con_binario_y_sin_sesion_se_distingue_de_no_tener_binario(monkeypatch):
    """Son dos situaciones con botones distintos: no pueden dar lo mismo."""
    _hay(monkeypatch)
    monkeypatch.setattr(
        claude, "_ejecutar", lambda *_a, **_k: (0, '{"loggedIn": false}', "")
    )
    monkeypatch.setattr(claude, "credenciales", lambda: claude.Path("no-existe"))

    estado = claude.estado()
    assert estado["installed"] is True and estado["logged_in"] is False
