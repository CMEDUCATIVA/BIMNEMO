"""Auditoría de la pantalla: la barra de razonamiento, proveedor a proveedor.

La otra mitad de `tests/bimnemo/test_razonamiento_matriz.py`. Aquella
comprueba lo que se escribe; esta comprueba **lo que se ve y lo que se manda
al guardar**, moviendo los controles de verdad sobre el catálogo real.

Es lo que contesta a «ten cuidado con no romper los otros: el usuario puede
cambiar a otro modelo y debe funcionar para todos». Se recorre el catálogo
entero, en sus dos accesos —clave y suscripción—, y se hacen los saltos
entre proveedores que de verdad ocurren.

Aquí se vio el fallo que la motivó: en «Por suscripción» la pantalla miraba
los niveles del proveedor **por clave**, así que Claude por suscripción se
quedaba sin barra teniendo `--effort`.
"""

from __future__ import annotations

import pytest

from lightrag.api.bimnemo import razonamiento
from lightrag.api.bimnemo.providers import catalog_payload

pytestmark = pytest.mark.offline


@pytest.fixture(scope="module")
def catalogo() -> list[dict]:
    """El catálogo de verdad, el mismo que sirve el motor a la pantalla."""
    return list(catalog_payload()["llm"])


def _seccion(catalogo, proveedor: str, modelo: str, modo: str = "api"):
    from lightrag.api.bimnemo.nativo.pantalla_configuracion import Seccion

    seccion = Seccion("llm", "Modelo de lenguaje", "")
    seccion.poner_catalogo(catalogo)
    seccion.poner_valores({"provider": proveedor, "model": modelo, "mode": modo})
    return seccion


def _elegibles(catalogo) -> list[tuple[str, str, str]]:
    """Cada (proveedor, modelo, acceso) que se puede elegir en la pantalla.

    La suscripción no es otra entrada del catálogo: va **dentro** de su
    proveedor, y en la pantalla se llega a ella por el selector «Acceso».
    """
    salida: list[tuple[str, str, str]] = []
    for p in catalogo:
        for m in p.get("models") or []:
            salida.append((p["key"], m, "api"))
        for m in (p.get("subscription") or {}).get("models") or []:
            salida.append((p["key"], m, "suscripcion"))
    return salida


def _clave_niveles(catalogo, proveedor: str, modo: str) -> str:
    """El nombre con el que `razonamiento` conoce esa combinación."""
    p = next(x for x in catalogo if x["key"] == proveedor)
    if modo == "suscripcion" and p.get("subscription"):
        return p["subscription"]["key"]
    return proveedor


def _visible(seccion) -> bool:
    """Las barras existen siempre; lo que cambia es si se ven."""
    control = seccion.razonamiento
    return bool(control) and any(not b.isHidden() for b in control.barras.values())


# --- el catálogo entero -----------------------------------------------------


def test_los_dos_accesos_a_claude_no_dicen_lo_mismo(catalogo):
    """No es una incoherencia: son dos caminos al mismo modelo."""
    anthropic = next(p for p in catalogo if p["key"] == "anthropic")
    assert not anthropic["reasoning"], "por clave, su capa OpenAI lo ignora"
    assert anthropic["subscription"]["reasoning"], "por suscripción, su CLI sí"

    con_barra = [p["key"] for p in catalogo if p.get("reasoning")]
    assert "deepseek" in con_barra and "openai" in con_barra, "los de antes, intactos"


def test_todos_los_modelos_se_pueden_elegir_sin_romper_la_pantalla(
    aplicacion, catalogo
):
    """Recorre el catálogo entero eligiendo cada modelo, uno tras otro.

    No es una prueba de humo: es justo el camino por el que se rompería algo
    al añadir un proveedor —la pantalla decide si dibuja la barra y con qué
    niveles cada vez que cambia el modelo o el acceso.
    """
    from lightrag.api.bimnemo.nativo.pantalla_configuracion import Seccion

    seccion = Seccion("llm", "Modelo de lenguaje", "")
    seccion.poner_catalogo(catalogo)
    for proveedor, modelo, modo in _elegibles(catalogo):
        seccion.poner_valores({"provider": proveedor, "model": modelo, "mode": modo})
        peticion = seccion.a_peticion()
        assert peticion["provider"] == proveedor
        assert peticion["model"] == modelo
        # Sin tocar nada, lo que se guardaría es «lo que decida el modelo».
        for elegido in (peticion.get("reasoning") or {}).values():
            assert elegido == razonamiento.DEFECTO


def test_la_barra_sale_exactamente_donde_hay_niveles(aplicacion, catalogo):
    """Ni una barra que no controla nada, ni un modelo sin ella pudiendo."""
    for proveedor, modelo, modo in _elegibles(catalogo):
        seccion = _seccion(catalogo, proveedor, modelo, modo)
        clave = _clave_niveles(catalogo, proveedor, modo)
        hay = razonamiento.esquema(clave, modelo) is not None
        assert _visible(seccion) == hay, f"{clave}/{modelo} ({modo})"


# --- cambiar de proveedor en la pantalla ------------------------------------

SALTOS = [
    ("anthropic", "claude-opus-5", "suscripcion", "openai", "gpt-5.6-luna", "api"),
    ("openai", "gpt-5.6-luna", "api", "anthropic", "claude-opus-5", "suscripcion"),
    ("deepseek", "deepseek-v4-pro", "api", "anthropic", "claude-haiku-4-5", "suscripcion"),
    ("anthropic", "claude-opus-5", "suscripcion", "gemini", "gemini-2.5-flash", "api"),
    ("anthropic", "claude-opus-5", "suscripcion", "mistral", "mistral-small-2506", "api"),
    # El salto más fino: mismo proveedor y mismo modelo, cambiando solo el
    # acceso. Por clave no hay control; por suscripción sí.
    ("anthropic", "claude-opus-5", "suscripcion", "anthropic", "claude-opus-5", "api"),
]


@pytest.mark.parametrize("de_p,de_m,de_modo,a_p,a_m,a_modo", SALTOS)
def test_cambiar_de_modelo_no_arrastra_el_nivel_del_anterior(
    aplicacion, catalogo, de_p, de_m, de_modo, a_p, a_m, a_modo
):
    """Un nivel de otro proveedor no significa lo mismo, o no existe."""
    seccion = _seccion(catalogo, de_p, de_m, de_modo)

    barra = seccion.razonamiento.barras["indexar"]
    barra.deslizador.setValue(1)
    assert seccion.a_peticion()["reasoning"]["indexar"] != razonamiento.DEFECTO

    seccion.poner_valores({"provider": a_p, "model": a_m, "mode": a_modo})
    for elegido in (seccion.a_peticion().get("reasoning") or {}).values():
        assert elegido == razonamiento.DEFECTO, f"arrastrado de {de_p} a {a_p}"


# --- Claude por suscripción, en la pantalla ---------------------------------


def test_claude_por_suscripcion_ensena_sus_cinco_niveles(aplicacion, catalogo):
    seccion = _seccion(catalogo, "anthropic", "claude-opus-5", "suscripcion")

    assert _visible(seccion), "su CLI acepta --effort"
    barra = seccion.razonamiento.barras["indexar"]
    assert barra.deslizador.maximum() == 5, "defecto + low/medium/high/xhigh/max"
    barra.deslizador.setValue(1)
    assert barra.valor.text() == "Bajo"
    assert seccion.a_peticion()["reasoning"]["indexar"] == "low"


def test_claude_por_clave_no_ensena_barra(aplicacion, catalogo):
    """Su capa compatible con OpenAI la ignora: una barra ahí mentiría."""
    seccion = _seccion(catalogo, "anthropic", "claude-opus-5", "api")

    assert not _visible(seccion)
    assert "no razona" in seccion.razonamiento.nota.text()


def test_la_pista_tambien_cambia_con_el_acceso(aplicacion, catalogo):
    """Pedirle una clave a quien no la necesita es el error de al lado."""
    suscripcion = _seccion(catalogo, "anthropic", "claude-opus-5", "suscripcion")
    por_clave = _seccion(catalogo, "anthropic", "claude-opus-5", "api")

    assert "suscripción de Claude" in suscripcion.pista.text()
    assert "No necesita clave" in suscripcion.pista.text()
    assert "console.anthropic.com" not in suscripcion.pista.text()

    assert "console.anthropic.com" in por_clave.pista.text()
    assert "capa compatible con OpenAI" in por_clave.pista.text()


def test_cambiar_el_acceso_a_mano_repinta_pista_y_barras(aplicacion, catalogo):
    """Sin esto, el selector cambia y lo de debajo se queda como estaba."""
    seccion = _seccion(catalogo, "anthropic", "claude-opus-5", "api")
    assert not _visible(seccion)

    seccion.modo.setCurrentIndex(seccion.modo.findData("suscripcion"))
    seccion._cambio_modo()

    assert _visible(seccion), "la barra aparece al pasar a suscripción"
    assert "No necesita clave" in seccion.pista.text()
