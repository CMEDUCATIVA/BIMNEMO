"""Pantalla «API»: cómo conectar cualquier IA a esta memoria.

La lista de endpoints sale de `lightrag/api/bimnemo/manifiesto.py`, que es la
misma fuente que usa la interfaz web. **Escribirla aquí a mano sería tener dos
catálogos**, y el día que se añada un endpoint uno de los dos se quedaría
viejo sin que nadie se entere.

## El botón de copiar es la función, no un adorno

Nadie teclea a mano una dirección con su cuerpo JSON para pegársela a una IA.
Si copiar cuesta, la pantalla no sirve para lo que está: que el usuario se
lleve esto a su asistente y funcione a la primera.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.manifiesto import AMBITOS, ENDPOINTS, GRUPOS, MODOS
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Pantalla, Tarjeta

#: El color con el que se pinta cada verbo, para distinguirlos de un vistazo.
#: El rojo del borrado no es decorativo: avisa antes de leer la línea.
COLOR_VERBO = {
    "GET": "#0ea5e9",
    "POST": "#10b981",
    "PATCH": "#f59e0b",
    "DELETE": "#ef4444",
}


def _al_portapapeles(texto: str) -> None:
    QGuiApplication.clipboard().setText(texto)


class Endpoint(QWidget):
    """Una línea de la lista: verbo, ruta, para qué sirve y copiar."""

    def __init__(self, datos: dict[str, Any], base: str) -> None:
        super().__init__()
        self.setObjectName("fila")
        self.datos = datos
        self.base = base

        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 6, 0, 6)
        columna.setSpacing(3)

        arriba = QWidget()
        arriba.setObjectName("fila")
        caja = QHBoxLayout(arriba)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)

        verbo = QLabel(str(datos.get("method") or ""))
        verbo.setObjectName("verbo")
        verbo.setFixedWidth(66)
        verbo.setAlignment(Qt.AlignCenter)
        color = COLOR_VERBO.get(str(datos.get("method")), "#94a3b8")
        verbo.setStyleSheet(
            f"color: {color}; border: 1px solid {color}; border-radius: 6px;"
            " padding: 2px 0; font-weight: 600; font-size: 11px;"
        )
        caja.addWidget(verbo)

        ruta = QLabel(str(datos.get("path") or ""))
        ruta.setObjectName("ruta")
        ruta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        caja.addWidget(ruta, 1)

        copiar = QPushButton("Copiar")
        # Su propio nombre para darle menos relleno: con el del botón
        # corriente no cabe en la línea y el rótulo sale cortado.
        copiar.setObjectName("copiar-linea")
        copiar.setCursor(Qt.PointingHandCursor)
        copiar.clicked.connect(self._copiar)
        caja.addWidget(copiar)

        columna.addWidget(arriba)

        proposito = QLabel(str(datos.get("purpose") or ""))
        proposito.setObjectName("descripcion")
        proposito.setWordWrap(True)
        columna.addWidget(proposito)

        cuerpo = datos.get("body")
        if cuerpo:
            ejemplo = QLabel(json.dumps(cuerpo, ensure_ascii=False))
            ejemplo.setObjectName("codigo")
            ejemplo.setWordWrap(True)
            ejemplo.setTextInteractionFlags(Qt.TextSelectableByMouse)
            columna.addWidget(ejemplo)

    def _copiar(self) -> None:
        """Lo que se copia es lo que hace falta para llamarlo, no la ruta sola."""
        partes = [f"{self.datos.get('method')} {self.base}{self.datos.get('path')}"]
        cuerpo = self.datos.get("body")
        if cuerpo:
            partes.append(json.dumps(cuerpo, ensure_ascii=False, indent=2))
        _al_portapapeles("\n".join(partes))


class PantallaApi(Pantalla):
    def __init__(self, motor: Motor) -> None:
        super().__init__(
            "API",
            "Conecta cualquier IA a esta memoria. Todo lo que hace BIMNEMO "
            "se puede hacer desde aquí.",
        )
        self.motor = motor
        self.base = motor.base

        self.aviso = Aviso()
        self.anadir(self.aviso)
        self.anadir(self._direccion())
        self.anadir(self._para_la_ia())
        for clave, titulo in GRUPOS.items():
            tarjeta = self._grupo(clave, titulo)
            if tarjeta is not None:
                self.anadir(tarjeta)
        self.anadir(self._modos())
        self.cerrar_con_espacio()

    # -- bloques ------------------------------------------------------------

    def _direccion(self) -> QWidget:
        tarjeta = Tarjeta("Dirección de la memoria")

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)

        direccion = QLabel(self.base)
        direccion.setObjectName("codigo")
        direccion.setTextInteractionFlags(Qt.TextSelectableByMouse)
        caja.addWidget(direccion, 1)

        copiar = QPushButton("Copiar")
        copiar.setCursor(Qt.PointingHandCursor)
        copiar.clicked.connect(lambda: self._copiado(self.base))
        caja.addWidget(copiar)
        tarjeta.anadir(fila)

        nota = QLabel(
            "Escucha solo en esta máquina. Cualquier programa de este "
            "ordenador puede usarla; nada de fuera llega."
        )
        nota.setObjectName("descripcion")
        nota.setWordWrap(True)
        tarjeta.anadir(nota)
        return tarjeta

    def _para_la_ia(self) -> QWidget:
        tarjeta = Tarjeta("Copiar para la IA")

        texto = QLabel(
            "Se lleva la dirección, todos los endpoints con su cuerpo y los "
            "modos de consulta. Pégalo en tu asistente y ya sabe usar esta "
            "memoria."
        )
        texto.setObjectName("descripcion")
        texto.setWordWrap(True)
        tarjeta.anadir(texto)

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.addStretch(1)

        boton = QPushButton("Copiar para la IA")
        boton.setObjectName("principal")
        boton.setCursor(Qt.PointingHandCursor)
        boton.clicked.connect(lambda: self._copiado(self.instrucciones()))
        caja.addWidget(boton)

        tarjeta.anadir(fila)
        return tarjeta

    def _grupo(self, clave: str, titulo: str) -> Optional[QWidget]:
        dentro = [e for e in ENDPOINTS if e.get("group") == clave]
        if not dentro:
            return None

        tarjeta = Tarjeta(titulo)
        # Dentro de cada grupo, por ámbito: primero lo de esta memoria, que
        # es lo que casi siempre se busca.
        for ambito in AMBITOS:
            del_ambito = [e for e in dentro if e.get("scope") == ambito]
            if not del_ambito:
                continue
            rotulo = QLabel(AMBITOS[ambito])
            rotulo.setObjectName("rotulo-ambito")
            tarjeta.anadir(rotulo)
            for endpoint in del_ambito:
                tarjeta.anadir(Endpoint(endpoint, self.base))
        return tarjeta

    def _modos(self) -> QWidget:
        tarjeta = Tarjeta("Modos de consulta")
        for clave, explicacion in MODOS.items():
            tarjeta.dato(clave, explicacion)
        return tarjeta

    # -- copiar -------------------------------------------------------------

    def instrucciones(self) -> str:
        """Todo lo que una IA necesita para usar esta memoria, en texto.

        Se genera del manifiesto, no de una plantilla escrita a mano: si
        mañana hay un endpoint más, aparece aquí solo.
        """
        lineas = [
            "# BIMNEMO — memoria de conocimiento local",
            "",
            f"Dirección: {self.base}",
            "Todas las peticiones con cuerpo van en JSON.",
            "",
        ]
        for clave, titulo in GRUPOS.items():
            dentro = [e for e in ENDPOINTS if e.get("group") == clave]
            if not dentro:
                continue
            lineas.append(f"## {titulo}")
            for e in dentro:
                lineas.append(f"{e.get('method')} {self.base}{e.get('path')}")
                lineas.append(f"    {e.get('purpose')}")
                if e.get("body"):
                    lineas.append(
                        "    cuerpo: "
                        + json.dumps(e["body"], ensure_ascii=False)
                    )
            lineas.append("")

        lineas.append("## Modos de consulta")
        for clave, explicacion in MODOS.items():
            lineas.append(f"- {clave}: {explicacion}")
        return "\n".join(lineas)

    def _copiado(self, texto: str) -> None:
        _al_portapapeles(texto)
        self.aviso.acertar("Copiado al portapapeles.")
