"""El armazón: navegación, contadores, barra superior y tema."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline

# --- Pantallas y navegación -------------------------------------------------


def test_las_seis_pantallas_estan_montadas(ventana):
    """Ningún `Hueco`: si queda uno, alguien rompió el registro."""
    from lightrag.api.bimnemo.nativo.ventana import PANTALLAS

    montadas = [
        type(ventana.contenido.widget(i)).__name__ for i in range(len(PANTALLAS))
    ]
    assert montadas == [
        "PantallaPanel",
        "PantallaArchivos",
        "PantallaChat",
        "PantallaConfiguracion",
        "PantallaMotor",
        "PantallaApi",
    ]


def test_abre_por_el_panel(ventana):
    """Registrar pantallas mueve la que está delante: abría en Motor."""
    assert ventana.contenido.currentIndex() == 0
    assert ventana._botones[0].isChecked() is True


# --- Contador del carril ----------------------------------------------------


def test_archivos_empieza_con_una_raya_y_no_con_un_cero(ventana):
    """Un cero mientras carga se lee como «esta memoria está vacía»."""
    assert ventana._cuentas["Archivos"].text() == "—"


def test_el_carril_cuenta_los_archivos_de_la_memoria(ventana):
    archivos = ventana.contenido.widget(1)
    archivos._recibir({"files": [{"name": f"{i}.pdf"} for i in range(1234)]})
    assert ventana._cuentas["Archivos"].text() == "1.234"


def test_las_demas_entradas_no_llevan_contador(ventana):
    """Un número junto a «Motor» no significaría nada."""
    con_numero = [n for n, e in ventana._cuentas.items() if e.text()]
    assert con_numero == ["Archivos"]


def test_el_contador_no_se_come_el_clic(ventana):
    """La etiqueta va DENTRO del botón, y el ratón la atraviesa.

    Sin `WA_TransparentForMouseEvents`, la etiqueta es quien está debajo del
    puntero en esa esquina y el botón deja de encenderse y de responder ahí.
    """
    from PySide6.QtCore import QPoint

    boton = ventana._botones[1]
    boton.resize(200, 34)
    assert boton.childAt(QPoint(boton.width() - 20, boton.height() // 2)) is None


# --- Barra superior ---------------------------------------------------------


def test_el_selector_muestra_solo_el_nombre(ventana):
    """Sin el `·` detrás: se leía como parte del nombre de la memoria."""
    from PySide6.QtCore import Qt

    barra = ventana.barra
    rotulos = [barra.selector.itemText(i) for i in range(barra.selector.count())]
    assert rotulos == ["General", "Obra Sur"]
    assert barra.selector.currentText() == "General"
    # Cuál se abre al arrancar lo sigue diciendo el rótulo emergente.
    assert "por defecto" in barra.selector.itemData(0, Qt.ToolTipRole)


def test_cambiar_de_memoria_en_el_selector_cambia_la_del_motor(ventana):
    barra = ventana.barra
    indice = barra.selector.findData("obra-sur")
    barra._elegida(indice)

    assert ventana.memorias.actual == "obra-sur"
    assert ventana.motor.memoria == "obra-sur"


def test_la_memoria_base_tambien_se_puede_borrar(ventana):
    """Quien la ve en la lista tiene que poder quitarla: el usuario la
    encuentra limpia o la deja limpia."""
    assert ventana.barra.boton_borrar.isEnabled() is True

    ventana.barra._elegida(ventana.barra.selector.findData("obra-sur"))
    assert ventana.barra.boton_borrar.isEnabled() is True


def test_sin_memorias_no_hay_nada_que_renombrar_ni_borrar(ventana):
    ventana.motor.respuestas["/bimnemo/nemos"] = {"nemos": [], "default": ""}
    ventana.memorias.cargar()

    barra = ventana.barra
    assert barra.selector.currentText() == "Sin memorias"
    assert not barra.selector.isEnabled()
    assert not barra.boton_renombrar.isEnabled()
    assert not barra.boton_borrar.isEnabled()


def test_cambiar_de_memoria_relee_las_pantallas(ventana):
    """Cambiar de memoria es cambiar de datos en todas: si no, mienten."""
    ventana.motor.pedidos.clear()
    ventana.barra._elegida(ventana.barra.selector.findData("obra-sur"))
    assert "/bimnemo/files" in ventana.motor.pedidos


def test_la_pantalla_de_archivos_dice_que_memoria_enseña(ventana):
    archivos = ventana.contenido.widget(1)
    archivos._recibir({"files": [], "total": 0})
    assert archivos.pista.text().startswith("General")


def test_la_memoria_y_sus_acciones_van_en_un_grupo(ventana):
    """Es un grupo, no cuatro controles que se quedaron juntos por azar."""
    grupo = ventana.barra.selector.parent()
    assert grupo.objectName() == "grupo-nemo"
    for boton in ("boton_nueva", "boton_renombrar", "boton_borrar"):
        assert getattr(ventana.barra, boton).parent() is grupo


def test_el_desplegable_lleva_su_flecha(ventana):
    """Qt no dibuja ninguna por su cuenta, y sin ella parece una caja de texto."""
    from lightrag.api.bimnemo.nativo import tema

    hoja = tema.hoja(tema.ACTUAL)
    assert "QComboBox::down-arrow" in hoja
    assert "chevron-down" in hoja


def test_la_memoria_va_centrada_en_la_barra(ventana):
    """En el centro de la barra, no a medio camino entre sus vecinos.

    Con un espaciador a cada lado el grupo se movería cada vez que cambiara
    el ancho de la marca o de las acciones — y el nombre de la memoria cambia
    de ancho al cambiar de memoria.
    """
    ventana.resize(1920, 900)
    ventana.show()
    ventana.barra.layout().activate()

    grupo = ventana.barra.selector.parent()
    centro = grupo.mapTo(ventana.barra, grupo.rect().center()).x()
    ventana.hide()

    assert abs(centro - ventana.barra.width() // 2) <= 2


def test_todo_lo_de_la_barra_esta_centrado(ventana):
    """Una fila de controles a distintas alturas se lee como descuadrada."""
    ventana.resize(1400, 880)
    ventana.show()
    ventana.barra.layout().activate()

    # En coordenadas de la barra: cada zona vive dentro de su propia celda,
    # así que su geometría es relativa a esa caja y no a la barra.
    barra = ventana.barra
    centros = {
        w.mapTo(barra, w.rect().center()).y()
        for w in (
            barra.marca,
            barra.selector.parent(),
            barra.estado_motor,
            barra.boton_refrescar,
            barra.boton_tema,
        )
    }
    ventana.hide()
    assert len(centros) == 1


# --- Las cifras del panel ---------------------------------------------------


def _panel_con_cifras(ventana):
    """El panel, contestando cifras distintas según la memoria abierta."""
    motor = ventana.motor

    def stats():
        filas = 4 if motor.memoria == "" else 1
        return {
            "storage": {
                "total_files": filas,
                "total_bytes": filas * 1000,
                "categories_in_use": filas,
                "categories_available": 8,
                "categories": [],
                "types": [],
            },
            "memory": {"total_documents": filas, "total_chunks": filas * 5},
        }

    motor.respuestas["/bimnemo/stats"] = stats
    panel = ventana.contenido.widget(0)
    panel.refrescar()
    return panel


def test_las_cuatro_cifras_son_de_la_memoria_abierta(ventana):
    """Las cuatro: antes tres sumaban todas las memorias y no se movían."""
    panel = _panel_con_cifras(ventana)
    assert [
        panel.cifras[c].valor.text()
        for c in ("archivos", "almacenado", "categorias", "memoria")
    ] == ["4", "3.9 KB", "4 / 8", "4"]

    ventana.barra._elegida(ventana.barra.selector.findData("obra-sur"))

    assert [
        panel.cifras[c].valor.text()
        for c in ("archivos", "almacenado", "categorias", "memoria")
    ] == ["1", "1000 B", "1 / 8", "1"]


def test_las_cifras_no_se_quedan_con_las_de_la_memoria_anterior(ventana):
    """Abrir una memoria dormida tarda segundos: mientras, no se miente.

    Dejar puestas las cifras de la anterior es enseñar datos de otra memoria
    como si fueran de esta.
    """
    panel = _panel_con_cifras(ventana)
    assert panel.cifras["memoria"].valor.text() == "4"

    # Lo que se ve en el hueco entre pedir y que conteste el motor.
    panel.otra_memoria()
    assert [c.valor.text() for c in panel.cifras.values()] == ["…"] * len(panel.cifras)


# --- El resumen del carril --------------------------------------------------


def _con_almacen(ventana):
    """Una ventana cuyo panel ya leyó lo que ocupa la memoria abierta."""

    def stats():
        uno = ventana.motor.memoria == ""
        return {
            "storage": {
                "total_files": 3 if uno else 1,
                "total_bytes": 1000 if uno else 400,
                "categories_in_use": 2 if uno else 1,
                "categories_available": 5,
                "categories": [
                    {
                        "key": "document",
                        "label": "Documento",
                        "icon": "file-text",
                        "color": "sky",
                        "files": 2 if uno else 0,
                        "size_bytes": 900 if uno else 0,
                    },
                    {
                        "key": "data",
                        "label": "Datos",
                        "icon": "database",
                        "color": "amber",
                        "files": 1,
                        "size_bytes": 100 if uno else 400,
                    },
                ],
                "types": [],
            },
            "memory": {"total_documents": 1, "total_chunks": 1},
        }

    ventana.motor.respuestas["/bimnemo/stats"] = stats
    ventana.contenido.widget(0).refrescar()
    return ventana.resumen


def _chips(resumen):
    from PySide6.QtWidgets import QPushButton

    return resumen.chips.findChildren(QPushButton)


def test_el_carril_resume_lo_que_ocupa_la_memoria_abierta(ventana):
    """El mismo dato del panel, en pequeño y siempre a la vista."""
    resumen = _con_almacen(ventana)

    assert resumen.tamano.text() == "1000 B"
    assert resumen.cuantos.text() == "3 archivos"
    assert [b.text() for b in _chips(resumen)] == ["Documento  2", "Datos  1"]


def test_el_resumen_del_carril_sigue_a_la_memoria(ventana):
    resumen = _con_almacen(ventana)
    ventana.barra._elegida(ventana.barra.selector.findData("obra-sur"))

    assert resumen.tamano.text() == "400 B"
    assert resumen.cuantos.text() == "1 archivo"
    # La categoría vacía desaparece del carril: ahí solo caben las que hay.
    assert [b.text() for b in _chips(resumen)] == ["Datos  1"]


def test_pulsar_una_categoria_del_carril_lleva_a_archivos(ventana):
    resumen = _con_almacen(ventana)
    _chips(resumen)[0].click()

    assert ventana.contenido.currentIndex() == 1
    assert ventana.contenido.widget(1).filtros.activa == "document"


def test_el_resumen_va_justo_debajo_de_la_navegacion(ventana):
    """Y no pegado al pie: las categorías crecen hacia abajo al llenarse.

    Con el resumen al fondo, cada chip nuevo tendría que empujar al resto
    hacia arriba; aquí el hueco sobrante queda por debajo.
    """
    from PySide6.QtWidgets import QApplication

    ventana.show()
    QApplication.processEvents()

    ultima = ventana._botones[-1]
    hueco = ventana.resumen.mapTo(ventana, ventana.resumen.rect().topLeft()).y()
    abajo_de_la_nav = ultima.mapTo(ventana, ultima.rect().bottomLeft()).y()
    version = ventana.etiqueta_version.mapTo(
        ventana, ventana.etiqueta_version.rect().topLeft()
    ).y()
    ventana.hide()

    # Empieza nada más acabar la navegación, no al final del carril.
    assert 0 < hueco - abajo_de_la_nav < 40
    assert hueco < version - 100


def test_con_el_carril_estrecho_el_resumen_se_esconde(ventana):
    """En sesenta píxeles no cabe ni la cifra: mejor nada que un muñón."""
    _con_almacen(ventana)
    ventana.show()

    ventana._encoger_carril(True)
    assert ventana.resumen.isVisible() is False

    ventana._encoger_carril(False)
    assert ventana.resumen.isVisible() is True
    ventana.hide()


# --- Estado del motor -------------------------------------------------------


def test_el_motor_sano_sale_en_verde(ventana):
    ventana.barra._motor_contesto({"status": "healthy"})
    assert "Motor activo" in ventana.barra.estado_motor.text()


def test_un_estado_raro_se_dice_tal_cual(ventana):
    ventana.barra._motor_contesto({"status": "degraded"})
    assert "degraded" in ventana.barra.estado_motor.text()


def test_sin_clave_lo_dice_en_vez_de_culpar_al_motor(ventana):
    """«No disponible» mandaría a reiniciar algo que está funcionando."""
    from lightrag.api.bimnemo.nativo.motor import PIDE_CLAVE

    ventana.barra._motor_fallo(PIDE_CLAVE)
    assert "Requiere clave" in ventana.barra.estado_motor.text()


def test_cualquier_peticion_sin_motor_lo_cuenta_arriba(ventana):
    """Seis pantallas avisando de lo mismo serían seis avisos por un problema."""
    ventana.motor.caido.emit("El motor no responde (cerrado).")
    assert "Motor no disponible" in ventana.barra.estado_motor.text()


# --- Tema -------------------------------------------------------------------


def test_alternar_el_tema_cambia_la_paleta_y_la_recuerda(ventana, tmp_path):
    from lightrag.api.bimnemo.nativo import tema

    assert ventana.paleta is tema.OSCURO
    ventana.alternar_tema()

    assert ventana.paleta is tema.CLARO
    assert tema.ACTUAL is tema.CLARO
    # Y al volver, se queda donde estaba.
    ventana.alternar_tema()
    assert ventana.paleta is tema.OSCURO


def test_el_boton_del_tema_enseña_adonde_va(ventana):
    """Con el tema oscuro puesto, el sol es la salida."""
    assert "claro" in ventana.barra.boton_tema.toolTip()
    ventana.alternar_tema()
    assert "oscuro" in ventana.barra.boton_tema.toolTip()
    ventana.alternar_tema()


def test_los_iconos_siguen_al_tema(ventana):
    """Un icono ya pintado no lo alcanza la hoja de estilo: hay que reteñirlo."""
    from lightrag.api.bimnemo.nativo import iconos

    boton = ventana._botones[0]
    antes = boton.icon().pixmap(15, 15).toImage()
    ventana.alternar_tema()
    despues = boton.icon().pixmap(15, 15).toImage()
    ventana.alternar_tema()

    assert boton.property("icono-nombre") == "panel"
    assert antes != despues
    assert iconos is not None
