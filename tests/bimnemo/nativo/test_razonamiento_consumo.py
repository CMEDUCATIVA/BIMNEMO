"""Las barras de razonamiento en «Modelo de lenguaje» y la tarjeta de consumo."""

from __future__ import annotations

from lightrag.api.bimnemo import razonamiento

CATALOGO = [
    {
        "key": "deepseek",
        "label": "DeepSeek",
        "binding": "openai",
        "host": "https://api.deepseek.com/v1",
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "reasoning": razonamiento.para_catalogo(
            "deepseek", ("deepseek-flash", "deepseek-v4-pro")
        ),
    },
    {
        "key": "mistral",
        "label": "Mistral",
        "binding": "openai",
        "host": "https://api.mistral.ai/v1",
        "models": ["mistral-small-2506"],
        "reasoning": {},
    },
]


def _seccion(valores):
    from lightrag.api.bimnemo.nativo.pantalla_configuracion import Seccion

    seccion = Seccion("llm", "Modelo de lenguaje", "")
    seccion.poner_catalogo(CATALOGO)
    seccion.poner_valores(valores)
    return seccion


def test_solo_el_modelo_de_lenguaje_tiene_barras(aplicacion):
    from lightrag.api.bimnemo.nativo.pantalla_configuracion import Seccion

    assert Seccion("embedding", "Embeddings", "").razonamiento is None
    assert _seccion({"provider": "deepseek", "model": "deepseek-flash"}).razonamiento


def test_enseña_lo_guardado_y_lo_manda_al_guardar(aplicacion):
    seccion = _seccion(
        {
            "provider": "deepseek",
            "model": "deepseek-flash",
            "reasoning": {"indexar": "off", "responder": "high"},
        }
    )
    barra = seccion.razonamiento.barras["indexar"]
    assert barra.valor.text() == "Apagado"
    assert seccion.a_peticion()["reasoning"] == {"indexar": "off", "responder": "high"}


def test_mover_la_barra_cambia_lo_que_se_guarda(aplicacion):
    seccion = _seccion({"provider": "deepseek", "model": "deepseek-flash"})
    seccion.razonamiento.barras["indexar"].deslizador.setValue(1)
    assert seccion.a_peticion()["reasoning"]["indexar"] == "off"


def test_un_modelo_sin_control_no_enseña_barras_y_lo_dice(aplicacion):
    seccion = _seccion({"provider": "mistral", "model": "mistral-small-2506"})
    control = seccion.razonamiento
    assert all(b.isHidden() for b in control.barras.values())
    assert "no razona" in control.nota.text()
    assert seccion.a_peticion()["reasoning"] == {"indexar": "", "responder": ""}


def test_cambiar_de_proveedor_vuelve_a_lo_que_decida_el_modelo(aplicacion):
    seccion = _seccion(
        {
            "provider": "deepseek",
            "model": "deepseek-flash",
            "reasoning": {"indexar": "off", "responder": ""},
        }
    )
    seccion.proveedor.setCurrentIndex(seccion.proveedor.findData("mistral"))
    assert seccion.a_peticion()["reasoning"]["indexar"] == ""


def test_un_ajuste_a_mano_se_conserva_si_no_se_toca(aplicacion):
    seccion = _seccion(
        {
            "provider": "deepseek",
            "model": "deepseek-flash",
            "reasoning": {"indexar": "manual", "responder": ""},
        }
    )
    assert seccion.a_peticion()["reasoning"]["indexar"] == "manual"
    assert "a mano" in seccion.razonamiento.barras["indexar"].valor.text()


# -- tarjeta de consumo -------------------------------------------------------


class _Motor:
    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.pedidos = []

    def get(self, ruta, bien=None, mal=None):
        self.pedidos.append(ruta)
        if bien:
            bien(self.respuesta)


USO = {
    "rows": [
        {
            "fecha": "2026-09-22",
            "tipo": "llm",
            "tarea": "Indexar",
            "modelo": "deepseek-flash",
            "llamadas": 42,
            "entrada": 252000,
            "salida": 168000,
            "coste": 0.1386,
            "sin_precio": False,
        },
        {
            "fecha": "2026-09-22",
            "tipo": "embedding",
            "tarea": "Embeddings",
            "modelo": "raro",
            "llamadas": 3,
            "entrada": 900,
            "salida": 0,
            "coste": 0.0,
            "sin_precio": True,
        },
    ],
    "totals": {
        "today": {"coste": 0.1386},
        "week": {"coste": 1.5},
        "month": {"coste": 4.25, "sin_precio": True},
    },
    "prices_checked": "2026-09-21",
    "revision": 7,
}


def test_la_tarjeta_pinta_filas_y_totales(aplicacion):
    from lightrag.api.bimnemo.nativo.consumo import COSTE, ENTRADA, TIPO, TarjetaConsumo

    tarjeta = TarjetaConsumo(_Motor(USO))
    assert tarjeta.tabla.rowCount() == 2
    assert tarjeta.tabla.item(0, ENTRADA).text() == "252.000"
    assert tarjeta.tabla.item(0, COSTE).text() == "$0,1386"
    assert tarjeta.tabla.item(1, TIPO).text() == "Embeddings"
    assert tarjeta.tabla.item(1, COSTE).text() == "sin precio"
    assert "$4,25 + ?" in tarjeta.totales.text()
    assert "2026-09-21" in tarjeta.pista.text()


def test_sin_gasto_lo_dice_en_vez_de_una_tabla_vacia(aplicacion):
    from lightrag.api.bimnemo.nativo.consumo import TarjetaConsumo

    tarjeta = TarjetaConsumo(_Motor({"rows": [], "totals": {}, "revision": 0}))
    assert tarjeta.tabla.isHidden() and not tarjeta.vacio.isHidden()


def test_si_nada_cambio_no_repinta(aplicacion):
    from lightrag.api.bimnemo.nativo.consumo import TarjetaConsumo

    tarjeta = TarjetaConsumo(_Motor(USO))
    tarjeta.tabla.setRowCount(0)
    tarjeta.pintar(USO)  # misma revisión
    assert tarjeta.tabla.rowCount() == 0


def test_formatos_en_castellano():
    from lightrag.api.bimnemo.nativo.consumo import dinero, miles

    assert miles(1234567) == "1.234.567"
    assert dinero(0.1386) == "$0,1386"
    assert dinero(1234.5) == "$1.234,50"
