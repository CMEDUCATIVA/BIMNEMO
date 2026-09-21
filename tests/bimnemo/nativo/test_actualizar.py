"""Avisar de una versión nueva y traerla sin reinstalar."""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.offline

HAY = {
    "supported": True,
    "reachable": True,
    "behind": True,
    "installed": "v1.4.0",
    "latest": "v1.4.1",
    "message": "Arreglos del grafo",
}
AL_DIA = {**HAY, "behind": False, "latest": "v1.4.0"}


@pytest.fixture(autouse=True)
def motor_con_identidad(request):
    """El sondeo pregunta primero quién contesta: sin eso no pide nada."""
    if "ventana" in request.fixturenames:
        request.getfixturevalue("ventana").motor.respuestas["/bimnemo/app-build"] = {
            "boot_id": "motor-viejo"
        }


# -- el motor no baja de versión --------------------------------------------


@pytest.mark.parametrize(
    "publicada, instalada, nueva",
    [
        ("v1.4.1", "v1.4.0-nativa", True),
        ("v1.10.0", "v1.9.9", True),
        ("v2", "v1.9", True),
        # El caso que había: la 1.2.3 publicada se ofrecía a quien tenía la
        # 1.4, y «actualizar» le devolvía a la interfaz web.
        ("v1.2.3", "v1.4.0-nativa", False),
        ("v1.4.0", "v1.4.0-nativa", False),
        ("cualquier-cosa", "v1.0", False),
    ],
)
def test_solo_cuenta_como_nueva_una_version_posterior(publicada, instalada, nueva):
    from lightrag.api.bimnemo.paquete import es_mas_nueva

    assert es_mas_nueva(publicada, instalada) is nueva


def test_traer_se_niega_a_bajar_de_version(tmp_path, monkeypatch):
    """La segunda barrera: la que escribe en disco no se fía de la pantalla."""
    from lightrag.api.bimnemo import paquete

    (tmp_path / "VERSION").write_text("v1.4.0-nativa\n", encoding="utf-8")
    monkeypatch.setattr(
        paquete,
        "ultima_version",
        lambda _repo: {"tag_name": "v1.2.3", "zipball_url": "https://ejemplo/zip"},
    )
    descargas = []
    monkeypatch.setattr(paquete, "_descargar", lambda *a: descargas.append(a) or True)

    resultado = paquete.traer("CMEDUCATIVA/BIMNEMO", tmp_path)

    assert resultado["ok"] is False and resultado["reason"] == "older"
    assert descargas == [], "llegó a descargar una versión vieja"
    assert (tmp_path / "VERSION").read_text(encoding="utf-8").strip() == "v1.4.0-nativa"


# -- el aviso en la barra ---------------------------------------------------


def test_con_version_nueva_el_boton_aparece_y_parpadea(ventana):
    ventana.motor.respuestas["/bimnemo/update"] = HAY
    ventana.vigia.mirar()

    boton = ventana.barra.boton_actualizar
    assert not boton.isHidden()
    assert "v1.4.1" in boton.toolTip()

    antes = boton.property("encendido")
    boton._latir()
    assert boton.property("encendido") is (not antes)


def test_al_dia_no_hay_boton(ventana):
    ventana.motor.respuestas["/bimnemo/update"] = AL_DIA
    ventana.vigia.mirar()

    assert ventana.barra.boton_actualizar.isHidden()


# -- el diálogo -------------------------------------------------------------


def test_actualizar_pide_la_actualizacion_al_motor(ventana):
    from lightrag.api.bimnemo.nativo.actualizar import DialogoActualizar

    dialogo = DialogoActualizar(ventana.motor, HAY, ventana)
    dialogo._actualizar()

    assert "/bimnemo/update/apply" in ventana.motor.pedidos
    assert not dialogo.aceptar.isEnabled()


def test_si_ya_estaba_al_dia_no_se_queda_esperando(ventana):
    """El motor contesta «up_to_date» y no se reinicia: esperar sería eterno."""
    from lightrag.api.bimnemo.nativo.actualizar import DialogoActualizar

    ventana.motor.respuestas["/bimnemo/update/apply"] = {
        "status": "up_to_date",
        "message": "Ya tienes la última versión publicada.",
    }
    dialogo = DialogoActualizar(ventana.motor, HAY, ventana)
    dialogo._actualizar()

    assert "última versión" in dialogo.error.text()
    assert dialogo.aceptar.isEnabled()


def test_si_la_descarga_falla_se_dice_enseguida(ventana):
    from lightrag.api.bimnemo.nativo.actualizar import DialogoActualizar

    ventana.motor.respuestas["/bimnemo/update/apply"] = {"status": "updating"}
    ventana.motor.respuestas["/bimnemo/update/progress"] = {
        "state": "failed",
        "message": "No se pudo descargar la versión. Comprueba la conexión.",
    }
    dialogo = DialogoActualizar(ventana.motor, HAY, ventana)
    dialogo._actualizar()
    dialogo._trabajo._mirar()

    assert "Comprueba la conexión" in dialogo.error.text()
    assert dialogo.aceptar.isEnabled()


# -- volver a abrir ---------------------------------------------------------


def test_relanzar_abre_otra_copia_que_espera_a_esta(monkeypatch, aplicacion):
    import os

    from lightrag.api.bimnemo.nativo import actualizar

    lanzadas = []
    monkeypatch.setattr(
        actualizar.subprocess, "Popen", lambda orden, **kw: lanzadas.append(orden)
    )
    cerrada = []
    monkeypatch.setattr(actualizar.QApplication, "quit", lambda: cerrada.append(1))

    actualizar.relanzar("http://127.0.0.1:9700")

    orden = lanzadas[0]
    assert orden[:3] == [sys.executable, "-m", "lightrag.api.bimnemo.desktop"]
    assert orden[orden.index("--esperar-pid") + 1] == str(os.getpid())
    assert orden[orden.index("--port") + 1] == "9700"
    assert cerrada == [1]


def test_la_copia_nueva_espera_a_que_la_vieja_termine():
    import time

    from lightrag.api.bimnemo.desktop import esperar_a_que_termine

    vieja = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.2)"])
    inicio = time.monotonic()
    esperar_a_que_termine(vieja.pid, segundos=10)

    assert vieja.poll() is not None, "volvió antes de que terminara"
    assert time.monotonic() - inicio < 8
    # Y con un proceso que ya no existe, no espera nada.
    inicio = time.monotonic()
    esperar_a_que_termine(vieja.pid, segundos=10)
    assert time.monotonic() - inicio < 2


# -- sin ventanas negras ----------------------------------------------------


def test_los_saltos_de_linea_no_cuentan_como_dependencias_nuevas(tmp_path):
    """El mismo pyproject con CRLF y con LF: pip no tiene nada que hacer."""
    from lightrag.api.bimnemo.paquete import pyproject_cambio

    (tmp_path / "pyproject.toml").write_bytes(b'[project]\nname = "x"\n')
    assert pyproject_cambio(tmp_path, b'[project]\r\nname = "x"\r\n') is False
    assert pyproject_cambio(tmp_path, b'[project]\r\nname = "y"\r\n') is True


def test_pip_y_git_se_lanzan_sin_ventana(monkeypatch):
    """BIMNEMO corre sin consola: lo que lance de consola recibiría una."""
    from lightrag.api.bimnemo import actualizacion

    banderas = []

    class Hecho:
        returncode, stdout, stderr = 0, "", ""

    def falso(orden, **kw):
        banderas.append(kw.get("creationflags", 0))
        return Hecho()

    monkeypatch.setattr(actualizacion.subprocess, "run", falso)
    actualizacion.instalar_dependencias()
    actualizacion._git("status")

    assert banderas == [actualizacion.SIN_VENTANA] * 2
    if sys.platform == "win32":
        assert actualizacion.SIN_VENTANA != 0
