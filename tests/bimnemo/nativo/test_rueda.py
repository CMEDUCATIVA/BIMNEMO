"""La rueda del ratón desplaza la página y no cambia los selectores."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.offline


def _pagina_con_selector():
    from PySide6.QtWidgets import QComboBox, QScrollArea, QVBoxLayout, QWidget

    pagina = QScrollArea()
    pagina.setWidgetResizable(True)
    dentro = QWidget()
    columna = QVBoxLayout(dentro)
    selector = QComboBox()
    selector.addItems(["OpenAI", "Gemini", "Ollama"])
    columna.addWidget(selector)
    for _ in range(40):  # contenido de sobra para que haya que desplazar
        relleno = QWidget()
        relleno.setFixedHeight(60)
        columna.addWidget(relleno)
    pagina.setWidget(dentro)
    pagina.resize(400, 300)
    pagina.show()
    return pagina, selector


def _girar(widget, hacia_abajo=True):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    paso = -120 if hacia_abajo else 120
    evento = QWheelEvent(
        QPointF(10, 10), QPointF(widget.mapToGlobal(QPoint(10, 10))), QPoint(0, 0),
        QPoint(0, paso), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False,
    )
    QApplication.sendEvent(widget, evento)


def test_girar_la_rueda_sobre_un_selector_no_lo_cambia_y_baja_la_pagina(aplicacion):
    from lightrag.api.bimnemo.nativo import rueda

    rueda.instalar(aplicacion)
    pagina, selector = _pagina_con_selector()
    antes = pagina.verticalScrollBar().value()

    for _ in range(3):
        _girar(selector)

    assert selector.currentText() == "OpenAI", "la rueda cambió el selector"
    assert pagina.verticalScrollBar().value() > antes, "la página no bajó"


def test_la_ventana_lo_instala_sola(ventana):
    from lightrag.api.bimnemo.nativo import rueda

    assert rueda._instalado is not None
