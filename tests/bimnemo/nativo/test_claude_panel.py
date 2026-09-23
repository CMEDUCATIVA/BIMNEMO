"""El panel de la suscripción enseña los botones que sirven, y solo esos.

El fallo que lo motivó: con Claude Code ya instalado, la pantalla seguía
diciendo «Descarga el binario» y ofreciendo *Descargar* y *Desinstalar*, sin
manera de iniciar sesión. El estado de la instalación era un recuerdo del
proceso en marcha —se perdía al reiniciar el motor— en vez de una mirada al
disco.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.offline


class MotorFalso:
    """Contesta lo que se le diga a cada ruta y apunta lo que le piden."""

    def __init__(self, respuestas: dict[str, Any]) -> None:
        self.base = "http://127.0.0.1:0"
        self.respuestas = respuestas
        self.pedidos: list[tuple[str, str]] = []

    def _contestar(self, verbo: str, ruta: str, bien) -> None:
        self.pedidos.append((verbo, ruta))
        for clave, respuesta in self.respuestas.items():
            if clave in ruta and bien is not None:
                bien(respuesta)
                return

    def get(self, ruta, bien=None, mal=None):
        self._contestar("GET", ruta, bien)

    def post(self, ruta, cuerpo=None, bien=None, mal=None):
        self._contestar("POST", ruta, bien)

    def borrar(self, ruta, cuerpo=None, bien=None, mal=None):
        self._contestar("DELETE", ruta, bien)


INSTALADO_CON_SESION = {
    "download-progress": {
        "state": "instalado",
        "message": "",
        "path": "C:/Users/yo/.local/bin/claude.exe",
    },
    "/status": {
        "logged_in": True,
        "installed": True,
        "path": "C:/Users/yo/.local/bin/claude.exe",
        "source": "cli",
        "message": "",
    },
}

SIN_BINARIO = {
    "download-progress": {"state": "inactivo", "message": ""},
}


def _panel(aplicacion, respuestas):
    from lightrag.api.bimnemo.nativo.claude_panel import PanelSuscripcion

    panel = PanelSuscripcion(MotorFalso(respuestas))
    panel.refrescar()
    return panel


# --- sin binario ---------------------------------------------------------


def test_sin_binario_solo_se_ofrece_instalar(aplicacion):
    """Desinstalar lo que no está, o entrar sin programa, no son opciones."""
    panel = _panel(aplicacion, SIN_BINARIO)

    assert not panel.fila_descarga.isHidden()
    assert panel.fila_sesion.isHidden(), "ni sesión ni desinstalar"
    assert "Descarga el binario" in panel.estado.text()


def test_el_boton_dice_que_descarga_e_instala(aplicacion):
    panel = _panel(aplicacion, SIN_BINARIO)
    assert panel.boton_descargar.text() == "Descargar e instalar"


# --- con binario ---------------------------------------------------------


def test_con_binario_aparecen_sesion_y_desinstalar(aplicacion):
    """Lo que pidió el usuario: iniciar, cerrar, el estado y desinstalar."""
    panel = _panel(aplicacion, INSTALADO_CON_SESION)

    assert panel.fila_descarga.isHidden(), "ya está instalado: nada que descargar"
    assert not panel.fila_sesion.isHidden()
    assert not panel.boton_borrar.isHidden()
    assert panel.boton_login.text() == "Iniciar sesión"
    assert panel.boton_logout.text() == "Cerrar sesión"


def test_el_estado_dice_si_hay_sesion_y_donde_esta_el_binario(aplicacion):
    panel = _panel(aplicacion, INSTALADO_CON_SESION)

    texto = panel.estado.text()
    assert "Sesión de Claude iniciada" in texto
    assert "claude.exe" in texto, "saber dónde está es la mitad del diagnóstico"
    # Con sesión, entrar otra vez no hace nada; salir sí.
    assert not panel.boton_login.isEnabled()
    assert panel.boton_logout.isEnabled()


def test_instalado_pero_sin_sesion_lo_dice_y_deja_entrar(aplicacion):
    sin_sesion = dict(
        INSTALADO_CON_SESION,
        **{
            "/status": {
                "logged_in": False,
                "installed": True,
                "path": "C:/Users/yo/.local/bin/claude.exe",
                "source": "cli",
                "message": "sin sesión",
            }
        },
    )
    panel = _panel(aplicacion, sin_sesion)

    assert "no hay sesión" in panel.estado.text()
    assert panel.boton_login.isEnabled()
    assert not panel.boton_logout.isEnabled()
    # Probar la conexión sin sesión solo puede fallar: no se ofrece.
    assert not panel.boton_probar.isEnabled()


# --- desinstalar ---------------------------------------------------------


def test_desinstalar_pregunta_antes_y_borra_el_binario(aplicacion):
    panel = _panel(aplicacion, INSTALADO_CON_SESION)
    panel.confirmar = lambda *_a, **_k: True

    panel._borrar_binario()

    assert ("DELETE", "/bimnemo/claude-subscription/download") in panel.motor.pedidos


def test_si_se_dice_que_no_no_se_borra_nada(aplicacion):
    panel = _panel(aplicacion, INSTALADO_CON_SESION)
    panel.confirmar = lambda *_a, **_k: False

    panel._borrar_binario()

    assert not any(v == "DELETE" for v, _ in panel.motor.pedidos)


# --- instalación en curso ------------------------------------------------


def test_mientras_instala_se_ve_la_barra_y_ningun_boton(aplicacion):
    panel = _panel(aplicacion, {"download-progress": {"state": "descargando"}})

    assert not panel.barra.isHidden()
    assert panel.fila_descarga.isHidden() and panel.fila_sesion.isHidden()
    panel.detener()


def test_un_fallo_de_instalacion_se_cuenta_y_deja_reintentar(aplicacion):
    panel = _panel(
        aplicacion,
        {"download-progress": {"state": "error", "message": "no hay red"}},
    )

    assert "no hay red" in panel.estado.text()
    assert not panel.fila_descarga.isHidden(), "se tiene que poder reintentar"
