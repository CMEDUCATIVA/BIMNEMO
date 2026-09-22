"""Pantalla «Configuración IA»: elegir proveedor, modelo y clave.

Los proveedores salen de `GET /bimnemo/providers` y no de una lista escrita
aquí. Es importante: el catálogo sabe qué `binding` real le corresponde a
cada proveedor —«DeepSeek» se guarda como `openai` más su dirección, porque
eso es lo que el motor entiende— y duplicar esa traducción en la ventana
sería tener dos catálogos que un día no coinciden.

Guardar **no aplica nada**: escribe el `.env`. El motor construye sus
funciones de LLM y embeddings al arrancar, así que hay que reiniciarlo, y
esta pantalla lo ofrece en cuanto hay algo guardado sin aplicar.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import (
    Aviso,
    Pantalla,
    RejillaTarjetas,
    Tarjeta,
)
from lightrag.api.bimnemo.nativo.razonamiento_control import ControlRazonamiento
from lightrag.api.bimnemo.nativo.reinicio import Reinicio, conectar_barra

#: Las tres secciones configurables, con el nombre que se le enseña a quien
#: no sabe qué es un «embedding».
#: Los idiomas que se ofrecen, los mismos que `configuracion-idioma.js`. El
#: valor va literal al prompt del motor —por eso en inglés—, y el rótulo es
#: lo que se lee. El campo admite cualquiera que el modelo entienda, pero una
#: lista corta evita la errata que estropea una indexación entera.
IDIOMAS = (
    ("Spanish", "Español"),
    ("English", "Inglés"),
    ("Portuguese", "Portugués"),
    ("French", "Francés"),
    ("German", "Alemán"),
    ("Italian", "Italiano"),
    ("Chinese", "Chino"),
)

SECCIONES = (
    (
        "llm",
        "Modelo de lenguaje",
        "El que lee tus documentos y responde tus preguntas. Es lo que más "
        "cuesta y lo que más se nota.",
    ),
    (
        "embedding",
        "Embeddings",
        "Convierte el texto en números para poder buscar por significado y "
        "no por palabras exactas.",
    ),
    (
        "rerank",
        "Reordenado",
        "Opcional. Reordena los resultados de la búsqueda antes de "
        "responder. Se puede dejar en blanco.",
    ),
)

#: Lo que se escribe en el campo de la clave cuando ya hay una guardada.
#:
#: **No se recibe la clave del motor y no se debe.** Dejar la clave real en
#: un campo de texto es dejarla a la vista de cualquiera que mire la
#: pantalla. Si el usuario no toca el campo, no se envía nada y la de antes
#: se queda como está.
CLAVE_PUESTA = "•••••••••••• (guardada)"

#: El dato del elemento «Otro modelo…» del selector.
#:
#: El selector de modelo **no se puede escribir**: un desplegable en el que
#: además se teclea no se lee como un selector, y el texto a medio escribir
#: acababa guardado como nombre de modelo. Pero hay modelos que no están en
#: el catálogo —el que cada uno se baja en Ollama, o los proveedores que no
#: traen lista, como LocalAI—, y a esos se llega por aquí: abre un cuadro,
#: se escribe el nombre exacto y queda en la lista.
OTRO_MODELO = "__otro__"
SIN_MODELO = "— sin modelo —"


class Seccion(QWidget):
    """El formulario de un proveedor: catálogo, modelo, dirección y clave."""

    def __init__(
        self, clave: str, titulo: str, explicacion: str, motor: Optional[Motor] = None
    ) -> None:
        super().__init__()
        self.clave = clave
        self.motor = motor
        self._catalogo: list[dict[str, Any]] = []
        self._tenia_clave = False
        self._suscripcion: Optional[QWidget] = None
        self.modo: Optional[QComboBox] = None

        columna = QVBoxLayout(self)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(0)

        self.tarjeta = Tarjeta(titulo)
        texto = QLabel(explicacion)
        texto.setObjectName("descripcion")
        texto.setWordWrap(True)
        self.tarjeta.anadir(texto)

        self.proveedor = QComboBox()
        self.proveedor.currentIndexChanged.connect(self._cambio_proveedor)
        self._fila("Proveedor", self.proveedor)

        # Solo el modelo de lenguaje ofrece «por suscripción»: un segundo
        # selector que aparece cuando el proveedor lo permite (hoy Claude).
        if clave == "llm":
            self.modo = QComboBox()
            self.modo.addItem("Por API", "api")
            self.modo.addItem("Por suscripción", "suscripcion")
            self.modo.currentIndexChanged.connect(self._cambio_modo)
            self._fila_modo = self._fila("Acceso", self.modo)
            self._fila_modo.hide()

        self.modelo = QComboBox()
        # `activated` y no `currentIndexChanged`: solo lo que elige una
        # persona. Rehacer la lista también cambia el índice.
        self.modelo.activated.connect(self._modelo_elegido)
        self._modelo_anterior = ""
        self._fila("Modelo", self.modelo)

        self.host = QLineEdit()
        self._fila_host = self._fila("Dirección", self.host)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self._fila_clave = self._fila("Clave de API", self.api_key)

        # Solo el modelo de lenguaje razona. Los niveles dependen del modelo,
        # no del proveedor: se rehacen cada vez que cambia uno de los dos.
        self.razonamiento: Optional[ControlRazonamiento] = None
        self._razonamiento_guardado: dict[str, Any] = {}
        if clave == "llm":
            self.razonamiento = ControlRazonamiento()
            self.tarjeta.anadir(self.razonamiento)

        self.pista = QLabel()
        self.pista.setObjectName("descripcion")
        self.pista.setWordWrap(True)
        self.tarjeta.anadir(self.pista)

        # Panel de la suscripción de Claude: descargar, iniciar sesión y probar.
        if clave == "llm":
            self._suscripcion = self._panel_suscripcion()
            self.tarjeta.anadir(self._suscripcion)
            self._suscripcion.hide()

        columna.addWidget(self.tarjeta)

    def _fila(self, nombre: str, control: QWidget) -> QWidget:
        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(12)

        etiqueta = QLabel(nombre)
        etiqueta.setObjectName("dato-nombre")
        etiqueta.setMinimumWidth(130)
        caja.addWidget(etiqueta)
        caja.addWidget(control, 1)

        self.tarjeta.anadir(fila)
        return fila

    # -- carga --------------------------------------------------------------

    def poner_catalogo(self, proveedores: list[dict[str, Any]]) -> None:
        self._catalogo = proveedores or []
        self.proveedor.blockSignals(True)
        self.proveedor.clear()
        for p in self._catalogo:
            etiqueta = p.get("label") or p.get("key") or "?"
            grupo = p.get("group")
            self.proveedor.addItem(
                f"{etiqueta}  ·  {grupo}" if grupo else etiqueta, p.get("key")
            )
        self.proveedor.blockSignals(False)

    def poner_valores(self, valores: dict[str, Any]) -> None:
        clave = valores.get("provider") or valores.get("binding") or ""
        indice = self.proveedor.findData(clave)
        if indice >= 0:
            self.proveedor.blockSignals(True)
            self.proveedor.setCurrentIndex(indice)
            self.proveedor.blockSignals(False)
            self._poner_modelos(self._elegido(), valores.get("model") or "")
        else:
            self._elegir_modelo(valores.get("model") or "")
        self.host.setText(valores.get("host") or "")

        self._tenia_clave = bool(valores.get("api_key_set"))
        self.api_key.setPlaceholderText(
            CLAVE_PUESTA if self._tenia_clave else "Pega aquí tu clave"
        )
        self.api_key.clear()
        self._pintar_pista()

        if self.razonamiento is not None:
            self._razonamiento_guardado = dict(valores)
            self._poner_razonamiento(valores.get("reasoning") or {})

        if self.modo is not None:
            modo = valores.get("mode") or "api"
            indice = self.modo.findData(modo)
            self.modo.blockSignals(True)
            self.modo.setCurrentIndex(indice if indice >= 0 else 0)
            self.modo.blockSignals(False)
        self._aplicar_modo()

    def _poner_razonamiento(self, elegidos: dict[str, str]) -> None:
        """Los niveles del modelo marcado y, encima, lo que había elegido.

        Del catálogo si el modelo está en él; si no, los que calculó el motor
        para el modelo guardado (uno escrito a mano también puede tener barra).
        """
        if self.razonamiento is None:
            return
        modelo = self.modelo_actual()
        info = ((self._elegido() or {}).get("reasoning") or {}).get(modelo)
        guardado = self._razonamiento_guardado
        if info is None and modelo == guardado.get("model"):
            info = guardado.get("reasoning_levels")
        self.razonamiento.poner_niveles(info)
        self.razonamiento.poner_elegidos(elegidos)

    def _elegido(self) -> Optional[dict[str, Any]]:
        clave = self.proveedor.currentData()
        for p in self._catalogo:
            if p.get("key") == clave:
                return p
        return None

    def _cambio_proveedor(self) -> None:
        elegido = self._elegido()
        if elegido is None:
            return
        # Al cambiar de proveedor se propone su dirección y sus modelos. Es
        # lo que evita el error más común: dejar la dirección del proveedor
        # anterior y no entender por qué falla todo.
        self.host.setText(elegido.get("host") or "")
        # Con otro proveedor, su primer modelo. Conservar el de antes dejaba
        # «gpt-4o» elegido para Gemini, que no lo tiene.
        modelos = elegido.get("models") or []
        self._poner_modelos(elegido, modelos[0] if modelos else "")
        self._pintar_pista()
        # Con otro modelo, lo que decida el modelo: un nivel de otro proveedor
        # podría no existir en este, y un ajuste a mano tampoco le serviría.
        self._poner_razonamiento({})
        self._aplicar_modo()

    def _poner_modelos(
        self, proveedor: Optional[dict[str, Any]], elegir: Optional[str] = None
    ) -> None:
        """Los modelos del catálogo y, al final, «Otro modelo…».

        ``elegir`` es el que queda marcado; sin él, el que ya lo estaba. Se
        dice aquí y no después para no añadir a la lista nueva, de paso, el
        modelo de la anterior.
        """
        actual = self.modelo_actual() if elegir is None else elegir
        self.modelo.blockSignals(True)
        self.modelo.clear()
        for m in (proveedor or {}).get("models") or []:
            self.modelo.addItem(m, m)
        if self.modelo.count():
            self.modelo.insertSeparator(self.modelo.count())
        self.modelo.addItem("Otro modelo…", OTRO_MODELO)
        self.modelo.blockSignals(False)
        self._elegir_modelo(actual)

    def modelo_actual(self) -> str:
        """El nombre del modelo elegido; vacío si no hay ninguno."""
        dato = self.modelo.currentData()
        return "" if dato in (None, OTRO_MODELO) else str(dato)

    def _elegir_modelo(self, nombre: str) -> None:
        """Deja marcado ese modelo, añadiéndolo si no está en la lista.

        Un modelo guardado que no está en el catálogo —uno propio, o uno que
        el catálogo ya no ofrece— se añade tal cual y se deja marcado.
        Elegir otro en su lugar lo cambiaría en el siguiente «Guardar» sin
        que nadie lo hubiera pedido. Por lo mismo, sin modelo guardado se
        enseña «— sin modelo —» y no el primero de la lista: el reordenado,
        por ejemplo, se puede dejar en blanco.
        """
        nombre = (nombre or "").strip()
        indice = self.modelo.findData(nombre)
        if indice < 0:
            self.modelo.insertItem(0, nombre or SIN_MODELO, nombre)
            indice = 0
        self.modelo.setCurrentIndex(indice)
        self._modelo_anterior = nombre

    def _modelo_elegido(self, indice: int) -> None:
        anterior = self._modelo_anterior
        if self.modelo.itemData(indice) != OTRO_MODELO:
            self._modelo_anterior = self.modelo_actual()
        else:
            texto, aceptado = QInputDialog.getText(
                self,
                "Otro modelo",
                "Nombre exacto del modelo, tal como lo da el proveedor:",
            )
            # Cancelar deja el que había, no «Otro modelo…» marcado.
            self._elegir_modelo(
                texto.strip() if aceptado and texto.strip() else anterior
            )
        if self.modelo_actual() != anterior:
            self._poner_razonamiento({})

    def _pintar_pista(self) -> None:
        elegido = self._elegido() or {}
        partes = [t for t in (elegido.get("key_hint"), elegido.get("note")) if t]
        if elegido.get("key_url"):
            partes.append(f"Claves: {elegido['key_url']}")
        self.pista.setText("  ·  ".join(partes))
        self.api_key.setEnabled(bool(elegido.get("needs_key", True)))

    # -- suscripción de Claude ----------------------------------------------

    def _es_suscripcion(self) -> bool:
        return self.modo is not None and self.modo.currentData() == "suscripcion"

    def _aplicar_modo(self) -> None:
        """Muestra u oculta el selector de acceso y los controles de suscripción.

        El selector «Acceso» solo existe para proveedores con variante de
        suscripción (hoy Claude). En «por suscripción» la dirección y la clave
        se esconden porque no se usan: la credencial es el login OAuth de
        Claude Code, no una clave de API ni un endpoint.
        """
        if self.modo is None:
            return
        elegido = self._elegido() or {}
        tiene_suscripcion = bool(elegido.get("subscription"))
        self._fila_modo.setVisible(tiene_suscripcion)
        suscripcion = tiene_suscripcion and self._es_suscripcion()
        self._fila_host.setVisible(not suscripcion)
        self._fila_clave.setVisible(not suscripcion)
        if self._suscripcion is not None:
            self._suscripcion.setVisible(suscripcion)
        if suscripcion:
            self.host.clear()
            self.api_key.clear()
            self._pintar_estado_suscripcion()

    def _cambio_modo(self) -> None:
        self._aplicar_modo()

    def _panel_suscripcion(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("suscripcion")
        columna = QVBoxLayout(panel)
        columna.setContentsMargins(0, 6, 0, 0)
        columna.setSpacing(8)

        self.suscripcion_estado = QLabel(
            "Descarga el binario de Claude Code y después inicia sesión."
        )
        self.suscripcion_estado.setObjectName("descripcion")
        self.suscripcion_estado.setWordWrap(True)
        columna.addWidget(self.suscripcion_estado)

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(8)
        self.boton_descargar = QPushButton("Descargar binario")
        self.boton_descargar.setCursor(Qt.PointingHandCursor)
        self.boton_descargar.clicked.connect(self._descargar)
        caja.addWidget(self.boton_descargar)
        self.boton_login = QPushButton("Iniciar sesión")
        self.boton_login.setCursor(Qt.PointingHandCursor)
        self.boton_login.clicked.connect(self._iniciar_sesion)
        caja.addWidget(self.boton_login)
        caja.addStretch(1)
        columna.addWidget(fila)

        fila_prueba = QWidget()
        fila_prueba.setObjectName("fila")
        caja_prueba = QHBoxLayout(fila_prueba)
        caja_prueba.setContentsMargins(0, 0, 0, 0)
        caja_prueba.setSpacing(8)
        self.boton_probar = QPushButton("Probar conexión")
        self.boton_probar.setCursor(Qt.PointingHandCursor)
        self.boton_probar.clicked.connect(self._probar)
        caja_prueba.addWidget(self.boton_probar)
        self.resultado_test = QLabel("")
        self.resultado_test.setObjectName("resultado-test")
        caja_prueba.addWidget(self.resultado_test, 1)
        columna.addWidget(fila_prueba)

        return panel

    def _suscripcion_ocupado(self, ocupado: bool) -> None:
        self.boton_descargar.setEnabled(not ocupado)
        self.boton_login.setEnabled(not ocupado)
        self.boton_probar.setEnabled(not ocupado)

    def _pintar_estado_suscripcion(self) -> None:
        if self.motor is None or not self._es_suscripcion():
            return
        self.motor.get(
            "/bimnemo/claude-subscription/status",
            self._estado_suscripcion,
            self._suscripcion_fallo,
        )

    def _estado_suscripcion(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        if datos.get("logged_in"):
            self.suscripcion_estado.setText(
                "Sesión de Claude iniciada. Guarda y reinicia para usar tu "
                "suscripción."
            )
        else:
            self.suscripcion_estado.setText(
                "Aún no hay sesión. Descarga el binario y después inicia sesión."
            )

    def _descargar(self) -> None:
        if self.motor is None:
            return
        self._suscripcion_ocupado(True)
        self.suscripcion_estado.setText("Descargando el binario de Claude Code…")
        self.motor.post(
            "/bimnemo/claude-subscription/download",
            {},
            self._descargado,
            self._suscripcion_fallo,
        )

    def _descargado(self, datos: Any) -> None:
        self._suscripcion_ocupado(False)
        if isinstance(datos, dict) and datos.get("ok"):
            self.suscripcion_estado.setText("Binario instalado. Ahora inicia sesión.")
        else:
            self._suscripcion_fallo(
                (datos or {}).get("message")
                if isinstance(datos, dict)
                else "No se pudo descargar."
            )
        self._pintar_estado_suscripcion()

    def _iniciar_sesion(self) -> None:
        if self.motor is None:
            return
        self._suscripcion_ocupado(True)
        self.suscripcion_estado.setText(
            "Abre tu navegador y termina el inicio de sesión…"
        )
        self.motor.post(
            "/bimnemo/claude-subscription/login",
            {},
            self._sesion_iniciada,
            self._suscripcion_fallo,
        )

    def _sesion_iniciada(self, datos: Any) -> None:
        self._suscripcion_ocupado(False)
        if isinstance(datos, dict) and datos.get("ok"):
            self.suscripcion_estado.setText(
                "Sesión de Claude iniciada. Guarda y reinicia para usar tu "
                "suscripción."
            )
        else:
            self._suscripcion_fallo(
                (datos or {}).get("message")
                if isinstance(datos, dict)
                else "No se pudo iniciar sesión."
            )
        self._pintar_estado_suscripcion()

    def _probar(self) -> None:
        if self.motor is None:
            return
        self._suscripcion_ocupado(True)
        self.resultado_test.setText("Probando…")
        self.resultado_test.setStyleSheet("")
        self.motor.post(
            "/bimnemo/claude-subscription/probe",
            {},
            self._probado,
            self._suscripcion_fallo,
        )

    def _probado(self, datos: Any) -> None:
        self._suscripcion_ocupado(False)
        bien = isinstance(datos, dict) and bool(datos.get("ok"))
        if bien:
            self.resultado_test.setText("● Conectado")
            self.resultado_test.setStyleSheet("color: #16a34a; font-weight: 700;")
        else:
            self.resultado_test.setText("● Sin conexión")
            self.resultado_test.setStyleSheet("color: #dc2626; font-weight: 700;")

    def _suscripcion_fallo(self, motivo: str) -> None:
        self._suscripcion_ocupado(False)
        self.suscripcion_estado.setText(motivo or "Error al conectar con la suscripción.")
        self.resultado_test.setText("● Sin conexión")
        self.resultado_test.setStyleSheet("color: #dc2626; font-weight: 700;")

    # -- guardado -----------------------------------------------------------

    def falta_clave(self) -> bool:
        """¿Pide clave este proveedor y no hay ninguna, ni escrita ni guardada?"""
        if self._es_suscripcion():
            return False
        return (
            self.api_key.isEnabled()
            and not self.api_key.text().strip()
            and not self._tenia_clave
        )

    def a_peticion(self) -> dict[str, Any]:
        elegido = self._elegido() or {}
        datos: dict[str, Any] = {
            "provider": self.proveedor.currentData() or "",
            "binding": elegido.get("binding") or "",
            "model": self.modelo_actual(),
            "host": self.host.text().strip(),
        }
        if self.modo is not None:
            datos["mode"] = self.modo.currentData() or "api"
        escrita = self.api_key.text().strip()
        if escrita:
            datos["api_key"] = escrita
        if self.razonamiento is not None:
            datos["reasoning"] = self.razonamiento.elegidos()
        # Si no escribió nada, no se manda la clave: así no se borra la que
        # ya estaba por el hecho de guardar otro campo.
        return datos


class AvisoPeligro(QDialog):
    """Un aviso de los que rompen algo: en rojo, y con la salida segura delante.

    No es un ``QMessageBox`` porque ése pinta el triángulo amarillo de
    Windows y dos botones iguales, y aquí los botones no pesan lo mismo:
    «No continuar» es lo que conviene casi siempre, así que va en rojo
    lleno, es el botón por defecto (Intro) y el que tiene el foco. Seguir
    adelante queda discreto, con un nombre que dice lo que es.
    """

    # Con {titulo} y {discreto} según el tema: el rojo claro que se lee bien
    # sobre fondo oscuro se pierde sobre blanco, y al revés.
    ESTILO = """
        #banda {{
            background: rgba(220, 38, 38, 0.13);
            border-left: 4px solid #dc2626;
            border-radius: 6px;
        }}
        #banda-icono {{
            background: #dc2626;
            color: #ffffff;
            border-radius: 13px;
            font-size: 16px;
            font-weight: 800;
        }}
        #banda-titulo {{ color: {titulo}; font-size: 15px; font-weight: 700; }}
        #aviso-texto {{ font-size: 13px; }}
        QPushButton#parar {{
            background: #dc2626;
            border: 1px solid #dc2626;
            color: #ffffff;
            font-weight: 700;
            padding: 8px 18px;
        }}
        QPushButton#parar:hover {{ background: #b91c1c; border-color: #b91c1c; }}
        QPushButton#parar:focus {{ border: 2px solid #fca5a5; }}
        QPushButton#seguir {{
            background: transparent;
            border: 1px solid {discreto_borde};
            color: {discreto};
            padding: 8px 14px;
        }}
        QPushButton#seguir:hover {{ color: {discreto_hover}; }}
    """

    def __init__(
        self,
        padre: Optional[QWidget],
        titulo: str,
        cabecera: str,
        texto: str,
        parar: str = "No continuar",
        seguir: str = "Continuar de todos modos",
    ) -> None:
        super().__init__(padre)
        self.setWindowTitle(titulo)
        from lightrag.api.bimnemo.nativo import tema

        oscuro = tema.ACTUAL is tema.OSCURO
        self.setStyleSheet(
            self.ESTILO.format(
                titulo="#f87171" if oscuro else "#b91c1c",
                discreto="#94a3b8" if oscuro else "#475569",
                discreto_borde="rgba(148, 163, 184, 0.35)" if oscuro else "#cbd5e1",
                discreto_hover="#e2e8f0" if oscuro else "#0f172a",
            )
        )
        self.setMinimumWidth(520)
        self.continuar = False

        columna = QVBoxLayout(self)
        columna.setContentsMargins(22, 20, 22, 18)
        columna.setSpacing(16)

        banda = QWidget()
        banda.setObjectName("banda")
        banda.setAttribute(Qt.WA_StyledBackground, True)
        banda.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        fila = QHBoxLayout(banda)
        fila.setContentsMargins(14, 10, 14, 10)
        fila.setSpacing(12)
        # Un «!» en un círculo rojo dibujado, y no el ⚠ del sistema: Windows
        # lo pinta como emoji amarillo y se come el rojo del aviso.
        icono = QLabel("!")
        icono.setObjectName("banda-icono")
        icono.setAlignment(Qt.AlignCenter)
        icono.setFixedSize(26, 26)
        fila.addWidget(icono)
        rotulo = QLabel(cabecera)
        rotulo.setObjectName("banda-titulo")
        rotulo.setWordWrap(True)
        fila.addWidget(rotulo, 1)
        columna.addWidget(banda)

        cuerpo = QLabel(texto)
        cuerpo.setObjectName("aviso-texto")
        cuerpo.setTextFormat(Qt.RichText)
        cuerpo.setWordWrap(True)
        columna.addWidget(cuerpo)

        botones = QHBoxLayout()
        botones.setSpacing(10)
        botones.addStretch(1)
        self.boton_seguir = QPushButton(seguir)
        self.boton_seguir.setObjectName("seguir")
        self.boton_seguir.setCursor(Qt.PointingHandCursor)
        self.boton_seguir.setAutoDefault(False)
        self.boton_seguir.clicked.connect(self._seguir)
        botones.addWidget(self.boton_seguir)
        self.boton_parar = QPushButton(parar)
        self.boton_parar.setObjectName("parar")
        self.boton_parar.setCursor(Qt.PointingHandCursor)
        self.boton_parar.setDefault(True)
        self.boton_parar.clicked.connect(self.reject)
        botones.addWidget(self.boton_parar)
        columna.addLayout(botones)
        self.boton_parar.setFocus()

    def _seguir(self) -> None:
        self.continuar = True
        self.accept()


class PantallaConfiguracion(Pantalla):
    def __init__(self, motor: Motor) -> None:
        super().__init__(
            "Configuración IA",
            "BIMNEMO necesita un modelo de IA para entender tus documentos. "
            "Aquí se elige cuál y se pega la clave.",
        )
        self.motor = motor
        # El embedding con el que arrancó la pantalla y si ya hay vectores
        # hechos con él: cambiarlo entonces deja el motor sin arrancar.
        self._embedding_guardado: tuple[str, str] = ("", "")
        self._embedding_valores: dict[str, Any] = {}
        self._hay_vectores = False
        # Ya dijo «Continuar» a este cambio: no se le vuelve a preguntar.
        self._cambio_aceptado = False
        # El reinicio en curso lo lanzó «Guardar», no el botón de reiniciar.
        self._tras_guardar = False
        # Hay configuración guardada que el motor todavía no usa.
        self._pendiente = False

        self.aviso = Aviso()
        self.anadir(self.aviso)

        self.secciones: dict[str, Seccion] = {}
        for clave, titulo, explicacion in SECCIONES:
            self.secciones[clave] = Seccion(clave, titulo, explicacion, motor)

        # Se avisa al elegir, no solo al guardar: es cuando se decide.
        # `activated` y no `currentIndexChanged`, para que solo salte con lo
        # que elige una persona y no al cargar los valores guardados.
        embedding = self.secciones["embedding"]
        embedding.proveedor.activated.connect(self._embedding_elegido)
        embedding.modelo.activated.connect(self._embedding_elegido)

        # De dos en dos, como en la web. La de acciones sí va entera, debajo:
        # afecta a todas.
        self.rejilla = RejillaTarjetas([*self.secciones.values(), self._idioma()])
        self.anadir(self.rejilla)

        self.anadir(self._acciones())
        self.cerrar_con_espacio()

        self.refrescar()

    def _idioma(self) -> QWidget:
        """Idioma de la memoria: un selector, como en la web.

        Era un campo de texto libre, y ahí está el peligro: el valor va
        literal al prompt del motor, y una errata —«Spansih»— estropea una
        indexación entera sin avisar. Con la lista no se puede escribir mal.
        """
        tarjeta = Tarjeta("Idioma de la memoria")
        texto = QLabel("En qué idioma se escriben las entidades y las respuestas.")
        texto.setObjectName("descripcion")
        texto.setWordWrap(True)
        tarjeta.anadir(texto)

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(12)
        etiqueta = QLabel("Idioma")
        etiqueta.setObjectName("dato-nombre")
        etiqueta.setMinimumWidth(130)
        caja.addWidget(etiqueta)

        self.idioma = QComboBox()
        for valor, rotulo in IDIOMAS:
            self.idioma.addItem(rotulo, valor)
        caja.addWidget(self.idioma, 1)
        tarjeta.anadir(fila)

        ayuda = QLabel("Se guarda como SUMMARY_LANGUAGE.")
        ayuda.setObjectName("pista")
        tarjeta.anadir(ayuda)

        # El aviso, visible y no escondido en la descripción: es el único
        # ajuste de esta pantalla que no se arregla sin reindexar.
        aviso = Aviso()
        aviso.informar(
            "Cambiarlo no reescribe lo ya indexado: las entidades guardadas "
            "conservan el idioma con el que se extrajeron. Para unificarlo hay "
            "que vaciar la memoria y volver a indexar."
        )
        tarjeta.anadir(aviso)
        return tarjeta

    def _acciones(self) -> QWidget:
        tarjeta = Tarjeta()

        self.barra = QProgressBar()
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(6)
        self.barra.hide()
        tarjeta.anadir(self.barra)

        self.estado = Aviso()
        tarjeta.anadir(self.estado)

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)
        caja.addStretch(1)

        self.boton_reiniciar = QPushButton("Reiniciar motor")
        self.boton_reiniciar.setCursor(Qt.PointingHandCursor)
        self.boton_reiniciar.clicked.connect(self._reiniciar)
        caja.addWidget(self.boton_reiniciar)

        self.boton_guardar = QPushButton("Guardar")
        self.boton_guardar.setObjectName("principal")
        self.boton_guardar.setCursor(Qt.PointingHandCursor)
        self.boton_guardar.clicked.connect(self._guardar)
        caja.addWidget(self.boton_guardar)

        tarjeta.anadir(fila)
        return tarjeta

    # -- datos --------------------------------------------------------------

    def refrescar(self) -> None:
        self.motor.get("/bimnemo/providers", self._pintar_catalogo, self._fallo)
        self.motor.get("/bimnemo/settings", self._pintar_valores, self._fallo)

    def _pintar_catalogo(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        for clave, seccion in self.secciones.items():
            seccion.poner_catalogo(datos.get(clave) or [])
        # El catálogo puede llegar después de los valores; en ese caso hay
        # que volver a colocarlos o el desplegable se queda en el primero.
        self.motor.get("/bimnemo/settings", self._pintar_valores, self._fallo)

    def _pintar_valores(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        for clave, seccion in self.secciones.items():
            seccion.poner_valores(datos.get(clave) or {})
        self._poner_idioma(str(datos.get("language") or ""))
        embedding = datos.get("embedding") or {}
        self._embedding_guardado = (
            str(embedding.get("binding") or ""),
            str(embedding.get("model") or ""),
        )
        self._embedding_valores = dict(embedding)
        self._hay_vectores = bool(datos.get("has_vectors"))
        self._cambio_aceptado = False

        self._pendiente = bool(datos.get("restart_required"))
        if self._pendiente:
            self.estado.informar(
                "Hay configuración guardada que el motor todavía no usa. "
                "Reinicia para aplicarla."
            )

    def _poner_idioma(self, actual: str) -> None:
        """Marca el idioma guardado, aunque no esté en la lista.

        Si alguien lo cambió a mano en el `.env` —«Catalan», por ejemplo—, se
        añade tal cual y se deja marcado. Elegir el primero de la lista en su
        lugar cambiaría el idioma en el siguiente «Guardar» sin que nadie lo
        hubiera pedido.
        """
        if not actual:
            return
        indice = self.idioma.findData(actual)
        if indice < 0:
            self.idioma.insertItem(0, actual, actual)
            indice = 0
        self.idioma.setCurrentIndex(indice)

    def _fallo(self, motivo: str) -> None:
        self.aviso.fallar(motivo)

    # -- acciones -----------------------------------------------------------

    def cambio_de_embedding(self) -> Optional[tuple[str, str]]:
        """``(modelo actual, modelo nuevo)`` si se va a cambiar con vectores hechos."""
        nuevo = self.secciones["embedding"].a_peticion()
        binding, modelo = self._embedding_guardado
        if not self._hay_vectores or not modelo:
            return None
        if (nuevo["binding"], nuevo["model"]) == (binding, modelo):
            return None
        return modelo, nuevo["model"] or nuevo["provider"]

    def preguntar(self, titulo: str, texto: str) -> bool:
        """Aviso en rojo: «No continuar» o seguir. Devuelve si eligió seguir."""
        aviso = AvisoPeligro(
            self, titulo, "Tus memorias dejarán de abrirse", texto
        )
        aviso.exec()
        return aviso.continuar

    def _confirmar_cambio_de_embedding(self) -> bool:
        """Avisa de que el embedding elegido no casa con las memorias.

        Cambiarlo no rompe nada todavía; lo rompe el reinicio: el motor no
        arranca con vectores de otro modelo. Mejor decirlo cuando aún se
        puede no hacerlo que en un error al abrir.
        """
        cambio = self.cambio_de_embedding()
        if cambio is None:
            self._cambio_aceptado = False
            return True
        if self._cambio_aceptado:
            return True
        actual, nuevo = cambio
        self._cambio_aceptado = self.preguntar(
            "Cambiar el modelo de embeddings",
            f"Tus memorias ya tienen grafos hechos con <b>«{actual}»</b>. Los "
            f"vectores de un modelo no sirven para otro: con <b>«{nuevo}»</b>, "
            "al reiniciar, el motor <b>no podrá abrirlas</b>.<br><br>"
            "Para usarlo habría que reconstruir los índices, lo que vuelve a "
            "enviar todo el texto al proveedor nuevo (gasta saldo). Si BIMNEMO "
            f"no arranca, te ofrecerá volver a «{actual}».<br><br>"
            "Si no estás seguro, pulsa <b>No continuar</b>: todo se queda "
            "como está.",
        )
        return self._cambio_aceptado

    def _embedding_elegido(self, _indice: int = 0) -> None:
        """Al elegir otro proveedor o modelo: avisar, y si no sigue, deshacer."""
        if self._confirmar_cambio_de_embedding():
            return
        self.secciones["embedding"].poner_valores(self._embedding_valores)
        self.estado.informar(
            f"Se mantiene «{self._embedding_guardado[1]}» para los embeddings."
        )

    def _guardar(self) -> None:
        if not self._confirmar_cambio_de_embedding():
            self.estado.informar("No se ha guardado nada.")
            return
        cuerpo: dict[str, Any] = {
            clave: seccion.a_peticion() for clave, seccion in self.secciones.items()
        }
        cuerpo["language"] = str(self.idioma.currentData() or "")

        self.boton_guardar.setEnabled(False)
        self.estado.informar("Guardando…")
        self.motor.post("/bimnemo/settings", cuerpo, self._guardado, self._no_guardo)

    def _guardado(self, datos: Any) -> None:
        """Guardado: y ahora aplicarlo, que es lo que se quería.

        Antes solo se decía «reinicia el motor» en una línea pequeña, y el
        usuario guardó `deepseek-flash`, no reinició, y el motor indexó un
        documento entero con `deepseek-v4-pro`. Guardar sin aplicar no le
        sirve a nadie: se reinicia aquí mismo. Si el motor está indexando se
        negará (409), y `_reiniciado` explica qué hacer.
        """
        self.boton_guardar.setEnabled(True)
        # Sin cambios no basta para no reiniciar: puede haber algo guardado
        # antes y todavía sin aplicar, que es justo cuando más falta hace.
        cambio = not isinstance(datos, dict) or datos.get("restart_required", True)
        if not cambio and not self._pendiente:
            # O no cambió nada, o era solo el razonamiento y el motor ya lo
            # aplicó en caliente: lo dice su mensaje.
            mensaje = datos.get("message") if isinstance(datos, dict) else ""
            self.estado.acertar(mensaje or "No había nada que cambiar.")
            self.refrescar()
            return
        self.estado.informar("Guardado. Reiniciando el motor para aplicarlo…")
        self._tras_guardar = True
        self._reiniciar()

    def _no_guardo(self, motivo: str) -> None:
        self.boton_guardar.setEnabled(True)
        self.estado.fallar(motivo)

    def _reiniciar(self) -> None:
        self.boton_reiniciar.setEnabled(False)
        self.barra.setValue(0)
        self.barra.show()

        self._trabajo = Reinicio(self.motor, self)
        conectar_barra(
            self._trabajo,
            self.estado.informar,
            lambda hecho, tope: (
                self.barra.setMaximum(tope),
                self.barra.setValue(hecho),
            ),
        )
        self._trabajo.terminado.connect(self._reiniciado)
        self._trabajo.arrancar()

    def _reiniciado(self, bien: bool, motivo: str) -> None:
        self.barra.hide()
        self.boton_reiniciar.setEnabled(True)
        tras_guardar, self._tras_guardar = self._tras_guardar, False
        if bien:
            self.estado.acertar("El motor ha vuelto con la configuración nueva.")
            self.refrescar()
        elif tras_guardar:
            # Lo corriente: está indexando y no se corta a mitad. Lo guardado
            # está a salvo, pero NO se está usando: hay que decirlo claro.
            self.estado.fallar(
                "Guardado, pero todavía NO se usa: el motor está indexando y "
                "sigue con el modelo anterior. Pausa la indexación en Archivos "
                "o espera a que termine, y pulsa «Reiniciar motor»."
            )
            self.refrescar()
        else:
            self.estado.fallar(motivo)
