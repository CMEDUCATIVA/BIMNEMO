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
    from lightrag.api.bimnemo.nativo.consumo import (
        COSTE,
        TAREA,
        TOKENS,
        TarjetaConsumo,
    )

    tarjeta = TarjetaConsumo(_Motor(USO))
    assert tarjeta.tabla.rowCount() == 2
    assert tarjeta.tabla.item(0, TOKENS).text() == "252.000 / 168.000"
    assert tarjeta.tabla.item(0, COSTE).text() == "$0,1386"
    assert tarjeta.tabla.item(1, TAREA).text() == "Embeddings"
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


def test_avisa_si_el_motor_no_usa_lo_guardado(aplicacion):
    """El caso real: se guardó flash, no se reinició, y se indexó con pro."""
    from lightrag.api.bimnemo.nativo.consumo import TarjetaConsumo

    datos = dict(
        USO,
        restart_required=True,
        saved_model="deepseek-flash",
        running_model="deepseek-v4-pro",
    )
    tarjeta = TarjetaConsumo(_Motor(datos))
    assert not tarjeta.pendiente.isHidden()
    assert "deepseek-v4-pro" in tarjeta.pendiente.text()

    tarjeta.pintar(dict(datos, restart_required=False))  # misma revisión
    assert tarjeta.pendiente.isHidden()


def test_guardar_reinicia_el_motor_aunque_no_cambie_nada_si_habia_algo_pendiente(
    aplicacion, monkeypatch
):
    from lightrag.api.bimnemo.nativo.pantalla_configuracion import PantallaConfiguracion

    pantalla = PantallaConfiguracion(_Motor({}))
    reinicios = []
    monkeypatch.setattr(pantalla, "_reiniciar", lambda: reinicios.append(1))

    pantalla._pendiente = True
    pantalla._guardado({"restart_required": False})
    assert reinicios == [1]

    pantalla._pendiente = False
    pantalla._guardado({"restart_required": False})
    assert reinicios == [1]


def test_si_esta_indexando_dice_que_lo_guardado_no_se_usa(aplicacion):
    from lightrag.api.bimnemo.nativo.pantalla_configuracion import PantallaConfiguracion

    pantalla = PantallaConfiguracion(_Motor({}))
    pantalla._tras_guardar = True
    pantalla._reiniciado(False, "409 ocupado")
    assert "NO se usa" in pantalla.estado.text()


def test_la_tabla_dice_de_que_archivo_es_cada_gasto(aplicacion):
    from lightrag.api.bimnemo.nativo.consumo import ARCHIVO, TarjetaConsumo

    filas = [
        {
            "fecha": "2026-09-22",
            "tipo": "llm",
            "tarea": "Indexar",
            "archivo": "ley.pdf",
            "modelo": "deepseek-flash",
            "llamadas": 1,
            "entrada": 1,
            "salida": 1,
            "coste": 0.1,
            "sin_precio": False,
        },
        {
            "fecha": "2026-09-22",
            "tipo": "llm",
            "tarea": "Responder",
            "archivo": "",
            "modelo": "deepseek-flash",
            "llamadas": 1,
            "entrada": 1,
            "salida": 1,
            "coste": 0.1,
            "sin_precio": False,
        },
        {
            "fecha": "2026-09-21",
            "tipo": "llm",
            "tarea": "Indexar",
            "modelo": "deepseek-v4-pro",
            "llamadas": 1,
            "entrada": 1,
            "salida": 1,
            "coste": 0.1,
            "sin_precio": False,
        },
    ]
    tarjeta = TarjetaConsumo(_Motor(dict(USO, rows=filas, revision=99)))
    assert tarjeta.tabla.item(0, ARCHIVO).text() == "ley.pdf"
    assert tarjeta.tabla.item(1, ARCHIVO).text() == "Preguntas del chat"
    assert tarjeta.tabla.item(2, ARCHIVO).text() == "—"


def test_la_tabla_dice_el_razonamiento_y_cuanto_se_penso(aplicacion):
    from lightrag.api.bimnemo.nativo.consumo import RAZONAMIENTO, TarjetaConsumo

    base = {
        "fecha": "2026-09-22",
        "tipo": "llm",
        "tarea": "Indexar",
        "archivo": "ley.pdf",
        "modelo": "deepseek-flash",
        "llamadas": 1,
        "entrada": 1,
        "coste": 0.1,
        "sin_precio": False,
    }
    filas = [
        dict(base, nivel="Lo que decida el modelo", salida=1000, razonando=680),
        dict(base, nivel="Apagado", salida=1000, razonando=0),
        dict(base, tipo="embedding", tarea="Embeddings", salida=0),
        dict(base, salida=10),  # contado antes de guardar el nivel
    ]
    tarjeta = TarjetaConsumo(_Motor(dict(USO, rows=filas, revision=123)))
    celda = lambda i: tarjeta.tabla.item(i, RAZONAMIENTO).text()  # noqa: E731
    assert celda(0) == "Por defecto · 68 %"
    assert celda(1) == "Apagado"
    assert celda(2) == "—"
    assert celda(3) == "—"


# -- fecha con hora, tiempo y borrar ------------------------------------------


def test_la_fecha_dice_de_que_hora_a_que_hora(aplicacion):
    from datetime import datetime, timezone

    from lightrag.api.bimnemo.nativo.consumo import fecha_de

    ini = datetime(2026, 9, 22, 13, 44, tzinfo=timezone.utc)
    fin = datetime(2026, 9, 22, 14, 12, tzinfo=timezone.utc)
    texto = fecha_de({"inicio": ini.isoformat(), "fin": fin.isoformat()})
    local = lambda d: d.astimezone().strftime("%H:%M")  # noqa: E731
    assert texto.endswith(f"{local(ini)}–{local(fin)}")
    # Lo contado antes de medir horas: solo el día.
    assert fecha_de({"fecha": "2026-09-21"}) == "21/09/2026"


def test_el_tiempo_de_un_archivo_es_de_principio_a_fin_y_el_del_chat_la_suma():
    from lightrag.api.bimnemo.nativo.consumo import duracion, tiempo_de

    archivo = {
        "archivo": "ley.pdf",
        "inicio": "2026-09-22T13:00:00+00:00",
        "fin": "2026-09-22T13:12:30+00:00",
        "segundos": 2000.0,
    }
    assert tiempo_de(archivo)[0] == "12 min 30 s"  # no los 2000 s sumados
    chat = {"archivo": "", "tarea": "Responder", "segundos": 45.4}
    assert tiempo_de(chat)[0] == "45 s"
    assert tiempo_de({"tarea": "Indexar"})[0] == "—"
    assert duracion(3900) == "1 h 05 min"


class _MotorBorra(_Motor):
    def __init__(self, respuesta):
        super().__init__(respuesta)
        self.borrados = []

    def borrar(self, ruta, cuerpo=None, bien=None, mal=None):
        self.borrados.append(ruta)
        if bien:
            bien({"status": "deleted"})


def _con_id():
    fila = dict(
        USO["rows"][0], id="2026-09-22|llm|Indexar|deepseek-flash|ley.pdf|Apagado"
    )
    return dict(USO, rows=[fila], revision=500)


def test_cada_fila_tiene_su_papelera_y_pregunta_antes(aplicacion):
    from PySide6.QtWidgets import QPushButton

    from lightrag.api.bimnemo.nativo.consumo import ACCIONES, TarjetaConsumo

    motor = _MotorBorra(_con_id())
    tarjeta = TarjetaConsumo(motor)
    boton = tarjeta.tabla.cellWidget(0, ACCIONES).findChildren(QPushButton)[0]

    tarjeta.confirmar = lambda *_: False
    boton.click()
    assert motor.borrados == []

    tarjeta.confirmar = lambda *_: True
    boton.click()
    assert motor.borrados and motor.borrados[0].startswith("/bimnemo/usage?id=")
    assert "%7C" in motor.borrados[0]  # la clave va entera y escapada


# -- la tabla es de la memoria abierta -----------------------------------------


def test_pide_el_gasto_de_la_memoria_abierta(aplicacion):
    """El `nemo` lo pone el motor; la tarjeta solo dice si quiere una o todas."""
    from lightrag.api.bimnemo.nativo.consumo import TarjetaConsumo

    tarjeta = TarjetaConsumo(_Motor(USO))
    assert tarjeta.motor.pedidos[-1] == "/bimnemo/usage?days=30&scope=nemo"


def test_pulsar_todas_pide_la_cuenta_entera(aplicacion):
    from lightrag.api.bimnemo.nativo.consumo import TarjetaConsumo

    tarjeta = TarjetaConsumo(_Motor(USO))
    tarjeta._ver("all")
    assert tarjeta.motor.pedidos[-1] == "/bimnemo/usage?days=30&scope=all"


def test_cambiar_de_memoria_repinta_aunque_la_revision_no_cambie(aplicacion):
    """La revisión es del registro entero: al cambiar de NEMO no se mueve."""
    from lightrag.api.bimnemo.nativo.consumo import TarjetaConsumo

    de_una = dict(USO, nemo="obra-sur", nemo_name="Obra Sur", scope="nemo")
    tarjeta = TarjetaConsumo(_Motor(de_una))
    tarjeta.pintar(de_una)
    assert tarjeta.tabla.rowCount() == 2

    # Misma revisión, otra memoria y sin gasto: la tabla tiene que vaciarse.
    otra = dict(
        USO, rows=[], nemo="", nemo_name="General", scope="nemo", other_rows=2
    )
    tarjeta.pintar(otra)
    assert tarjeta.tabla.rowCount() == 0
    assert "General" in tarjeta.pista.text()


def test_dice_cuanto_gasto_queda_fuera_del_filtro(aplicacion):
    """Si no, la tabla parece incompleta sin que nada explique por qué."""
    from lightrag.api.bimnemo.nativo.consumo import TarjetaConsumo

    datos = dict(USO, nemo_name="Obra Sur", scope="nemo", other_rows=3, revision=11)
    tarjeta = TarjetaConsumo(_Motor(datos))
    assert "Obra Sur" in tarjeta.pista.text()
    assert "3 filas más" in tarjeta.pista.text() and "Todas" in tarjeta.pista.text()


def test_sin_gasto_aqui_pero_si_en_otras_lo_dice(aplicacion):
    from lightrag.api.bimnemo.nativo.consumo import TarjetaConsumo

    tarjeta = TarjetaConsumo(
        _Motor({"rows": [], "totals": {}, "revision": 0, "other_rows": 4})
    )
    assert "otras" in tarjeta.vacio.text() and "Todas" in tarjeta.vacio.text()


def test_mirando_todas_cada_fila_dice_de_que_memoria_es(aplicacion):
    from lightrag.api.bimnemo.nativo.consumo import ARCHIVO, TarjetaConsumo, memoria_de

    filas = [
        dict(USO["rows"][0], archivo="ley.pdf", nemo="obra-sur", nemo_name="Obra Sur"),
        dict(USO["rows"][1], archivo="bases.docx", nemo=None),
    ]
    tarjeta = TarjetaConsumo(_Motor(dict(USO, rows=filas, scope="all", revision=31)))

    assert "Obra Sur" in tarjeta.tabla.item(0, ARCHIVO).toolTip()
    assert "antes de medirlas" in memoria_de(filas[1])
