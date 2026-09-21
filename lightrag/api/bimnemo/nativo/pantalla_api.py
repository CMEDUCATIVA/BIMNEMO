"""Pantalla «API»: cómo conectar cualquier IA a esta memoria.

Los mismos paneles que la interfaz web y en su orden: la dirección, los
endpoints por ámbito —esta memoria, todas las memorias, el motor—, un
ejemplo, los modos de recuperación y el acceso.

## Las rutas siguen a la memoria abierta

Cambiar de memoria **cambia los endpoints que se enseñan**. No es cosmética:
con «Obra Sur» abierta, copiar `/bimnemo/memory/search` lee la memoria por
defecto. Funciona al pegarlo y devuelve lo que no es, que es peor que
fallar. Quien resuelve cada ruta es `api_rutas`.

## Swagger y ReDoc se abren fuera

La ventana nativa no lleva motor web —esa fue justo la decisión que la hizo
nativa—, así que no puede pintar Swagger dentro. Las solapas están y lo
abren en el navegador. Fingir que están dentro sería mentir sobre lo que se
puede hacer aquí.
"""

from __future__ import annotations

import secrets
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.manifiesto import AMBITOS, ENDPOINTS, MODOS
from lightrag.api.bimnemo.nativo import api_piezas, api_rutas, api_textos, iconos
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Pantalla, Tarjeta

#: Las tres solapas, con lo que abre cada una. La «Guía» es esta pantalla.
SOLAPAS = (("Guía", ""), ("Swagger", "/docs"), ("ReDoc", "/redoc"))

#: Longitud de la clave que se genera, y su alfabeto.
#:
#: Sin parejas que se confundan al copiarlas a mano: nada de `0/O` ni de
#: `1/l/I`. Una clave que se teclea mal es una clave que parece rota.
LARGO_CLAVE = 32
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


class PantallaApi(Pantalla):
    def __init__(self, motor: Motor) -> None:
        super().__init__(
            "API",
            "Conecta cualquier IA a esta memoria. Todo lo que hace BIMNEMO "
            "se puede hacer desde aquí.",
        )
        self.motor = motor
        self.base = motor.base
        self._memoria = motor.memoria
        self._clave = ""
        self._paneles: list = []

        self.aviso = Aviso()
        self.anadir(self._encabezado())
        self.anadir(self.aviso)
        self.anadir(self._direccion())

        # Los paneles de endpoints se rehacen al cambiar de memoria, así que
        # van en su propio contenedor y no sueltos en la pantalla.
        zona = QWidget()
        zona.setObjectName("fila")
        self.caja_endpoints = QVBoxLayout(zona)
        self.caja_endpoints.setContentsMargins(0, 0, 0, 0)
        self.caja_endpoints.setSpacing(16)
        self.anadir(zona)

        self.anadir(self._ejemplo())
        self.anadir(self._modos())
        self.anadir(self._acceso())
        self.cerrar_con_espacio()

        self.refrescar()

    # -- encabezado ---------------------------------------------------------

    def _encabezado(self) -> QWidget:
        caja = QWidget()
        caja.setObjectName("fila")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)
        fila.addStretch(1)

        copiar = QPushButton("  Copiar para la IA")
        copiar.setObjectName("principal")
        copiar.setIcon(iconos.icono("copiar", 14, "#ffffff"))
        copiar.setCursor(Qt.PointingHandCursor)
        copiar.clicked.connect(self._copiar_para_la_ia)
        fila.addWidget(copiar)

        self.solapas = api_piezas.Pestanas(tuple(n for n, _r in SOLAPAS))
        self.solapas.elegida.connect(self._abrir_solapa)
        fila.addWidget(self.solapas)
        return caja

    def _abrir_solapa(self, nombre: str) -> None:
        for rotulo, ruta in SOLAPAS:
            if rotulo != nombre or not ruta:
                continue
            QDesktopServices.openUrl(QUrl(f"{self.base}{ruta}"))
            self.aviso.informar(
                f"{nombre} se ha abierto en tu navegador: {self.base}{ruta}"
            )
            return
        self.aviso.callar()

    # -- paneles ------------------------------------------------------------

    def _direccion(self) -> QWidget:
        panel = api_piezas.Panel(
            "Dirección de la memoria", "entidades", "Sin autenticación"
        )
        self.panel_direccion = panel

        panel.anadir(
            api_piezas.fila_con_boton(
                self.base, "Copiar", lambda: self._copiado(self.base)
            )
        )

        nota = QLabel(
            "Escucha solo en esta máquina. Cualquier programa de este "
            "ordenador puede usarla; nada de fuera llega."
        )
        nota.setObjectName("descripcion")
        nota.setWordWrap(True)
        panel.anadir(nota)
        return panel

    def _pintar_endpoints(self) -> None:
        """Rehace los paneles con las rutas de la memoria abierta."""
        while self.caja_endpoints.count():
            viejo = self.caja_endpoints.takeAt(0)
            if viejo.widget():
                viejo.widget().deleteLater()

        self._paneles = api_rutas.por_ambito(ENDPOINTS, self._memoria, AMBITOS)
        for clave, titulo, filas in self._paneles:
            nota = (self._memoria or "General") if clave == "esta" else ""
            panel = api_piezas.Panel(titulo, "api", nota)
            for fila in filas:
                panel.anadir(api_piezas.Fila(fila, self.base))
            self.caja_endpoints.addWidget(panel)

    def _ejemplo(self) -> QWidget:
        panel = api_piezas.Panel("Ejemplo", "copiar")

        self.ejemplo_curl = self._bloque_de_codigo(panel)
        self.ejemplo_python = self._bloque_de_codigo(panel)

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.addStretch(1)
        for rotulo, dame in (
            ("Copiar curl", lambda: self.ejemplo_curl.text()),
            ("Copiar Python", lambda: self.ejemplo_python.text()),
        ):
            boton = QPushButton(rotulo)
            boton.setCursor(Qt.PointingHandCursor)
            boton.clicked.connect(lambda _c=False, d=dame: self._copiado(d()))
            caja.addWidget(boton)
        panel.anadir(fila)
        return panel

    @staticmethod
    def _bloque_de_codigo(panel: api_piezas.Panel) -> QLabel:
        etiqueta = QLabel("")
        etiqueta.setObjectName("codigo")
        etiqueta.setWordWrap(True)
        etiqueta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        panel.anadir(etiqueta)
        return etiqueta

    def _modos(self) -> QWidget:
        panel = api_piezas.Panel("Modos de recuperación", "trozos")
        tarjeta = Tarjeta()
        for nombre, explicacion in MODOS.items():
            tarjeta.dato(nombre, explicacion)
        panel.anadir(tarjeta)
        return panel

    # -- acceso -------------------------------------------------------------

    def _acceso(self) -> QWidget:
        panel = api_piezas.Panel("Acceso a la API", "motor")

        texto = QLabel(
            "Por defecto la memoria está abierta a cualquier programa de esta "
            "máquina. Al exigir clave, quien la use tendrá que mandarla en la "
            "cabecera X-API-Key.\n\n"
            "El guardia de las rutas se construye al arrancar el motor, así "
            "que el cambio pide un reinicio."
        )
        texto.setObjectName("descripcion")
        texto.setWordWrap(True)
        panel.anadir(texto)

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)

        self.interruptor = api_piezas.Interruptor()
        self.interruptor.clicked.connect(self._cambiar_acceso)
        caja.addWidget(self.interruptor)

        self.estado_acceso = QLabel("Abierta, sin clave")
        self.estado_acceso.setObjectName("dato-valor")
        caja.addWidget(self.estado_acceso, 1)
        panel.anadir(fila)

        self.caja_clave = QWidget()
        self.caja_clave.setObjectName("fila")
        caja2 = QHBoxLayout(self.caja_clave)
        caja2.setContentsMargins(0, 0, 0, 0)
        caja2.setSpacing(10)

        self.clave = QLineEdit()
        self.clave.setReadOnly(True)
        self.clave.setPlaceholderText("Se genera al activar")
        caja2.addWidget(self.clave, 1)

        copiar = QPushButton("Copiar clave")
        copiar.setCursor(Qt.PointingHandCursor)
        copiar.clicked.connect(lambda: self._copiado(self.clave.text()))
        caja2.addWidget(copiar)

        self.caja_clave.hide()
        panel.anadir(self.caja_clave)
        return panel

    def _cambiar_acceso(self) -> None:
        exigir = self.interruptor.isChecked()
        cuerpo: dict[str, Any] = {"enabled": exigir}
        if exigir:
            # La clave se genera **aquí** y se enseña una vez: el motor solo
            # guarda que la exige, y no hay forma de recuperarla después. Por
            # eso el campo de copiar aparece justo al activarla.
            self._clave = "".join(
                secrets.choice(ALFABETO) for _ in range(LARGO_CLAVE)
            )
            cuerpo["key"] = self._clave

        self.motor.post(
            "/bimnemo/access", cuerpo, self._acceso_cambiado, self._fallo_acceso
        )

    def _acceso_cambiado(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        exigir = bool(datos.get("enabled"))
        self._pintar_acceso(exigir)

        if exigir:
            self.clave.setText(self._clave)
            # Que la ventana siga hablando con el motor tras el reinicio.
            self.motor.usar_clave(self._clave)
        else:
            self._clave = ""
            self.motor.usar_clave("")

        mensaje = str(datos.get("message") or "")
        if datos.get("restart_required"):
            mensaje += "  Reinicia el motor para que tenga efecto."
        self.aviso.acertar(mensaje.strip() or "Guardado.")
        self._refrescar_ejemplos()

    def _fallo_acceso(self, motivo: str) -> None:
        # El interruptor vuelve a donde estaba: dejarlo encendido cuando el
        # motor ha dicho que no es mentirle al usuario.
        self.interruptor.setChecked(not self.interruptor.isChecked())
        self.aviso.fallar(motivo)

    def _pintar_acceso(self, exigir: bool) -> None:
        self.interruptor.setChecked(exigir)
        self.estado_acceso.setText(
            "Exige clave" if exigir else "Abierta, sin clave"
        )
        self.panel_direccion.nota.setText(
            "Exige clave" if exigir else "Sin autenticación"
        )
        self.caja_clave.setVisible(exigir)

    # -- datos --------------------------------------------------------------

    def refrescar(self) -> None:
        self._memoria = self.motor.memoria
        self._pintar_endpoints()
        self._refrescar_ejemplos()

    def cambiar_memoria(self, nemo: str) -> None:
        """La ventana llama a esto al cambiar de memoria."""
        if nemo == self._memoria:
            return
        self._memoria = nemo
        self._pintar_endpoints()
        self._refrescar_ejemplos()

    def showEvent(self, evento) -> None:  # noqa: N802 (nombre de Qt)
        """Al volver a la pantalla, seguir a la memoria que haya activa.

        El cambio de memoria se hace desde la barra de arriba, que no sabe
        de esta pantalla. Comprobarlo al mostrarse cuesta nada y evita
        enseñar rutas de la memoria anterior.
        """
        super().showEvent(evento)
        self.cambiar_memoria(self.motor.memoria)

    def _refrescar_ejemplos(self) -> None:
        rutas = api_rutas.de_memoria(ENDPOINTS, self._memoria)
        self.ejemplo_curl.setText(
            api_textos.ejemplo_curl(self.base, rutas, self._clave)
        )
        self.ejemplo_python.setText(
            api_textos.ejemplo_python(self.base, rutas, self._clave)
        )

    # -- copiar -------------------------------------------------------------

    def _copiar_para_la_ia(self) -> None:
        self._copiado(
            api_textos.instrucciones(
                self.base, self._memoria, self._paneles, MODOS, self._clave
            )
        )

    def _copiado(self, texto: str) -> None:
        api_piezas.al_portapapeles(texto)
        self.aviso.acertar("Copiado al portapapeles.")
