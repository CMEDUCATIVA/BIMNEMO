"""El cuadro de la primera vez: cuándo sale, qué pide y en qué orden guarda."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.offline

DE_FABRICA = {"nemos": [{"id": "", "name": "General", "protected": True}], "default": ""}
VACIA = {"storage": {"total_files": 0}}
CON_ARCHIVOS = {"storage": {"total_files": 3}}

#: Un proveedor que no pide clave y otro que sí, como en el catálogo real.
CATALOGO = {
    "llm": [
        {"key": "ollama", "label": "Ollama", "binding": "ollama", "needs_key": False,
         "host": "http://localhost:11434", "models": ["qwen2.5:7b"]},
        {"key": "openai", "label": "OpenAI", "binding": "openai", "needs_key": True,
         "host": "https://api.openai.com/v1", "models": ["gpt-4o-mini"]},
    ],
    "embedding": [
        {"key": "ollama", "label": "Ollama", "binding": "ollama", "needs_key": False,
         "host": "http://localhost:11434", "models": ["bge-m3"]},
    ],
}
AJUSTES = {
    "llm": {"provider": "ollama", "model": "qwen2.5:7b", "api_key_set": False},
    "embedding": {"provider": "ollama", "model": "bge-m3", "api_key_set": False},
}


def _abrir(ventana, nemos=DE_FABRICA, stats=VACIA):
    ventana.motor.respuestas.update(
        {
            "/bimnemo/nemos": nemos,
            "/bimnemo/stats": stats,
            "/bimnemo/providers": CATALOGO,
            "/bimnemo/settings": AJUSTES,
            # El renombrado de la de fábrica, que se indica por parámetro.
            "/bimnemo/nemos?nemo=": {"id": "", "name": "Obra Norte"},
        }
    )
    ventana.bienvenida.comprobar()
    return ventana.bienvenida


def _espiar_envios(ventana) -> list[tuple[str, Any]]:
    """Lo que la ventana manda al motor, con su cuerpo."""
    envios: list[tuple[str, Any]] = []
    motor = ventana.motor
    for verbo in ("post", "parchear"):
        original = getattr(motor, verbo)

        def espia(ruta, cuerpo=None, bien=None, mal=None, _o=original, _v=verbo):
            envios.append((f"{_v} {ruta}", cuerpo))
            _o(ruta, cuerpo, bien, mal)

        setattr(motor, verbo, espia)
    return envios


# -- cuándo sale ------------------------------------------------------------


def test_solo_cuenta_como_nueva_la_de_fabrica_vacia():
    from lightrag.api.bimnemo.nativo.bienvenida import es_nueva

    general = [{"id": "", "name": "General"}]
    assert es_nueva(general, 0)
    assert not es_nueva(general, 1), "con documentos no hay nada que estrenar"
    assert not es_nueva([{"id": "", "name": "Obra Norte"}], 0), "ya tiene nombre"
    assert not es_nueva(general + [{"id": "obra", "name": "Obra"}], 0)


def test_sale_en_una_instalacion_nueva(ventana):
    cuadro = _abrir(ventana)

    assert not cuadro.isHidden()
    assert not ventana.centralWidget().isEnabled(), "lo de detrás se podía tocar"
    assert set(cuadro.secciones) == {"llm", "embedding"}


@pytest.mark.parametrize(
    "nemos, stats",
    [
        (DE_FABRICA, CON_ARCHIVOS),
        ({"nemos": [{"id": "", "name": "Obra Norte"}], "default": ""}, VACIA),
    ],
)
def test_no_sale_si_ya_se_ha_usado(ventana, nemos, stats):
    assert _abrir(ventana, nemos, stats).isHidden()


def test_la_ventana_de_detras_se_ve_desenfocada(aplicacion):
    from PySide6.QtGui import QColor, QPixmap

    from lightrag.api.bimnemo.nativo.bienvenida import difuminar

    foto = QPixmap(200, 120)
    foto.fill(QColor("#000000"))
    # Una raya blanca de un píxel: desenfocada deja de ser de un píxel.
    from PySide6.QtGui import QPainter

    pintor = QPainter(foto)
    pintor.fillRect(100, 0, 1, 120, QColor("#ffffff"))
    pintor.end()

    borrosa = difuminar(foto).toImage()
    assert borrosa.width() == 200 and borrosa.height() == 120
    vecino = borrosa.pixelColor(103, 60)
    assert vecino.red() > 0, "no se ha desenfocado nada"


# -- qué pide ---------------------------------------------------------------


def test_sin_nombre_no_manda_nada(ventana):
    cuadro = _abrir(ventana)
    envios = _espiar_envios(ventana)

    cuadro.nombre.setText("   ")
    cuadro._guardar()

    assert envios == []
    assert "nombre" in cuadro.aviso.text()


def test_pide_la_clave_si_el_proveedor_la_necesita(ventana):
    cuadro = _abrir(ventana)
    envios = _espiar_envios(ventana)
    llm = cuadro.secciones["llm"]
    llm.proveedor.setCurrentIndex(llm.proveedor.findData("openai"))

    cuadro.nombre.setText("Obra Norte")
    cuadro._guardar()

    assert envios == []
    assert "clave" in cuadro.aviso.text()


# -- cómo guarda ------------------------------------------------------------


def test_nombra_la_memoria_guarda_el_modelo_y_reinicia(ventana):
    cuadro = _abrir(ventana)
    envios = _espiar_envios(ventana)

    cuadro.nombre.setText("Obra Norte")
    cuadro._guardar()

    rutas = [ruta for ruta, _cuerpo in envios]
    # Primero el nombre —a la de fábrica, no una memoria nueva al lado— y
    # después el modelo.
    assert rutas[:2] == ["parchear /bimnemo/nemos?nemo=", "post /bimnemo/settings"]
    assert envios[0][1] == {"name": "Obra Norte"}
    assert set(envios[1][1]) == {"llm", "embedding"}
    assert envios[1][1]["llm"]["model"] == "qwen2.5:7b"
    # Y el reinicio, que es lo que hace que el motor lo use.
    assert "/bimnemo/app-build" in ventana.motor.pedidos
    assert not cuadro.barra.isHidden()


def test_ahora_no_lo_cierra_y_devuelve_la_ventana(ventana):
    cuadro = _abrir(ventana)

    cuadro.boton_luego.click()

    assert cuadro.isHidden()
    assert ventana.centralWidget().isEnabled()
