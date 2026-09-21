"""Registro de NEMOs: las memorias separadas de BIMNEMO.

Una **NEMO** es una memoria aislada. Por debajo es un ``workspace`` de
LightRAG, que es lo que de verdad separa los datos: el núcleo prefija todos
sus namespaces con él (``kg/shared_storage.py``) y cada backend lo aísla a su
manera — subcarpeta con ficheros, filtro de columna en PostgreSQL, base propia
en Neo4j, partición por payload en Qdrant.

Que sean workspaces y no etiquetas no es un detalle de implementación: LightRAG
**fusiona entidades por nombre**. «Plazo de ejecución» de dos proyectos
distintos sería UN nodo con las dos descripciones mezcladas. Separar al
consultar llega tarde; hay que separar al indexar.

Este módulo solo guarda el índice — qué NEMOs existen y cómo se llaman. Las
instancias de LightRAG las gestiona ``nemo_manager``.

## El nombre visible y el identificador no son lo mismo

El usuario escribe «Proyecto Norte»; eso acaba siendo un nombre de carpeta, así
que el identificador se deriva saneando a ``[A-Za-z0-9_]``. Se guardan los dos:
el nombre para enseñarlo, el identificador para el disco. Renombrar cambia solo
el primero — mover los datos de sitio para cambiar un rótulo es pedir un
desastre.

## Unicidad sin distinguir mayúsculas

``Obra`` y ``obra`` son la MISMA carpeta en Windows y en macOS. Si el registro
los admitiera como dos NEMOs, compartirían datos en silencio, que es
exactamente lo que esto viene a evitar. La unicidad se comprueba en minúsculas.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from lightrag.file_atomic import atomic_write
from lightrag.utils import logger, validate_workspace

#: Nombre del fichero de índice, dentro del ``working_dir`` del motor.
REGISTRY_FILENAME = "bimnemo_nemos.json"

#: Versión del formato. Si algún día cambia la forma, esto permite migrar en
#: vez de adivinar.
REGISTRY_VERSION = 1

#: Identificador de la NEMO heredada: el workspace vacío, que es donde vive
#: todo lo que se indexó antes de que existieran las NEMOs. Se registra tal
#: cual, SIN mover un solo fichero.
LEGACY_ID = ""
LEGACY_NAME = "General"

#: Tope del identificador. Los nombres de carpeta tienen límites reales y una
#: ruta larga en Windows falla de formas poco claras.
MAX_ID_LENGTH = 48
MAX_NAME_LENGTH = 60


class NemoError(Exception):
    """Fallo de uso del registro: nombre inválido, duplicado o inexistente."""


@dataclass(frozen=True)
class Nemo:
    """Una memoria registrada."""

    id: str  # workspace real; "" es la heredada
    name: str  # lo que ve el usuario
    created_at: str  # ISO 8601, UTC
    protected: bool = False  # es la memoria base
    #: Solo la base puede estar oculta. Existe por dentro —el motor necesita
    #: un espacio de trabajo por defecto— pero no se enseña: es el estado de
    #: una instalación sin estrenar, y el de después de borrar «General».
    hidden: bool = False

    def to_payload(self) -> dict[str, Any]:
        datos = {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "protected": self.protected,
        }
        if self.hidden:
            datos["hidden"] = True
        return datos


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(name: str) -> str:
    """Convierte un nombre visible en un identificador válido de workspace.

    Saneado igual que hace el servidor con la cabecera ``LIGHTRAG-WORKSPACE``
    (``lightrag_server.py::get_workspace_from_request``), para que un nombre
    creado aquí y uno llegado por cabecera se resuelvan al mismo sitio. Si
    divergieran, una IA externa escribiría en una memoria distinta de la que
    cree.
    """
    slug = re.sub(r"[^A-Za-z0-9_]", "_", (name or "").strip())
    slug = re.sub(r"_{2,}", "_", slug).strip("_")
    return slug[:MAX_ID_LENGTH]


@dataclass
class NemoRegistry:
    """Índice de NEMOs, persistido en un JSON junto a los datos del motor.

    No es seguro entre procesos: el índice lo escribe un único servidor. Sí lo
    es entre hilos, que es lo que hace falta con varios trabajadores de
    uvicorn en el mismo proceso.
    """

    working_dir: Path
    _nemos: dict[str, Nemo] = field(default_factory=dict, init=False)
    _default_id: str = field(default=LEGACY_ID, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    # -- Ciclo de vida -----------------------------------------------------

    @property
    def path(self) -> Path:
        return Path(self.working_dir) / REGISTRY_FILENAME

    def load(self) -> None:
        """Lee el índice del disco, creándolo si no existe.

        Un índice ilegible **no se borra ni se sobrescribe**: se deja donde
        está, se avisa, y se arranca con la NEMO heredada. Reescribirlo
        borraría la lista de memorias del usuario por un fichero corrupto,
        cuando sus datos siguen intactos en disco.
        """
        with self._lock:
            self._nemos = {}
            self._default_id = LEGACY_ID

            raw: dict[str, Any] | None = None
            if self.path.is_file():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    logger.error(
                        "BIMNEMO: el índice de NEMOs (%s) no se pudo leer: %s. "
                        "Se arranca solo con la memoria heredada; el fichero NO "
                        "se ha tocado.",
                        self.path,
                        exc,
                    )

            if raw:
                self._load_entries(raw.get("nemos") or [])
                stored_default = raw.get("default", LEGACY_ID)
                if isinstance(stored_default, str) and stored_default in self._nemos:
                    self._default_id = stored_default

            # Sin índice **y** sin datos en la base es una instalación nueva:
            # no hay ninguna memoria que enseñar, y la primera la nombra el
            # usuario. Con datos se enseña aunque falte el índice: un índice
            # perdido no puede esconder los documentos de nadie.
            # Un índice que existe pero no se lee NO es una instalación nueva:
            # ahí la base se enseña, que es lo prudente.
            nuevo = not self.path.is_file() and not self._base_con_datos()
            self._ensure_legacy(oculta=nuevo)

    def _load_entries(self, entries: Iterable[Any]) -> None:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            nemo_id = entry.get("id")
            name = entry.get("name")
            if not isinstance(nemo_id, str) or not isinstance(name, str):
                continue
            if nemo_id and slugify(nemo_id) != nemo_id:
                # Un identificador que no sobrevive al saneado apuntaría a una
                # carpeta distinta de la que dice. Se descarta la entrada, no
                # los datos: siguen en disco y se pueden volver a registrar.
                logger.warning(
                    "BIMNEMO: se ignora la NEMO %r: su identificador no es válido.",
                    nemo_id,
                )
                continue
            self._nemos[nemo_id] = Nemo(
                id=nemo_id,
                name=name[:MAX_NAME_LENGTH],
                created_at=entry.get("created_at") or _now(),
                protected=bool(entry.get("protected")) or nemo_id == LEGACY_ID,
                hidden=nemo_id == LEGACY_ID and bool(entry.get("hidden")),
            )

    def _ensure_legacy(self, oculta: bool = False) -> None:
        """La NEMO heredada existe siempre y no se puede borrar.

        Es el workspace vacío, es decir el ``working_dir`` raíz: ahí vive todo
        lo indexado antes de que existieran las NEMOs, y ahí siguen los datos
        aunque el índice se pierda.
        """
        if LEGACY_ID not in self._nemos:
            self._nemos[LEGACY_ID] = Nemo(
                id=LEGACY_ID,
                name=LEGACY_NAME,
                created_at=_now(),
                protected=True,
                hidden=oculta,
            )
        if self._default_id not in self._nemos:
            self._default_id = LEGACY_ID

    def _base_con_datos(self) -> bool:
        """¿Tiene documentos la memoria base?

        Se mira el estado de los documentos, que es la verdad del motor, y no
        si hay ficheros: un almacén vacío sigue dejando sus ficheros ``{}``.
        Ante la duda se responde que sí: equivocarse por ese lado enseña una
        memoria vacía; por el otro, esconde los documentos de alguien.
        """
        estado = Path(self.working_dir) / "kv_store_doc_status.json"
        if not estado.is_file():
            return False
        try:
            return bool(json.loads(estado.read_text(encoding="utf-8") or "{}"))
        except (OSError, ValueError):
            return True

    def save(self) -> None:
        """Escribe el índice de forma atómica."""
        with self._lock:
            payload = {
                "version": REGISTRY_VERSION,
                "default": self._default_id,
                "nemos": [n.to_payload() for n in self._todas()],
            }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

        def _write(tmp_path: str) -> None:
            Path(tmp_path).write_text(text, encoding="utf-8")

        atomic_write(str(self.path), _write, workspace="bimnemo")

    # -- Consulta ----------------------------------------------------------

    def _todas(self) -> list[Nemo]:
        """Todas, la base primero, oculta o no; el resto por nombre."""
        others = [n for n in self._nemos.values() if n.id != LEGACY_ID]
        others.sort(key=lambda n: n.name.lower())
        legacy = self._nemos.get(LEGACY_ID)
        return ([legacy] if legacy else []) + others

    def _ordered(self) -> list[Nemo]:
        """Las que se enseñan: todas menos la base si está oculta."""
        return [n for n in self._todas() if not n.hidden]

    def list(self) -> list[Nemo]:
        with self._lock:
            return self._ordered()

    def ids(self) -> list[str]:
        with self._lock:
            return [n.id for n in self._ordered()]

    def get(self, nemo_id: str) -> Nemo | None:
        with self._lock:
            return self._nemos.get(nemo_id or LEGACY_ID)

    def exists(self, nemo_id: str) -> bool:
        return self.get(nemo_id) is not None

    @property
    def default_id(self) -> str:
        with self._lock:
            return self._default_id

    def _default_visible(self) -> None:
        """Si la por defecto está oculta y hay otra a la vista, pasa a ésa.

        Una petición sin memoria iría si no a una base vacía e invisible, y
        quien consulta por la API recibiría «no hay nada» teniendo memorias.
        """
        actual = self._nemos.get(self._default_id)
        if actual is not None and not actual.hidden:
            return
        visibles = self._ordered()
        self._default_id = visibles[0].id if visibles else LEGACY_ID

    def resolve(self, requested: str | None) -> str:
        """Identificador de NEMO a usar para una petición.

        ``None`` o cadena vacía significan «la de por defecto». Un
        identificador desconocido **no cae silenciosamente en la de por
        defecto**: eso escribiría en la memoria equivocada sin que nadie se
        entere. Se rechaza.
        """
        if requested is None or requested == "":
            return self.default_id

        candidate = slugify(requested)
        with self._lock:
            if candidate in self._nemos:
                return candidate
            # Admite también que llamen por el nombre visible.
            lowered = requested.strip().lower()
            for nemo in self._nemos.values():
                if nemo.name.lower() == lowered:
                    return nemo.id
        raise NemoError(f"No existe ninguna NEMO llamada {requested!r}")

    # -- Modificación ------------------------------------------------------

    def create(self, name: str) -> Nemo:
        """Registra una NEMO nueva a partir de su nombre visible.

        No crea carpetas: de eso se encarga el almacenamiento la primera vez
        que la NEMO se usa. Registrar y materializar son cosas distintas, y
        separarlas evita dejar carpetas huérfanas si el registro falla.
        """
        clean_name = (name or "").strip()
        if not clean_name:
            raise NemoError("La NEMO necesita un nombre.")
        if len(clean_name) > MAX_NAME_LENGTH:
            raise NemoError(
                f"El nombre no puede pasar de {MAX_NAME_LENGTH} caracteres."
            )

        nemo_id = slugify(clean_name)
        if not nemo_id:
            raise NemoError(
                "Ese nombre no deja ningún carácter utilizable. Usa letras o números."
            )

        try:
            validate_workspace(nemo_id)
        except Exception as exc:  # el validador del motor manda
            raise NemoError(f"Nombre no admitido: {exc}") from exc

        with self._lock:
            # Unicidad sin distinguir mayúsculas: en Windows «Obra» y «obra»
            # son la misma carpeta, y admitir las dos las haría compartir
            # datos en silencio.
            lowered = nemo_id.lower()
            # El choque de NOMBRE se comprueba primero aunque el de carpeta
            # también saltaría: «ya existe una NEMO llamada así» le dice al
            # usuario qué ha pasado, y «ocuparía la misma carpeta» no.
            for existing in self._nemos.values():
                if existing.hidden:
                    continue
                if existing.name.strip().lower() == clean_name.lower():
                    raise NemoError(f"Ya existe una NEMO llamada {clean_name!r}.")
            for existing in self._nemos.values():
                if existing.id.lower() == lowered:
                    raise NemoError(
                        f"Ya existe una NEMO que ocuparía la misma carpeta "
                        f"({existing.name})."
                    )

            nemo = Nemo(id=nemo_id, name=clean_name, created_at=_now())
            self._nemos[nemo_id] = nemo
            self._default_visible()

        self.save()
        logger.info("BIMNEMO: NEMO creada %r (workspace %r)", clean_name, nemo_id)
        return nemo

    def ensure(
        self,
        nemo_id: str,
        *,
        name: str | None = None,
        default: bool = False,
    ) -> Nemo:
        """Registra una NEMO por su identificador si todavía no está.

        Es la vía para adoptar lo que ya existe, no para crear: el servidor
        arranca con un ``WORKSPACE`` configurado y esa memoria tiene datos
        aunque nadie la haya registrado nunca. Dejarla fuera del índice la
        volvería invisible en la interfaz mientras sigue siendo la que
        responde.

        A diferencia de :meth:`create`, **no rechaza duplicados**: si ya
        está, la devuelve tal cual.
        """
        if nemo_id and slugify(nemo_id) != nemo_id:
            raise NemoError(f"Identificador de NEMO no válido: {nemo_id!r}")

        with self._lock:
            nemo = self._nemos.get(nemo_id)
            if nemo is None:
                nemo = Nemo(
                    id=nemo_id,
                    name=(name or nemo_id or LEGACY_NAME)[:MAX_NAME_LENGTH],
                    created_at=_now(),
                    protected=nemo_id == LEGACY_ID,
                )
                self._nemos[nemo_id] = nemo
            if default:
                self._default_id = nemo_id
            self._default_visible()

        self.save()
        return nemo

    def rename(self, nemo_id: str, new_name: str) -> Nemo:
        """Cambia el nombre visible. **El identificador no se toca.**

        Renombrar no mueve datos: el workspace sigue siendo el mismo. Lo
        contrario obligaría a reescribir todos los almacenes por un cambio de
        rótulo.
        """
        clean_name = (new_name or "").strip()
        if not clean_name:
            raise NemoError("La NEMO necesita un nombre.")
        if len(clean_name) > MAX_NAME_LENGTH:
            raise NemoError(
                f"El nombre no puede pasar de {MAX_NAME_LENGTH} caracteres."
            )

        with self._lock:
            nemo = self._nemos.get(nemo_id)
            if nemo is None:
                raise NemoError(f"No existe la NEMO {nemo_id!r}.")
            for existing in self._nemos.values():
                if (
                    existing.id != nemo_id
                    and not existing.hidden
                    and existing.name.strip().lower() == clean_name.lower()
                ):
                    raise NemoError(f"Ya existe una NEMO llamada {clean_name!r}.")

            # Ponerle nombre a la base oculta es crear la primera memoria:
            # vuelve a verse, con el nombre que eligió el usuario.
            renamed = Nemo(
                id=nemo.id,
                name=clean_name,
                created_at=_now() if nemo.hidden else nemo.created_at,
                protected=nemo.protected,
            )
            self._nemos[nemo_id] = renamed

        self.save()
        return renamed

    def delete(self, nemo_id: str) -> Nemo:
        """Quita una NEMO del índice y devuelve la que se quitó.

        **No borra datos de disco.** Quién borra la carpeta, y con qué
        confirmación, lo decide la capa de arriba: dejar esas dos cosas juntas
        convierte un fallo del índice en una pérdida de datos.
        """
        with self._lock:
            nemo = self._nemos.get(nemo_id)
            if nemo is None or nemo.hidden:
                raise NemoError(f"No existe la NEMO {nemo_id!r}.")
            if nemo_id == LEGACY_ID:
                # La base no se puede quitar de verdad: es el espacio de
                # trabajo por defecto del motor. Se oculta y vuelve a su
                # nombre de fábrica, que es lo que el usuario ve como
                # «borrada». **Vaciarla antes es cosa de quien llama**: esto
                # solo toca el índice.
                self._nemos[LEGACY_ID] = Nemo(
                    id=LEGACY_ID,
                    name=LEGACY_NAME,
                    created_at=nemo.created_at,
                    protected=True,
                    hidden=True,
                )
            else:
                del self._nemos[nemo_id]
            if self._default_id == nemo_id:
                self._default_id = LEGACY_ID
            self._default_visible()

        self.save()
        logger.info("BIMNEMO: NEMO eliminada del índice %r", nemo_id)
        return nemo

    def set_default(self, nemo_id: str) -> None:
        """Fija qué NEMO se usa cuando una petición no dice cuál."""
        with self._lock:
            if nemo_id not in self._nemos:
                raise NemoError(f"No existe la NEMO {nemo_id!r}.")
            self._default_id = nemo_id
        self.save()

    # -- Presentación ------------------------------------------------------

    def to_payload(self) -> dict[str, Any]:
        with self._lock:
            return {
                "default": self._default_id,
                "nemos": [n.to_payload() for n in self._ordered()],
            }


__all__ = [
    "LEGACY_ID",
    "LEGACY_NAME",
    "MAX_ID_LENGTH",
    "MAX_NAME_LENGTH",
    "Nemo",
    "NemoError",
    "NemoRegistry",
    "REGISTRY_FILENAME",
    "slugify",
]
