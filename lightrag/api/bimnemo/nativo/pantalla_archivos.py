"""Pantalla «Archivos»: subir documentos, ver por dónde van y borrarlos.

Las mismas ocho columnas y los mismos rótulos que la interfaz web, porque son
el mismo producto: un fichero que allí sale como «4.9 MB · En memoria» y aquí
como «5013504 · processed» convierte una aplicación en dos.

## Cómo se reparte el trabajo

Aquí vive **qué** se enseña y qué pasa al pulsar: la memoria abierta, el
filtro, lo que se está subiendo, y las llamadas al motor. El dibujo de la
tabla está en ``archivos_tabla`` y las barras de avance en
``archivos_avance``; juntos pasaban de las novecientas líneas.

## El estado va en su columna, no en una barra aparte

Cada fichero tiene su propio estado —uno subiendo, otro en cola, otro ya en
memoria— y una barra global no puede contar eso. La columna **Estado** de
cada fila es la que cambia, y la barra de avance vive dentro de esa celda: es
donde el usuario ya está mirando cuando se pregunta si aquello sigue vivo.

## Por qué se sondea, y qué se sondea

El motor no empuja nada: hay que preguntarle. Se pregunta por `/bimnemo/
progress`, que es barato y trae un sello (`revision`); **la lista completa
solo se vuelve a pedir cuando ese sello cambia**. Repintar la tabla entera
cada dos segundos le quitaría el ratón de encima a quien está a punto de
pulsar un botón, y pedir el listado en cada latido es recorrer el disco para
enterarse de que no ha pasado nada.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from lightrag.api.bimnemo.nativo import formato, iconos
from lightrag.api.bimnemo.nativo.archivos_avance import Barras
from lightrag.api.bimnemo.nativo.archivos_nombres import GuardianNombres
from lightrag.api.bimnemo.nativo.archivos_piezas import Filtros, ZonaSoltar
from lightrag.api.bimnemo.nativo.archivos_tabla import (
    ACCIONES,
    ARCHIVO,
    CATEGORIA,
    COLUMNAS,
    ESTADO,
    FRAGMENTOS,
    MODIFICADO,
    TAMANO,
    TIPO,
    Acciones,
    TablaArchivos,
    estado_de,
)
from lightrag.api.bimnemo.nativo.consumo import TarjetaConsumo
from lightrag.api.bimnemo.nativo.motor import Motor
from lightrag.api.bimnemo.nativo.piezas import Aviso, Pantalla, Tarjeta

#: Cada cuánto se mira el avance: mientras hay trabajo, y en reposo.
CADENCIA_ACTIVA = 2000
CADENCIA_REPOSO = 6000

#: Las columnas se vuelven a exportar desde aquí aunque vivan en
#: ``archivos_tabla``: quien habla de la pantalla de Archivos —la ventana,
#: las pruebas— pregunta por ella, no por el fichero donde acabó el dibujo.
__all__ = ["CADENCIA_ACTIVA", "CADENCIA_REPOSO", "COLUMNAS", "PantallaArchivos"]


class PantallaArchivos(Pantalla):
    #: Cuántos ficheros hay en esta memoria. Lo escucha la ventana para el
    #: contador del carril; se emite solo cuando el número cambia, que es
    #: mucho menos que cada repintado.
    cuenta = Signal(int)

    def __init__(self, motor: Motor) -> None:
        super().__init__(
            "Archivos",
            "Sube documentos y míralos entrar en la memoria.",
        )
        self.motor = motor

        #: Lo que se está subiendo ahora, por nombre: el porcentaje manda
        #: sobre el estado que diga el motor, porque el motor todavía no
        #: sabe que ese fichero existe.
        self._subiendo: dict[str, int] = {}
        #: Los que están borrándose. El servidor responde en cuanto lanza el
        #: trabajo, no cuando termina: sin esta marca la fila se quedaría
        #: intacta fingiendo que no pasa nada.
        self._borrandose: set[str] = set()

        self._catalogo: list[dict[str, Any]] = []
        self._extensiones: list[str] = []
        self._memoria = ""
        self._filas: list[dict[str, Any]] = []

        self._sello: Optional[str] = None
        self._ultima_cuenta: Optional[int] = None
        #: Si el motor ya ha contestado alguna vez. Hasta entonces no hay
        #: «cero archivos»: hay «todavía no se sabe», y son cosas distintas.
        self._recibido = False
        #: Las barras vivas de la tabla y el último avance del motor.
        self.barras = Barras()
        #: Qué nombre cabe en la memoria abierta, y el aviso si no.
        self.nombres = GuardianNombres(
            motor,
            self,
            lambda: frozenset(str(f.get("name") or "") for f in self._filas),
        )
        self.nombres.cargar()

        self.aviso = Aviso()
        self.anadir(self.aviso)
        self.anadir(self._acciones())
        self.anadir(self._zona())
        # Debajo de la zona de arrastre: subir es lo que dispara el gasto.
        self.consumo = TarjetaConsumo(motor)
        self.anadir(self.consumo)
        self.anadir(self._almacenados())
        self.cerrar_con_espacio()

        # Soltar vale en cualquier parte de la pantalla, no solo dentro del
        # recuadro: quien arrastra un fichero apunta a la ventana.
        self.setAcceptDrops(True)

        self._vigilante = QTimer(self)
        self._vigilante.setInterval(CADENCIA_REPOSO)
        self._vigilante.timeout.connect(self._mirar)
        self._vigilante.start()

        self._cargar_catalogo()
        self.refrescar()
        self._mirar()

    # -- estructura ---------------------------------------------------------

    def _acciones(self) -> QWidget:
        """Los dos botones de la cabecera.

        No hay «Actualizar»: el vigilante mira cada dos o seis segundos y
        vuelve a pedir la lista en cuanto el sello del motor cambia. Un botón
        que solo puede adelantar unos segundos lo que va a pasar solo invita
        a pulsarlo cuando algo parece atascado —y ahí no arregla nada.
        """
        fila = QWidget()
        fila.setObjectName("fila")
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)
        caja.addStretch(1)

        self.boton_reindexar = QPushButton("Reindexar pendientes")
        iconos.poner(self.boton_reindexar, "recargar", 14)
        self.boton_reindexar.setCursor(Qt.PointingHandCursor)
        self.boton_reindexar.setToolTip(
            "Busca en la carpeta de entrada lo que todavía no está en la "
            "memoria y lo encola."
        )
        self.boton_reindexar.clicked.connect(self._reindexar)
        caja.addWidget(self.boton_reindexar)

        subir = QPushButton("Subir archivos")
        subir.setObjectName("principal")
        iconos.poner(subir, "subir", 15, "sobre_azul")
        subir.setCursor(Qt.PointingHandCursor)
        subir.clicked.connect(self._elegir)
        caja.addWidget(subir)
        return fila

    def _zona(self) -> QWidget:
        self.zona = ZonaSoltar()
        self.zona.soltados.connect(self._subir_varios)
        self.zona.pulsada.connect(self._elegir)
        return self.zona

    def _almacenados(self) -> QWidget:
        tarjeta = Tarjeta()

        cabecera = QWidget()
        cabecera.setObjectName("fila")
        caja = QHBoxLayout(cabecera)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)

        titulo = QLabel("Almacenados")
        titulo.setObjectName("subtitulo")
        caja.addWidget(titulo)
        caja.addStretch(1)

        self.pista = QLabel("…")
        self.pista.setObjectName("pista")
        caja.addWidget(self.pista)
        tarjeta.anadir(cabecera)

        self.filtros = Filtros()
        self.filtros.elegida.connect(lambda _clave: self._repintar())
        tarjeta.anadir(self.filtros)

        # La tabla dibuja; lo que hacen sus botones sigue viviendo aquí, que
        # es donde están los avisos y el refresco que tocan.
        self.tabla = TablaArchivos(
            self.barras,
            Acciones(
                pausar=self._pausar,
                reintentar=self._reintentar,
                renombrar=self._renombrar,
                borrar=self._confirmar_borrado,
                no_cabe=lambda nombre: self.nombres.no_cabe(nombre),
            ),
        )
        tarjeta.anadir(self.tabla)

        # El hueco. Una tabla vacía sin explicación se lee como un fallo de
        # carga; esto dice si es que no hay nada o si es el filtro.
        self.vacio = QLabel("")
        self.vacio.setObjectName("descripcion")
        self.vacio.setAlignment(Qt.AlignCenter)
        self.vacio.setWordWrap(True)
        self.vacio.hide()
        tarjeta.anadir(self.vacio)
        return tarjeta

    # -- datos --------------------------------------------------------------

    def _cargar_catalogo(self) -> None:
        """Qué categorías hay y qué formatos admite el motor ahora mismo."""

        def llego(datos: Any) -> None:
            if not isinstance(datos, dict):
                return
            self._catalogo = list(datos.get("categories") or [])
            self._extensiones = [
                str(e) for e in (datos.get("ingestible_extensions") or [])
            ]
            self.zona.formatos(self._extensiones)
            self._repintar()

        def no_pudo(motivo: str) -> None:
            self.zona.no_se_pudo(
                f"No se pudo preguntar al motor qué formatos admite: {motivo}"
            )

        self.motor.get("/bimnemo/catalog", llego, no_pudo)

    def retematizar(self) -> None:
        """Las insignias de la tabla llevan su color escrito en el widget.

        Los iconos los repasa la ventana; esto es para lo que se pinta con
        un estilo propio por fila, que no lo alcanza ninguna hoja.
        """
        self._repintar()

    def filtrar(self, categoria: str) -> None:
        """Deja la tabla en una categoría. La pulsa alguien en el panel."""
        self.filtros.elegir(categoria)

    def poner_memoria(self, nombre: str) -> None:
        """El nombre de la memoria abierta, para la pista de la cabecera.

        Lo inyecta la ventana en vez de pedirlo aquí: quién está abierta lo
        sabe la barra superior, y dos sitios preguntándolo se contradicen en
        cuanto uno se entera del cambio antes que el otro.
        """
        self._memoria = nombre
        # Cuánto cabe depende de la memoria: su carpeta es parte de la ruta.
        self.nombres.cargar()
        self._repintar()

    def refrescar(self) -> None:
        self.motor.get("/bimnemo/files", self._recibir, self._fallo)

    def _recibir(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        self.aviso.callar()
        self._recibido = True
        self._filas = list(datos.get("files") or [])

        # Un borrado termina con la fila desapareciendo, así que la marca
        # deja de tener a quién describir. Sin esto, subir otro archivo con
        # el mismo nombre lo pintaría «Borrando…» nada más llegar.
        vivos = {str(f.get("name") or "") for f in self._filas}
        self._borrandose &= vivos

        if datos.get("scan_error"):
            self.aviso.fallar(str(datos["scan_error"]))
        self._repintar()

    def _fallo(self, motivo: str) -> None:
        self.aviso.fallar(motivo)

    # -- pintado ------------------------------------------------------------

    def _subiendo_fuera(self) -> list[dict[str, Any]]:
        """Los que se están subiendo y el motor todavía no conoce.

        Se pintan delante de todo y **no se filtran**: su categoría aún no
        se sabe, y esconder un fichero justo mientras sube es lo contrario
        de lo que hace falta.
        """
        return [
            {"name": nombre, "type": "", "size_bytes": None, "status": ""}
            for nombre in self._subiendo
            if not any(f.get("name") == nombre for f in self._filas)
        ]

    def _filas_visibles(self) -> list[dict[str, Any]]:
        activa = self.filtros.activa
        del_motor = (
            self._filas
            if not activa
            else [f for f in self._filas if f.get("category") == activa]
        )
        return self._subiendo_fuera() + del_motor

    def _repintar(self) -> None:
        self.filtros.poner(self._filas, self._catalogo)
        visibles = self._filas_visibles()
        total = len(self._filas) + len(self._subiendo_fuera())

        pista = f"{formato.numero(len(visibles))} de {formato.numero(total)}"
        self.pista.setText(f"{self._memoria} · {pista}" if self._memoria else pista)

        if self._recibido and total != self._ultima_cuenta:
            self._ultima_cuenta = total
            self.cuenta.emit(total)

        self.tabla.pintar(visibles, self._catalogo, self._subiendo, self._borrandose)
        self._decir_si_esta_vacio(len(visibles), total)

    def _decir_si_esta_vacio(self, visibles: int, total: int) -> None:
        if visibles:
            self.vacio.hide()
            self.tabla.show()
            return
        self.tabla.hide()
        self.vacio.setText(
            "Nada en esta categoría. Prueba con otro filtro."
            if total
            else "Todavía no hay archivos. Arrastra documentos a la zona de "
            "arriba y entrarán en la memoria."
        )
        self.vacio.show()

    # -- vigilancia ---------------------------------------------------------

    def _mirar(self) -> None:
        """Una petición barata que sirve para dos cosas: avance y frescura."""
        self.motor.get("/bimnemo/progress", self._avance_llego, None)

    def _avance_llego(self, datos: Any) -> None:
        if not isinstance(datos, dict):
            return
        activo = self.barras.recordar(datos)
        self._cadencia(CADENCIA_ACTIVA if activo else CADENCIA_REPOSO)

        sello = str(datos.get("revision") or "")
        cambio = bool(sello) and self._sello is not None and sello != self._sello
        if sello:
            self._sello = sello

        # La lista solo se vuelve a pedir cuando algo cambió de verdad. El
        # primer sondeo únicamente toma la referencia.
        if cambio:
            self.refrescar()
        elif activo or self._borrandose:
            # Borrar no cambia el sello hasta que termina, y purgar el grafo
            # lleva segundos: la barra de esa fila tiene que seguir viva.
            self._repintar_barras()

    def _repintar_barras(self) -> None:
        """Mueve las barras que ya están puestas, sin rehacer la tabla."""
        for archivo in self._filas_visibles():
            nombre = str(archivo.get("name") or "")
            if not self.barras.tiene(nombre):
                continue
            estado = estado_de(archivo, nombre, self._subiendo, self._borrandose)
            self.barras.pintar(
                nombre,
                str(archivo.get("doc_id") or ""),
                estado,
                self._subiendo.get(nombre, 0) if estado == "subiendo" else None,
            )

    def _cadencia(self, ms: int) -> None:
        if self._vigilante.interval() != ms:
            self._vigilante.setInterval(ms)

    # -- subir --------------------------------------------------------------

    def _filtro(self) -> str:
        """El filtro del diálogo, con lo que el motor admite de verdad.

        Sin esto se puede elegir un `.exe` que el motor rechazará después:
        el error llega tarde y parece un fallo del programa.
        """
        if not self._extensiones:
            return "Todos los archivos (*.*)"
        patrones = " ".join(f"*.{e}" for e in self._extensiones)
        return f"Documentos admitidos ({patrones});;Todos los archivos (*.*)"

    def _elegir(self) -> None:
        rutas, _filtro = QFileDialog.getOpenFileNames(
            self, "Elige los documentos", "", self._filtro()
        )
        self._subir_varios(rutas)

    def _subir_varios(self, rutas: list[str]) -> None:
        # Los que no caben pasan antes por el aviso de nombre largo.
        for ruta, nombre in self.nombres.preparar(rutas):
            self._subir(ruta, nombre)

    def dragEnterEvent(self, evento: QDragEnterEvent) -> None:  # noqa: N802
        if evento.mimeData().hasUrls():
            evento.acceptProposedAction()

    def dropEvent(self, evento: QDropEvent) -> None:  # noqa: N802
        self._subir_varios(
            [u.toLocalFile() for u in evento.mimeData().urls() if u.isLocalFile()]
        )
        evento.acceptProposedAction()

    def _subir(self, ruta: str, nombre: Optional[str] = None) -> None:
        nombre = nombre or Path(ruta).name
        self._subiendo[nombre] = 0
        self._repintar()

        def avanzar(hecho: int, total: int) -> None:
            if total <= 0:
                return
            self._subiendo[nombre] = int(hecho * 100 / total)
            # Se mueve la barra de esa fila y se deja la tabla en paz: pedir
            # el listado entero en cada trozo enviado es recorrer el disco
            # cincuenta veces por fichero.
            if self.barras.tiene(nombre):
                self.barras.pintar(nombre, "", "subiendo", self._subiendo[nombre])
            else:
                self._repintar()

        def acabo(_datos: Any) -> None:
            self._subiendo.pop(nombre, None)
            # Recién subido, el motor tarda un momento en encolarlo; el
            # vigilante se encarga de enseñarlo cuando aparezca.
            self._cadencia(CADENCIA_ACTIVA)
            self.refrescar()

        def no_pudo(motivo: str) -> None:
            self._subiendo.pop(nombre, None)
            self.aviso.fallar(f"{nombre}: {motivo}")
            self._repintar()

        if nombre == Path(ruta).name:
            self.motor.subir("/documents/upload", ruta, acabo, no_pudo, avanzar)
        else:
            self.motor.subir(
                "/documents/upload", ruta, acabo, no_pudo, avanzar, nombre=nombre
            )

    # -- reindexar y reintentar ---------------------------------------------

    def _reindexar(self) -> None:
        """Encola lo que está en la carpeta pero no en la memoria."""
        self.boton_reindexar.setEnabled(False)
        self.aviso.informar("Buscando documentos sin indexar…")

        def hecho(_datos: Any) -> None:
            self.boton_reindexar.setEnabled(True)
            self.aviso.acertar("Reindexado en marcha.")
            self._cadencia(CADENCIA_ACTIVA)
            self.refrescar()

        def no_pudo(motivo: str) -> None:
            self.boton_reindexar.setEnabled(True)
            self.aviso.fallar(f"No se pudo reindexar: {motivo}")

        self.motor.post("/documents/scan", {}, hecho, no_pudo)

    def _reintentar(self, doc_id: str) -> None:
        self.aviso.informar("Reencolando el documento…")

        def hecho(datos: Any) -> None:
            datos = datos if isinstance(datos, dict) else {}
            mensaje = str(datos.get("message") or "")
            if datos.get("status") == "waiting":
                # Apuntado: la fila pasa a «En espera».
                self.aviso.informar(mensaje)
                self.refrescar()
                return
            if datos.get("status") in ("busy", "nothing"):
                # No es un fallo, pero tampoco se ha hecho nada: no se pinta
                # en verde.
                self.aviso.informar(mensaje)
                return
            self.aviso.acertar(mensaje or "El documento vuelve a la cola.")
            self._cadencia(CADENCIA_ACTIVA)
            self.refrescar()

        self.motor.post(
            f"/bimnemo/documents/retry?doc_id={quote(doc_id, safe='')}",
            {},
            hecho,
            self._fallo,
        )

    def _renombrar(self, nombre: str) -> None:
        def hecho(datos: Any) -> None:
            datos = datos if isinstance(datos, dict) else {}
            mensaje = str(datos.get("message") or "Renombrado.")
            if datos.get("status") == "waiting":
                self.aviso.informar(mensaje)
                self.refrescar()
                return
            self.aviso.acertar(mensaje)
            self._cadencia(CADENCIA_ACTIVA)
            self.refrescar()

        self.nombres.renombrar(nombre, hecho, self._fallo)

    def _pausar(self) -> None:
        self.aviso.informar("Pausando la indexación…")

        def hecho(datos: Any) -> None:
            datos = datos if isinstance(datos, dict) else {}
            self.aviso.informar(str(datos.get("message") or "Pausando."))
            self._cadencia(CADENCIA_ACTIVA)

        self.motor.post("/bimnemo/documents/pause", {}, hecho, self._fallo)

    # -- borrar -------------------------------------------------------------

    def _confirmar_borrado(self, archivo: dict[str, Any]) -> None:
        nombre = str(archivo.get("name") or "")
        doc_id = archivo.get("doc_id")

        aviso = (
            f"Se borrará «{nombre}» y todo lo que el motor aprendió de él: "
            "sus trozos, sus entidades y sus relaciones."
            if doc_id
            else f"Se borrará el fichero «{nombre}», que todavía no está indexado."
        )
        respuesta = QMessageBox.question(
            self,
            "Borrar archivo",
            aviso + "\n\nEsto no se puede deshacer. ¿Seguir?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if respuesta != QMessageBox.Yes:
            return

        # La fila lo dice desde ya: el servidor contesta cuando lanza el
        # trabajo, no cuando termina, y purgar un documento lleva segundos.
        self._borrandose.add(nombre)
        self.aviso.informar(f"Borrando «{nombre}»…")
        # Mientras purga, el motor publica cuántas entidades y relaciones
        # lleva: se mira seguido para que esa barra se mueva de verdad.
        self._cadencia(CADENCIA_ACTIVA)
        self._repintar()

        def hecho(_datos: Any) -> None:
            self.aviso.acertar(f"Borrado «{nombre}».")
            self._cadencia(CADENCIA_ACTIVA)
            self.refrescar()

        def no_pudo(motivo: str) -> None:
            self._borrandose.discard(nombre)
            self.aviso.fallar(motivo)
            self._repintar()

        if doc_id:
            self.motor.borrar(
                "/bimnemo/documents",
                {"doc_ids": [doc_id], "delete_file": True},
                hecho,
                no_pudo,
            )
        else:
            self.motor.borrar(
                f"/bimnemo/files?name={quote(nombre)}", {}, hecho, no_pudo
            )
