"""La pantalla «API»: la tabla de endpoints y el interruptor de la clave.

Se prueban las dos cosas que se hacían mal y que no se ven mirando la
pantalla un segundo: que las cuatro columnas están **alineadas entre filas**
—si no, no es una tabla, son frases sueltas— y que el interruptor **no
protege nada por sí solo**, porque protegerla de verdad reinicia el motor y
eso no puede dispararse al rozar una palanca.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

MANIFIESTO_ABIERTO = {"authentication": "Sin autenticación en esta instancia"}
MANIFIESTO_PROTEGIDO = {"authentication": "Cabecera X-API-Key"}


def api_de(ventana):
    """La pantalla de API, que es la última del carril."""
    from lightrag.api.bimnemo.nativo.pantalla_api import PantallaApi

    for indice in range(ventana.contenido.count()):
        pantalla = ventana.contenido.widget(indice)
        if isinstance(pantalla, PantallaApi):
            return pantalla
    raise AssertionError("no hay pantalla de API")


# -- la tabla ---------------------------------------------------------------


def test_las_cuatro_columnas_se_alinean_en_todas_las_filas(ventana):
    """Una tabla es esto: la misma ruta empieza donde empieza la de arriba.

    Con una ficha por endpoint cada fila repartía su ancho a su manera y la
    vista no se podía recorrer por columnas.
    """
    from PySide6.QtWidgets import QLabel

    from lightrag.api.bimnemo.nativo import api_piezas

    api = api_de(ventana)
    api.resize(1100, 900)
    api.show()

    tablas = api.findChildren(api_piezas.Tabla)
    assert tablas, "la pantalla no tiene ninguna tabla de endpoints"

    rejilla = tablas[0].layout()
    columnas: dict[int, set[int]] = {}
    for indice in range(rejilla.count()):
        widget = rejilla.itemAt(indice).widget()
        _fila, columna, *_ = rejilla.getItemPosition(indice)
        if isinstance(widget, QLabel) and columna < 3:
            columnas.setdefault(columna, set()).add(widget.x())

    for columna, equis in columnas.items():
        assert len(equis) == 1, f"la columna {columna} empieza en {sorted(equis)}"


def test_el_cuerpo_json_no_se_pinta_pero_se_copia(ventana):
    """Debajo de cada ruta estorbaba; sin él no se puede llamar. Va al botón."""
    from PySide6.QtWidgets import QLabel, QPushButton

    from lightrag.api.bimnemo.nativo import api_piezas

    tabla = api_de(ventana).findChildren(api_piezas.Tabla)[0]

    sueltos = [w for w in tabla.findChildren(QLabel) if w.text().startswith("{")]
    assert not sueltos, "hay cuerpos JSON pintados en la tabla"

    botones = [
        w for w in tabla.findChildren(QPushButton) if w.objectName() == "copiar-linea"
    ]
    assert botones
    con_cuerpo = [b for b in botones if '"query"' in b.toolTip()]
    assert con_cuerpo, "ningún botón ofrece el cuerpo de la llamada"


def test_las_rutas_siguen_a_la_memoria(ventana):
    """Copiar `/bimnemo/…` con «Obra Sur» abierta lee **otra** memoria."""
    from PySide6.QtWidgets import QLabel

    from lightrag.api.bimnemo.nativo import api_piezas

    api = api_de(ventana)
    ventana.motor.usar_memoria("Obra_Sur")
    api.cambiar_memoria("Obra_Sur")

    rutas = [
        w.text()
        for tabla in api.findChildren(api_piezas.Tabla)
        for w in tabla.findChildren(QLabel)
        if w.objectName() == "ruta"
    ]
    assert any(r.startswith("/nemo/Obra_Sur/") for r in rutas)
    assert "/nemo/{nemo}/memory/search" not in rutas
    assert "{nemo}" not in api._instruccion


# -- el interruptor ---------------------------------------------------------


def test_el_interruptor_solo_descubre_el_boton(ventana):
    """Encenderlo no escribe nada: protegerla de verdad reinicia el motor."""
    acceso = api_de(ventana).acceso
    antes = list(ventana.motor.pedidos)

    acceso.interruptor.setChecked(True)
    acceso._pensarlo()

    # `isVisible` mira además a los padres, y aquí la ventana no está en
    # pantalla: lo que se comprueba es la orden de mostrarlo.
    assert not acceso.boton.isHidden()
    assert acceso.boton.text() == "Generar clave y reiniciar"
    assert ventana.motor.pedidos == antes, "ha llamado al motor sin confirmar"
    assert ventana.motor.clave == ""


def test_devolverlo_a_su_sitio_esconde_el_boton(ventana):
    acceso = api_de(ventana).acceso

    acceso.interruptor.setChecked(True)
    acceso._pensarlo()
    acceso.interruptor.setChecked(False)
    acceso._pensarlo()

    assert acceso.boton.isHidden()


def test_al_proteger_la_ventana_se_queda_la_clave_antes_de_escribirla(ventana):
    """El orden importa: si el motor vuelve pidiéndola y ésta no la tiene,
    la aplicación se queda fuera de su propia memoria."""
    acceso = api_de(ventana).acceso

    acceso.interruptor.setChecked(True)
    acceso._pensarlo()
    acceso._aplicar()

    assert len(ventana.motor.clave) == 32
    assert acceso.campo.text() == ventana.motor.clave
    assert "/bimnemo/access" in ventana.motor.pedidos


def test_dice_lo_que_dice_el_motor_en_marcha(ventana):
    """No se mira el `.env`: ahí está lo que pedirá el **próximo** arranque."""
    acceso = api_de(ventana).acceso

    ventana.motor.respuestas["/bimnemo/memory/manifest"] = MANIFIESTO_PROTEGIDO
    acceso.refrescar()
    assert acceso.interruptor.isChecked()
    assert acceso.nota.text() == "Protegida"

    ventana.motor.respuestas["/bimnemo/memory/manifest"] = MANIFIESTO_ABIERTO
    acceso.refrescar()
    assert not acceso.interruptor.isChecked()
    assert acceso.nota.text() == "Abierta"
