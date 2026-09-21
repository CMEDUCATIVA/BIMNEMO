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
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
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

    def __init__(self, clave: str, titulo: str, explicacion: str) -> None:
        super().__init__()
        self.clave = clave
        self._catalogo: list[dict[str, Any]] = []
        self._tenia_clave = False

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

        self.modelo = QComboBox()
        # `activated` y no `currentIndexChanged`: solo lo que elige una
        # persona. Rehacer la lista también cambia el índice.
        self.modelo.activated.connect(self._modelo_elegido)
        self._modelo_anterior = ""
        self._fila("Modelo", self.modelo)

        self.host = QLineEdit()
        self._fila("Dirección", self.host)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self._fila("Clave de API", self.api_key)

        self.pista = QLabel()
        self.pista.setObjectName("descripcion")
        self.pista.setWordWrap(True)
        self.tarjeta.anadir(self.pista)

        columna.addWidget(self.tarjeta)

    def _fila(self, nombre: str, control: QWidget) -> None:
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
        if self.modelo.itemData(indice) != OTRO_MODELO:
            self._modelo_anterior = self.modelo_actual()
            return
        texto, aceptado = QInputDialog.getText(
            self,
            "Otro modelo",
            "Nombre exacto del modelo, tal como lo da el proveedor:",
        )
        # Cancelar deja el que había, no «Otro modelo…» marcado.
        self._elegir_modelo(
            texto.strip() if aceptado and texto.strip() else self._modelo_anterior
        )

    def _pintar_pista(self) -> None:
        elegido = self._elegido() or {}
        partes = [t for t in (elegido.get("key_hint"), elegido.get("note")) if t]
        if elegido.get("key_url"):
            partes.append(f"Claves: {elegido['key_url']}")
        self.pista.setText("  ·  ".join(partes))
        self.api_key.setEnabled(bool(elegido.get("needs_key", True)))

    # -- guardado -----------------------------------------------------------

    def falta_clave(self) -> bool:
        """¿Pide clave este proveedor y no hay ninguna, ni escrita ni guardada?"""
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
        escrita = self.api_key.text().strip()
        if escrita:
            datos["api_key"] = escrita
        # Si no escribió nada, no se manda la clave: así no se borra la que
        # ya estaba por el hecho de guardar otro campo.
        return datos


class PantallaConfiguracion(Pantalla):
    def __init__(self, motor: Motor) -> None:
        super().__init__(
            "Configuración IA",
            "BIMNEMO necesita un modelo de IA para entender tus documentos. "
            "Aquí se elige cuál y se pega la clave.",
        )
        self.motor = motor

        self.aviso = Aviso()
        self.anadir(self.aviso)

        self.secciones: dict[str, Seccion] = {}
        for clave, titulo, explicacion in SECCIONES:
            self.secciones[clave] = Seccion(clave, titulo, explicacion)

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

        if datos.get("restart_required"):
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

    def _guardar(self) -> None:
        cuerpo: dict[str, Any] = {
            clave: seccion.a_peticion() for clave, seccion in self.secciones.items()
        }
        cuerpo["language"] = str(self.idioma.currentData() or "")

        self.boton_guardar.setEnabled(False)
        self.estado.informar("Guardando…")
        self.motor.post("/bimnemo/settings", cuerpo, self._guardado, self._no_guardo)

    def _guardado(self, _datos: Any) -> None:
        self.boton_guardar.setEnabled(True)
        self.estado.acertar("Guardado. Reinicia el motor para que empiece a usarlo.")
        self.refrescar()

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
        if bien:
            self.estado.acertar("El motor ha vuelto con la configuración nueva.")
            self.refrescar()
        else:
            self.estado.fallar(motivo)
