"""Las memorias (NEMOs): cuál está abierta, y crear, renombrar o borrar.

Es el `nemo.js` de la web, con sus tres diálogos. Las reglas son las mismas
porque los errores que evitan son los mismos:

- La memoria elegida **se recuerda entre sesiones, pero no se cree a ciegas**:
  si la guardada ya no existe —la borró otro, o es otro equipo— se vuelve a
  la de por defecto. Insistir en una memoria fantasma deja todas las
  pantallas enseñando errores.
- **Borrar exige escribir el nombre exacto.** Es la única operación
  irreversible de la aplicación; un «¿seguro?» se contesta que sí sin leerlo.
- **Renombrar no lo exige**, y eso también es deliberado: pedir confirmación
  escrita para algo reversible enseña a confirmar sin leer, y entonces la del
  borrado deja de servir.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lightrag.api.bimnemo.nativo import iconos, tema
from lightrag.api.bimnemo.nativo.motor import Motor

#: Lo que acepta el registro. Enterarse al pulsar «Guardar» es tarde.
MAXIMO = 60


def ajustes() -> QSettings:
    """Donde la ventana recuerda sus preferencias entre sesiones.

    Es el equivalente del `localStorage` de la web. En Windows va al
    registro, bajo el nombre de la organización y el producto.
    """
    return QSettings("CM Educativa", "BIMNEMO")


class Memorias(QObject):
    """Qué memorias hay y cuál está abierta.

    No dibuja nada: la barra le pregunta y le pide cosas. Quien cambia la
    memoria activa **no** avisa a cada pantalla, sino que se lo dice al motor
    —que es quien enruta— y emite `cambiada` para que la ventana repinte.
    """

    #: La lista o la memoria por defecto han cambiado.
    listado = Signal()
    #: Se ha abierto otra memoria. Lleva su identificador.
    cambiada = Signal(str)

    def __init__(self, motor: Motor, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.motor = motor
        self._nemos: list[dict[str, Any]] = []
        self._por_defecto = ""
        self._actual = ""

    # -- estado -------------------------------------------------------------

    @property
    def nemos(self) -> list[dict[str, Any]]:
        return self._nemos

    @property
    def por_defecto(self) -> str:
        return self._por_defecto

    @property
    def actual(self) -> str:
        return self._actual

    def ficha(self, nemo_id: Optional[str] = None) -> dict[str, Any]:
        """Los datos de una memoria. Vacío si no está en la lista."""
        buscada = self._actual if nemo_id is None else nemo_id
        for nemo in self._nemos:
            if str(nemo.get("id", "")) == buscada:
                return nemo
        return {}

    def nombre(self, nemo_id: Optional[str] = None) -> str:
        return str(self.ficha(nemo_id).get("name") or "—")

    # -- carga --------------------------------------------------------------

    def cargar(self, luego: Optional[Callable[[], None]] = None) -> None:
        """Pide la lista y decide cuál queda abierta."""

        def llego(datos: Any) -> None:
            if not isinstance(datos, dict):
                return
            self._nemos = list(datos.get("nemos") or [])
            self._por_defecto = str(datos.get("default") or "")

            existe = {str(n.get("id", "")) for n in self._nemos}
            guardada = ajustes().value("memoria", None)

            # El orden importa: lo recordado solo vale si sigue existiendo.
            if guardada is not None and str(guardada) in existe:
                elegida = str(guardada)
            elif self._actual in existe:
                elegida = self._actual
            else:
                elegida = self._por_defecto

            cambio = elegida != self._actual
            self._actual = elegida
            self.motor.usar_memoria(elegida)

            self.listado.emit()
            if cambio:
                self.cambiada.emit(elegida)
            if luego is not None:
                luego()

        self.motor.get("/bimnemo/nemos", llego, None)

    def elegir(self, nemo_id: str) -> None:
        if nemo_id == self._actual:
            return
        self._actual = nemo_id
        self.motor.usar_memoria(nemo_id)
        ajustes().setValue("memoria", nemo_id)
        self.listado.emit()
        self.cambiada.emit(nemo_id)

    # -- acciones -----------------------------------------------------------

    def crear(self, padre: QWidget) -> None:
        dialogo = DialogoCrear(self.motor, padre)
        if dialogo.exec() == QDialog.Accepted and dialogo.creada:
            # Se recarga y se salta a la nueva: quien crea una memoria la
            # crea para usarla ahora.
            self.cargar(lambda: self.elegir(dialogo.creada))

    def renombrar(self, padre: QWidget) -> None:
        ficha = self.ficha()
        if not ficha:
            return
        dialogo = DialogoRenombrar(
            self.motor, ficha, self._actual == self._por_defecto, padre
        )
        if dialogo.exec() == QDialog.Accepted:
            # Renombrar no cambia el identificador: la memoria abierta sigue
            # siendo la misma y solo hay que repintar el rótulo.
            self.cargar()

    def borrar(self, padre: QWidget) -> None:
        ficha = self.ficha()
        if not ficha:
            return
        dialogo = DialogoBorrar(self.motor, ficha, padre)
        if dialogo.exec() == QDialog.Accepted and dialogo.borrada:
            self.cargar(lambda: self.elegir(self._por_defecto))


# --- Diálogos ---------------------------------------------------------------


class _Dialogo(QDialog):
    """Lo común de los tres: título con icono, cuerpo y botonera."""

    def __init__(self, titulo: str, icono: str, padre: Optional[QWidget]) -> None:
        super().__init__(padre)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setStyleSheet(tema.hoja(tema.ACTUAL))

        self.columna = QVBoxLayout(self)
        self.columna.setContentsMargins(24, 22, 24, 20)
        self.columna.setSpacing(12)

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(8)

        marca = QLabel()
        iconos.poner(marca, icono, 16)
        caja.addWidget(marca)

        rotulo = QLabel(titulo)
        rotulo.setObjectName("subtitulo")
        caja.addWidget(rotulo)
        caja.addStretch(1)
        self.columna.addWidget(fila)

        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)

    def parrafo(self, texto: str, objeto: str = "descripcion") -> QLabel:
        etiqueta = QLabel(texto)
        etiqueta.setObjectName(objeto)
        etiqueta.setWordWrap(True)
        self.columna.addWidget(etiqueta)
        return etiqueta

    def botonera(
        self, cancelar: str, aceptar: str, peligro: bool = False
    ) -> QPushButton:
        self.columna.addWidget(self.error)

        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)
        caja.addStretch(1)

        boton_cancelar = QPushButton(cancelar)
        boton_cancelar.setCursor(Qt.PointingHandCursor)
        boton_cancelar.clicked.connect(self.reject)
        caja.addWidget(boton_cancelar)

        self.aceptar = QPushButton(aceptar)
        self.aceptar.setObjectName("peligro" if peligro else "principal")
        self.aceptar.setCursor(Qt.PointingHandCursor)
        self.aceptar.setDefault(True)
        caja.addWidget(self.aceptar)

        self.columna.addWidget(fila)
        return self.aceptar

    def fallar(self, motivo: str) -> None:
        self.error.setText(motivo)


class DialogoCrear(_Dialogo):
    """Nueva memoria."""

    def __init__(self, motor: Motor, padre: Optional[QWidget] = None) -> None:
        super().__init__("Nueva memoria", "acercar", padre)
        self.motor = motor
        self.creada = ""

        self.parrafo(
            "Cada memoria indexa y relaciona sus documentos por separado. Lo "
            "que guardes aquí no se mezclará con el resto."
        )
        self.parrafo("Nombre", "rotulo-dialogo")

        self.campo = QLineEdit()
        self.campo.setMaxLength(MAXIMO)
        self.campo.setPlaceholderText("Proyecto Norte")
        self.campo.returnPressed.connect(self._crear)
        self.columna.addWidget(self.campo)

        self.botonera("Cancelar", "Crear memoria").clicked.connect(self._crear)
        self.campo.setFocus()

    def _crear(self) -> None:
        nombre = self.campo.text().strip()
        if not nombre:
            self.fallar("Escribe un nombre para la memoria.")
            return

        self.aceptar.setEnabled(False)

        def hecho(datos: Any) -> None:
            self.creada = (
                str((datos or {}).get("id", "")) if isinstance(datos, dict) else ""
            )
            self.accept()

        def no_pudo(motivo: str) -> None:
            # 409 es el caso habitual —nombre repetido— y el motor ya manda
            # un texto que explica cuál es el choque. Se enseña tal cual.
            self.aceptar.setEnabled(True)
            self.fallar(motivo)

        self.motor.post("/bimnemo/nemos", {"name": nombre}, hecho, no_pudo)


class DialogoRenombrar(_Dialogo):
    """Renombrar, y de paso marcar como memoria por defecto.

    Las dos cosas juntas porque el diálogo ya está abierto y habla de esa
    memoria: `POST /bimnemo/nemos/default` no tenía pantalla ninguna, y es el
    punto `·` que se ve en el selector.
    """

    def __init__(
        self,
        motor: Motor,
        ficha: dict[str, Any],
        es_por_defecto: bool,
        padre: Optional[QWidget] = None,
    ) -> None:
        super().__init__("Renombrar memoria", "editar", padre)
        self.motor = motor
        self.ficha = ficha
        self.era_por_defecto = es_por_defecto

        self.parrafo("Nombre", "rotulo-dialogo")
        self.campo = QLineEdit(str(ficha.get("name") or ""))
        self.campo.setMaxLength(MAXIMO)
        self.campo.textChanged.connect(self._revisar)
        self.campo.returnPressed.connect(self._guardar)
        self.columna.addWidget(self.campo)

        self.cuenta = self.parrafo(f"Hasta {MAXIMO} caracteres", "pista")

        self.casilla = QCheckBox("Usar como memoria por defecto")
        self.casilla.setChecked(es_por_defecto)
        # Ya lo es: quitarle la marca no es una operación que exista, así que
        # la casilla se apaga en vez de ofrecer algo que no se puede hacer.
        self.casilla.setEnabled(not es_por_defecto)
        self.casilla.stateChanged.connect(self._revisar)
        self.columna.addWidget(self.casilla)

        self.parrafo(
            "Cambiar el nombre no mueve nada: tus documentos y lo que el "
            "motor aprendió de ellos se quedan donde están."
        )

        self.botonera("Cancelar", "Guardar").clicked.connect(self._guardar)
        self._revisar()
        # Seleccionado, no solo enfocado: escribir sustituye, una flecha
        # retoca. Renombrar casi siempre es corregir, no empezar de cero.
        self.campo.setFocus()
        self.campo.selectAll()

    def _revisar(self) -> None:
        self.fallar("")
        quedan = MAXIMO - len(self.campo.text())
        self.cuenta.setText(
            f"Quedan {quedan} caracteres"
            if quedan <= 10
            else f"Hasta {MAXIMO} caracteres"
        )
        # Nada que guardar si no cambió ni el nombre ni la casilla: un botón
        # activo que no va a hacer nada es una promesa que no se cumple.
        nombre = self.campo.text().strip()
        cambio_nombre = bool(nombre) and nombre != str(self.ficha.get("name") or "")
        cambio_defecto = self.casilla.isChecked() != self.era_por_defecto
        self.aceptar.setEnabled(cambio_nombre or cambio_defecto)

    def _guardar(self) -> None:
        if not self.aceptar.isEnabled():
            return
        nombre = self.campo.text().strip()
        nemo = str(self.ficha.get("id") or "")
        self.aceptar.setEnabled(False)
        self.aceptar.setText("Guardando…")

        def por_defecto() -> None:
            if not (self.casilla.isChecked() and not self.era_por_defecto):
                self.accept()
                return
            self.motor.post(
                f"/bimnemo/nemos/default?nemo={nemo}",
                {},
                lambda _datos: self.accept(),
                self._solo_el_nombre,
            )

        if nombre and nombre != str(self.ficha.get("name") or ""):
            # El nombre primero: es a lo que vino el usuario. Si la casilla
            # falla después, al menos lo principal quedó hecho.
            self.motor.parchear(
                f"/bimnemo/nemos?nemo={nemo}",
                {"name": nombre},
                lambda _datos: por_defecto(),
                self._no_pudo,
            )
        else:
            por_defecto()

    def _no_pudo(self, motivo: str) -> None:
        self.aceptar.setEnabled(True)
        self.aceptar.setText("Guardar")
        self.fallar(motivo)

    def _solo_el_nombre(self, motivo: str) -> None:
        self.aceptar.setText("Guardar")
        self.fallar(
            f"El nombre se guardó, pero no se pudo marcar por defecto: {motivo}"
        )


class DialogoBorrar(_Dialogo):
    """Borrar una memoria. Exige escribir el nombre exacto.

    La memoria base también se borra, aunque por dentro sea distinto: se
    vacía y se oculta, porque es el espacio de trabajo por defecto del motor
    y no puede desaparecer. Para quien la borra es lo mismo que cualquier
    otra: deja de estar, y si era la última, vuelve el cuadro de la primera
    memoria.
    """

    def __init__(
        self, motor: Motor, ficha: dict[str, Any], padre: Optional[QWidget] = None
    ) -> None:
        nombre = str(ficha.get("name") or "")
        super().__init__(f"Borrar «{nombre}»", "borrar", padre)
        self.motor = motor
        self.ficha = ficha
        self.borrada = False

        aviso = self.parrafo(
            "Se borrarán sus archivos, su índice y su grafo. No se puede "
            "deshacer y no pasa por la papelera."
        )
        aviso.setObjectName("error")
        self.parrafo("Escribe el nombre exacto para confirmarlo", "rotulo-dialogo")

        self.campo = QLineEdit()
        self.campo.setMaxLength(MAXIMO)
        self.campo.textChanged.connect(self._revisar)
        self.campo.returnPressed.connect(self._borrar)
        self.columna.addWidget(self.campo)

        self.botonera(
            "Cancelar", "Borrar definitivamente", peligro=True
        ).clicked.connect(self._borrar)
        self.aceptar.setEnabled(False)
        self.campo.setFocus()

    def _revisar(self) -> None:
        """El botón solo se enciende cuando lo escrito coincide.

        Mejor que dejarlo pulsable y reprochar después: el estado del botón
        dice en todo momento si lo escrito vale, sin tener que intentarlo.
        """
        self.fallar("")
        self.aceptar.setEnabled(
            self.campo.text().strip() == str(self.ficha.get("name") or "")
        )

    def _borrar(self) -> None:
        if not self.aceptar.isEnabled():
            return
        nombre = str(self.ficha.get("name") or "")
        nemo = str(self.ficha.get("id") or "")
        self.aceptar.setEnabled(False)
        self.aceptar.setText("Borrando…")

        def hecho(_datos: Any) -> None:
            self.borrada = True
            self.accept()

        def no_pudo(motivo: str) -> None:
            # El fallo se queda EN el diálogo: cerrarlo y avisar en otro sitio
            # dejaría al usuario sin saber si la memoria sigue ahí.
            self.aceptar.setEnabled(True)
            self.aceptar.setText("Borrar definitivamente")
            self.fallar(f"No se pudo borrar: {motivo}")

        if nemo:
            self.motor.borrar(
                f"/bimnemo/nemos/{nemo}",
                {"confirm_name": nombre, "purge_files": True},
                hecho,
                no_pudo,
            )
            return

        # La base: primero se vacía y después se quita del índice. En ese
        # orden y no en otro: el motor se niega a quitarla con documentos
        # dentro, porque quedarían escondidos y reaparecerían al nombrar la
        # primera memoria. El vaciado es el de siempre del motor, que borra
        # solo lo suyo y respeta las carpetas de las demás memorias.
        def quitar(respuesta: Any) -> None:
            estado = str((respuesta or {}).get("status") or "")
            if estado != "success":
                no_pudo(
                    str((respuesta or {}).get("message") or "")
                    or "el motor no pudo vaciarla"
                )
                return
            self.motor.borrar(
                "/bimnemo/nemos?nemo=", {"confirm_name": nombre}, hecho, no_pudo
            )

        self.motor.borrar(
            "/documents?delete_parsed_files=true&clear_llm_cache=true",
            {},
            quitar,
            no_pudo,
        )


__all__ = [
    "DialogoBorrar",
    "DialogoCrear",
    "DialogoRenombrar",
    "Memorias",
    "ajustes",
]
