"""El panel de la suscripción de Claude, dentro de «Configuración IA».

Usar Claude por suscripción no es pegar una clave: hay un programa que
instalar —el CLI oficial de Claude Code— y una sesión que abrir en el
navegador. Son dos cosas distintas y en la pantalla se ven como dos etapas,
porque los botones que tienen sentido no son los mismos.

## Las dos etapas

**Sin binario.** Un solo botón: *Descargar e instalar*. No hay nada que
desinstalar ni ninguna sesión que abrir, así que no se enseñan esos botones:
un botón que no puede hacer nada solo invita a pulsarlo y a que no pase nada.

**Con binario.** Se dice dónde está y si hay sesión, y aparecen los botones
que ahora sí valen: *Iniciar sesión*, *Cerrar sesión*, *Probar conexión* y,
aparte de los demás, *Desinstalar*.

## De dónde sale la etapa

De `GET /bimnemo/claude-subscription/download-progress`, que mira **el
disco**. Antes miraba solo lo que había hecho el proceso en marcha, y ese
recuerdo se pierde al reiniciar el motor: quien instaló Claude ayer volvía a
ver «Descarga el binario» hoy, con el binario puesto.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo.motor import ESPERA_LARGA_MS, Motor

#: Cada cuánto se pregunta por la instalación mientras corre.
SONDEO_MS = 500

#: La raíz de los cuatro endpoints de la suscripción.
RUTA = "/bimnemo/claude-subscription"

#: Verde y rojo del resultado de la prueba. Van en el botón, que es donde
#: mira quien acaba de pulsarlo.
VERDE = "color: #16a34a; font-weight: 700;"
ROJO = "color: #dc2626; font-weight: 700;"


class PanelSuscripcion(QWidget):
    """Descargar Claude Code, entrar con tu cuenta y comprobar que responde."""

    def __init__(self, motor: Optional[Motor], padre: Optional[QWidget] = None) -> None:
        super().__init__(padre)
        self.setObjectName("suscripcion")
        self.motor = motor

        #: Lo último que dijo el motor de cada cosa.
        self._descarga: dict[str, Any] = {"state": "inactivo"}
        self._sesion: dict[str, Any] = {"logged_in": False}

        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 6, 0, 0)
        columna.setSpacing(8)

        self.estado = QLabel("")
        self.estado.setObjectName("descripcion")
        self.estado.setWordWrap(True)
        columna.addWidget(self.estado)

        columna.addWidget(self._fila_instalar())
        columna.addWidget(self._barra())
        columna.addWidget(self._fila_sesion())

        self._reloj = QTimer(self)
        self._reloj.setInterval(SONDEO_MS)
        self._reloj.timeout.connect(self._consultar_progreso)

    # -- estructura ---------------------------------------------------------

    def _fila_instalar(self) -> QWidget:
        """La etapa sin binario: un botón y nada más."""
        self.fila_descarga = QWidget()
        self.fila_descarga.setObjectName("fila")
        caja = QHBoxLayout(self.fila_descarga)
        caja.setContentsMargins(0, 0, 0, 0)
        self.boton_descargar = QPushButton("Descargar e instalar")
        self.boton_descargar.setCursor(Qt.PointingHandCursor)
        self.boton_descargar.setToolTip(
            "Descarga el CLI oficial de Claude Code y lo instala en tu usuario."
        )
        self.boton_descargar.clicked.connect(self._descargar)
        caja.addWidget(self.boton_descargar)
        caja.addStretch(1)
        return self.fila_descarga

    def _barra(self) -> QWidget:
        # Indeterminada: el instalador oficial no informa de su avance, y una
        # barra que se inventara un porcentaje mentiría.
        self.barra = QProgressBar()
        self.barra.setTextVisible(False)
        self.barra.setRange(0, 0)
        self.barra.setFixedHeight(6)
        self.barra.hide()
        return self.barra

    def _fila_sesion(self) -> QWidget:
        """La etapa con binario: la sesión arriba, desinstalar abajo y aparte."""
        self.fila_sesion = QWidget()
        self.fila_sesion.setObjectName("fila-sesion")
        caja = QVBoxLayout(self.fila_sesion)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(8)

        self.boton_login = self._boton("Iniciar sesión", self._iniciar_sesion)
        caja.addWidget(self.boton_login)
        self.boton_logout = self._boton("Cerrar sesión", self._cerrar_sesion)
        caja.addWidget(self.boton_logout)
        self.boton_probar = self._boton("Probar conexión", self._probar)
        caja.addWidget(self.boton_probar)

        # Desinstalar, del mismo ancho que los demás: son cuatro acciones de
        # la misma pantalla y una más estrecha se lee como si fuera de otra
        # cosa. Va la última, que es su sitio: deshace lo que hacen las otras.
        self.boton_borrar = self._boton("Desinstalar", self._borrar_binario)
        self.boton_borrar.setToolTip(
            "Borra el binario de Claude Code de este equipo. Tu cuenta y tu "
            "suscripción no se tocan."
        )
        caja.addWidget(self.boton_borrar)

        self.fila_sesion.hide()
        return self.fila_sesion

    @staticmethod
    def _boton(rotulo: str, al_pulsar) -> QPushButton:
        boton = QPushButton(rotulo)
        boton.setCursor(Qt.PointingHandCursor)
        boton.clicked.connect(al_pulsar)
        return boton

    # -- qué se enseña ------------------------------------------------------

    def refrescar(self) -> None:
        """Vuelve a preguntar en qué etapa estamos. La llama la pantalla."""
        if self.motor is None:
            return
        self.motor.get(f"{RUTA}/download-progress", self._llego_descarga, self._fallo)

    def detener(self) -> None:
        """Deja de sondear. Se llama al salir del modo suscripción."""
        self._reloj.stop()

    def _llego_descarga(self, datos: Any) -> None:
        if isinstance(datos, dict):
            self._descarga = datos
        self._pintar()
        if self._descarga.get("state") == "descargando":
            self._reloj.start()
            return
        self._reloj.stop()
        if self._descarga.get("state") == "instalado" and self.motor is not None:
            self.motor.get(f"{RUTA}/status", self._llego_sesion, self._fallo)

    def _consultar_progreso(self) -> None:
        if self.motor is not None:
            self.motor.get(
                f"{RUTA}/download-progress", self._llego_descarga, self._fallo
            )

    def _llego_sesion(self, datos: Any) -> None:
        if isinstance(datos, dict):
            self._sesion = datos
        self._pintar()

    def _pintar(self) -> None:
        etapa = self._descarga.get("state", "inactivo")
        descargando = etapa == "descargando"
        instalado = etapa == "instalado"

        self.barra.setVisible(descargando)
        self.fila_descarga.setVisible(not descargando and not instalado)
        self.fila_sesion.setVisible(instalado)

        if descargando:
            self.estado.setText("Descargando e instalando Claude Code…")
        elif instalado:
            self._pintar_sesion()
        elif etapa == "error":
            self.estado.setText(
                self._descarga.get("message") or "La instalación falló."
            )
        else:
            self.estado.setText(
                "Descarga el binario de Claude Code para usar tu suscripción."
            )

    def _pintar_sesion(self) -> None:
        """Lo que hay que saber de un vistazo: si se puede usar, y desde dónde."""
        iniciado = bool(self._sesion.get("logged_in"))
        self.boton_login.setEnabled(not iniciado)
        self.boton_logout.setEnabled(iniciado)
        self.boton_probar.setEnabled(iniciado)

        donde = str(self._sesion.get("path") or self._descarga.get("path") or "")
        instalado_en = f" Instalado en {donde}." if donde else ""
        self.estado.setText(
            (
                "● Sesión de Claude iniciada. Guarda y reinicia para usar tu "
                "suscripción."
                if iniciado
                else "● Claude Code está instalado, pero no hay sesión. Inicia "
                "sesión con tu cuenta de Claude."
            )
            + instalado_en
        )

    def _ocupado(self, ocupado: bool) -> None:
        for boton in (
            self.boton_descargar,
            self.boton_borrar,
            self.boton_login,
            self.boton_logout,
            self.boton_probar,
        ):
            boton.setEnabled(not ocupado)

    # -- acciones -----------------------------------------------------------

    def _descargar(self) -> None:
        if self.motor is None:
            return
        self.estado.setText("Descargando e instalando Claude Code…")
        self.motor.post(f"{RUTA}/download", {}, self._llego_descarga, self._fallo)

    def _borrar_binario(self) -> None:
        """Quita el binario. Se pregunta antes: borra un fichero del equipo."""
        if self.motor is None or not self.confirmar(
            "Desinstalar Claude Code",
            "Se borrará el binario de Claude Code de este equipo.\n\n"
            "Tu cuenta y tu suscripción no se tocan, y puedes volver a "
            "instalarlo cuando quieras. Mientras no esté, BIMNEMO no podrá "
            "usar el modo «Por suscripción». ¿Seguir?",
        ):
            return
        self._ocupado(True)
        self.estado.setText("Eliminando el binario de Claude Code…")
        self.motor.borrar(f"{RUTA}/download", {}, self._borrado, self._fallo)

    def _borrado(self, datos: Any) -> None:
        self._ocupado(False)
        if isinstance(datos, dict) and not datos.get("ok", True):
            self.estado.setText(
                datos.get("message") or "No se pudo eliminar el binario."
            )
            return
        self._descarga = {"state": "inactivo", "message": ""}
        self._sesion = {"logged_in": False}
        self.refrescar()

    def _iniciar_sesion(self) -> None:
        if self.motor is None:
            return
        self._ocupado(True)
        self.estado.setText("Abre tu navegador y termina el inicio de sesión…")
        # Lo termina una persona en el navegador: el motor espera hasta diez
        # minutos y la ventana no puede rendirse antes que él.
        self.motor.post(
            f"{RUTA}/login",
            {},
            self._sesion_cambiada,
            self._fallo,
            espera_ms=ESPERA_LARGA_MS,
        )

    def _cerrar_sesion(self) -> None:
        if self.motor is None:
            return
        self._ocupado(True)
        self.estado.setText("Cerrando la sesión…")
        self.motor.post(f"{RUTA}/logout", {}, self._sesion_cambiada, self._fallo)

    def _sesion_cambiada(self, _datos: Any) -> None:
        self._ocupado(False)
        # El resultado no se cree a ciegas: se vuelve a preguntar quién hay.
        if self.motor is not None:
            self.motor.get(f"{RUTA}/status", self._llego_sesion, self._fallo)

    def _probar(self) -> None:
        if self.motor is None:
            return
        self._ocupado(True)
        self.boton_probar.setText("Probando…")
        self.boton_probar.setStyleSheet("")
        # La prueba hace una petición real al proveedor: el motor le da un
        # minuto, así que la ventana tiene que darle más.
        self.motor.post(
            f"{RUTA}/probe", {}, self._probado, self._fallo, espera_ms=ESPERA_LARGA_MS
        )

    def _probado(self, datos: Any) -> None:
        self._ocupado(False)
        bien = isinstance(datos, dict) and bool(datos.get("ok"))
        self.boton_probar.setText("● Conectado" if bien else "● Sin conexión")
        self.boton_probar.setStyleSheet(VERDE if bien else ROJO)

    def _fallo(self, motivo: str) -> None:
        self._ocupado(False)
        self._reloj.stop()
        self.estado.setText(motivo or "Error al conectar con la suscripción.")
        self.boton_probar.setText("● Sin conexión")
        self.boton_probar.setStyleSheet(ROJO)

    def confirmar(self, titulo: str, texto: str) -> bool:
        """Pregunta sí o no. Aparte para poder sustituirlo en las pruebas."""
        return (
            QMessageBox.question(self, titulo, texto, QMessageBox.Yes | QMessageBox.No)
            == QMessageBox.Yes
        )


__all__ = ["PanelSuscripcion", "RUTA", "SONDEO_MS"]
