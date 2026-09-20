"""Instancias de LightRAG por NEMO: creación perezosa, reutilización y desalojo.

Una NEMO en uso necesita su propia instancia de ``LightRAG``, con su
``workspace``. Este módulo las administra.

## Por qué varias instancias conviven en un proceso

Está previsto por el motor, no es un apaño. El núcleo está parametrizado por
workspace de arriba abajo — ``get_final_namespace()`` prefija cada namespace,
y ``initialize_pipeline_status``, ``get_pipeline_ingress`` y
``get_namespace_data`` reciben el workspace explícito. En
``lightrag.py::initialize_storages`` solo la PRIMERA instancia fija el
workspace por defecto del proceso; las siguientes registran un aviso cuyo
texto contempla justo este caso. Y ``tests/workspace/`` prueba que dos
workspaces corren en paralelo sin contaminarse.

**Regla que sostiene lo anterior:** aquí se pasa SIEMPRE el workspace
explícito. Apoyarse en el valor por defecto del proceso funcionaría con una
NEMO y daría datos de otra en cuanto hubiera dos.

## Por qué perezosas y con tope

Con almacenes de fichero —los que trae LightRAG por defecto— cada instancia
carga en memoria su grafo y sus vectores. Treinta NEMOs abiertas a la vez son
treinta grafos en RAM. Por eso una NEMO no crea nada hasta que se usa, y por
eso hay un tope de instancias vivas con desalojo de la menos usada.

El desalojo **cierra** la instancia (``finalize_storages``), que es lo que
vuelca a disco lo pendiente. Soltar la referencia sin cerrar dejaría escrituras
sin publicar.

Si se prevén decenas de NEMOs, la respuesta de verdad no es subir el tope: es
PostgreSQL, donde un workspace es un filtro de columna y no una copia en
memoria.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from lightrag.utils import logger

#: Cuántas instancias se mantienen vivas a la vez. Cuatro cubre el uso real
#: —se trabaja con una y se consulta alguna más— sin que la memoria se
#: dispare. Configurable por si el despliegue usa backends de servidor.
DEFAULT_MAX_LIVE = 4

#: Fábrica de instancias: recibe el workspace y devuelve una LightRAG YA
#: construida pero SIN inicializar. La construye quien sabe hacerlo — el
#: servidor, que tiene toda la configuración de modelos — y no este módulo:
#: duplicar aquí esas cien líneas garantizaría que las dos versiones se
#: separasen con el tiempo.
Factory = Callable[[str], Any]


@dataclass
class _Entry:
    instance: Any
    initialized: bool = False


@dataclass
class NemoManager:
    """Administra las instancias de LightRAG de cada NEMO.

    Args:
        factory: construye una ``LightRAG`` para un workspace dado.
        max_live: tope de instancias abiertas a la vez.
    """

    factory: Factory
    max_live: int = DEFAULT_MAX_LIVE

    # OrderedDict como LRU: el último en usarse va al final.
    _entries: "OrderedDict[str, _Entry]" = field(
        default_factory=OrderedDict, init=False
    )
    # Un cerrojo por NEMO. Sin esto, dos peticiones simultáneas sobre una NEMO
    # todavía sin abrir construirían DOS instancias del mismo workspace, y las
    # dos escribirían los mismos ficheros.
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict, init=False)
    _guard: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _closed: bool = field(default=False, init=False)
    # NEMOs que este gestor NO abrió y por tanto NO cierra. La instancia por
    # defecto la construye e inicializa el servidor, y su `lifespan` la
    # finaliza al apagar. Si el gestor la desalojara, los routers que la
    # tienen por referencia directa seguirían usando almacenes ya cerrados.
    _pinned: set[str] = field(default_factory=set, init=False)

    # -- Acceso ------------------------------------------------------------

    def adopt(self, nemo_id: str, instance: Any, *, pinned: bool = False) -> None:
        """Registra una instancia **ya inicializada** que construyó otro.

        Evita el caso absurdo de que el servidor cree la instancia por
        defecto, la inicialice, y el gestor construya una segunda para el
        mismo workspace: dos objetos escribiendo los mismos ficheros.

        Con ``pinned``, el gestor la sirve pero nunca la desaloja ni la
        cierra: su ciclo de vida sigue siendo de quien la creó.
        """
        self._entries[nemo_id] = _Entry(instance=instance, initialized=True)
        self._entries.move_to_end(nemo_id)
        if pinned:
            self._pinned.add(nemo_id)

    def _lock_for(self, nemo_id: str) -> asyncio.Lock:
        lock = self._locks.get(nemo_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[nemo_id] = lock
        return lock

    async def get(self, nemo_id: str) -> Any:
        """Instancia lista para usar de esa NEMO, creándola si hace falta."""
        if self._closed:
            raise RuntimeError("El gestor de NEMOs ya está cerrado.")

        async with self._lock_for(nemo_id):
            entry = self._entries.get(nemo_id)
            if entry is not None and entry.initialized:
                self._entries.move_to_end(nemo_id)
                return entry.instance

            if entry is None:
                logger.info("BIMNEMO: abriendo la NEMO %r", nemo_id or "(base)")
                entry = _Entry(instance=self.factory(nemo_id))
                self._entries[nemo_id] = entry

            if not entry.initialized:
                await entry.instance.initialize_storages()
                entry.initialized = True

            self._entries.move_to_end(nemo_id)

        # El desalojo va FUERA del cerrojo de esta NEMO: cierra otras, y
        # hacerlo dentro encadenaría cerrojos en orden variable — la receta
        # clásica del interbloqueo.
        await self._evict_if_needed(keep=nemo_id)
        return self._entries[nemo_id].instance

    def peek(self, nemo_id: str) -> Any | None:
        """La instancia si ya está abierta, sin abrir nada.

        Para lo que solo tiene sentido con lo que ya está en marcha, como
        informar del estado, sin pagar el coste de abrir una NEMO dormida.
        """
        entry = self._entries.get(nemo_id)
        return entry.instance if entry and entry.initialized else None

    def live_ids(self) -> list[str]:
        """NEMOs abiertas ahora mismo, de la menos usada a la más reciente."""
        return [k for k, v in self._entries.items() if v.initialized]

    # -- Desalojo y cierre -------------------------------------------------

    async def _evict_if_needed(self, keep: str) -> None:
        # Las fijadas no cuentan para el tope: no son nuestras y no se van a
        # cerrar, así que incluirlas en la cuenta solo desalojaría de más.
        while len(self._entries) - len(self._pinned) > self.max_live:
            victim_id = next(
                (k for k in self._entries if k != keep and k not in self._pinned),
                None,
            )
            if victim_id is None:
                return
            await self._close_one(victim_id, reason="desalojo por tope de memoria")

    async def _close_one(self, nemo_id: str, *, reason: str) -> None:
        async with self._lock_for(nemo_id):
            if nemo_id in self._pinned:
                # Se suelta la referencia pero NO se cierra: la finaliza quien
                # la creó. Cerrarla aquí dejaría a los routers que la usan por
                # referencia directa hablando con almacenes cerrados.
                self._entries.pop(nemo_id, None)
                self._pinned.discard(nemo_id)
                return

            entry = self._entries.pop(nemo_id, None)
            if entry is None:
                return
            logger.info(
                "BIMNEMO: cerrando la NEMO %r (%s)", nemo_id or "(base)", reason
            )
            if entry.initialized:
                try:
                    await entry.instance.finalize_storages()
                except Exception as exc:
                    # Cerrar mal es malo; dejar de cerrar las demás, peor.
                    logger.warning(
                        "BIMNEMO: fallo al cerrar la NEMO %r: %s", nemo_id, exc
                    )

    async def close(self, nemo_id: str) -> None:
        """Cierra una NEMO concreta. La próxima petición la abrirá de nuevo.

        Lo usa el borrado: hay que soltar los ficheros antes de tocar la
        carpeta, o Windows se niega a borrarlos.
        """
        await self._close_one(nemo_id, reason="cierre solicitado")

    async def close_all(self) -> None:
        """Cierra todas. Se llama al apagar el servidor."""
        self._closed = True
        for nemo_id in list(self._entries):
            await self._close_one(nemo_id, reason="apagado")

    # -- Difusión ----------------------------------------------------------

    async def map(
        self,
        nemo_ids: list[str],
        action: Callable[[str, Any], Awaitable[Any]],
    ) -> dict[str, Any]:
        """Ejecuta ``action`` sobre varias NEMOs y devuelve lo que dé cada una.

        Es lo que sostiene «buscar en todas»: la recuperación de cada NEMO es
        independiente, así que se lanzan a la vez. El resultado es un
        diccionario por NEMO, y **el fallo de una no tumba al resto**: llega
        como excepción en su hueco. Una memoria rota no debe dejar sin
        respuesta a las otras cinco.

        Ojo con el tope de instancias vivas: pedir a más NEMOs de las que caben
        provoca desalojos en cadena. Quien llame con muchas debería subir
        ``max_live`` o trocear la lista.
        """

        async def _one(nemo_id: str) -> Any:
            instance = await self.get(nemo_id)
            return await action(nemo_id, instance)

        results = await asyncio.gather(
            *(_one(n) for n in nemo_ids), return_exceptions=True
        )
        return dict(zip(nemo_ids, results))


__all__ = ["DEFAULT_MAX_LIVE", "Factory", "NemoManager"]
