"""Endpoints de la configuración de IA de BIMNEMO.

Separado de ``bimnemo_routes`` porque son cosas distintas: aquél sirve para
*usar* la memoria (panel, ficheros, consulta), éste para *decidir con qué
modelos funciona*. Se montan juntos — ``create_bimnemo_routes`` incluye este
router — así que desde fuera siguen siendo un solo prefijo ``/bimnemo``.

Lo que hay que tener presente al tocar esto:

* **No se aplica nada en caliente, y no se puede.** El motor construye sus
  funciones de LLM y de embeddings al arrancar a partir de estas variables.
  Guardar escribe el ``.env`` y devuelve ``restart_required``; aplicarlo es
  reiniciar el proceso.
* **Lista blanca de claves.** Este router configura la IA; no es una vía para
  reescribir cualquier variable del despliegue.
* **Las claves de API no vuelven al navegador.** De ellas solo se dice si
  están puestas.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lightrag.api.bimnemo.runtime import (
    CONFIGURABLE_ENV_KEYS,
    RESTART_EXIT_CODE as _RESTART_EXIT_CODE,
)
from lightrag.api.bimnemo.envfile import UNCHANGED, read_env, write_env
from lightrag.api.bimnemo.providers import catalog_payload, find, match_provider
from lightrag.utils import logger

from ..utils_api import get_combined_auth_dependency
from .document_routes import check_pipeline_busy_or_raise

# Código de salida con el que el motor se despide cuando le piden reiniciar.
# El lanzador de escritorio lo distingue de una caída para no contarlo como
# fallo ni entrar en su freno de reinicios.
# Las constantes viven en un módulo sin importaciones para que el lanzador
# pueda leerlas sin arrastrar consigo la carga del ``.env``; ver runtime.py.
RESTART_EXIT_CODE = _RESTART_EXIT_CODE
WRITABLE_ENV_KEYS = CONFIGURABLE_ENV_KEYS


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------


class ProvidersResponse(BaseModel):
    llm: list[dict[str, Any]]
    embedding: list[dict[str, Any]]
    rerank: list[dict[str, Any]]


class SettingsResponse(BaseModel):
    env_path: str
    env_exists: bool
    llm: dict[str, Any]
    embedding: dict[str, Any]
    rerank: dict[str, Any]
    language: str = Field(
        default="",
        description="Idioma en el que el motor escribe entidades y respuestas",
    )
    restart_required: bool = Field(
        description="Lo guardado difiere de lo que el motor está usando ahora"
    )


class SectionSettings(BaseModel):
    """Un bloque del formulario: proveedor, host, clave, modelo."""

    provider: str = Field(description="Clave del preajuste elegido")
    host: str = ""
    model: str = ""
    api_key: str = Field(
        default=UNCHANGED,
        description=(
            "Clave de API. Manda el centinela __BIMNEMO_SIN_CAMBIOS__ para "
            "dejar la guardada intacta, o cadena vacía para borrarla."
        ),
    )
    dim: Optional[int] = Field(
        default=None, description="Dimensión del embedding (solo embeddings)"
    )


class AccessRequest(BaseModel):
    """Encender o apagar la clave de acceso a la API."""

    enabled: bool = Field(
        description="True para exigir clave; False para dejar la API abierta."
    )
    key: Optional[str] = Field(
        default=None,
        min_length=16,
        max_length=200,
        description=(
            "La clave a exigir. Obligatoria al encender. Se ignora al apagar."
        ),
    )


class AccessResponse(BaseModel):
    enabled: bool
    changed: bool
    restart_required: bool
    message: str


class SaveSettingsRequest(BaseModel):
    llm: Optional[SectionSettings] = None
    embedding: Optional[SectionSettings] = None
    rerank: Optional[SectionSettings] = None
    language: Optional[str] = Field(
        default=None,
        description=(
            "Idioma de extraccion y de respuesta. Cambiarlo NO reescribe lo ya "
            "indexado: las entidades guardadas conservan el idioma con el que "
            "se extrajeron."
        ),
    )

    def to_env_updates(self) -> dict[str, Optional[str]]:
        """Traduce el formulario a las variables que el motor lee al arrancar.

        El binding que se escribe NO es la clave del preajuste: es el binding
        real del catálogo. «DeepSeek» se guarda como ``LLM_BINDING=openai``
        más su host, porque eso es lo que el motor entiende.
        """
        updates: dict[str, Optional[str]] = {}

        for kind, section, prefix in (
            ("llm", self.llm, "LLM"),
            ("embedding", self.embedding, "EMBEDDING"),
            ("rerank", self.rerank, "RERANK"),
        ):
            if section is None:
                continue

            provider = find(kind, section.provider)
            if provider is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Proveedor desconocido para {kind}: {section.provider!r}",
                )

            updates[f"{prefix}_BINDING"] = provider.binding

            # Un host vacío se deja SIN escribir en lugar de escribirse vacío:
            # varios bindings (gemini, bedrock, voyageai) resuelven su propio
            # endpoint, y una cadena vacía los rompería.
            host = (section.host or "").strip()
            if host:
                updates[f"{prefix}_BINDING_HOST"] = host

            model = (section.model or "").strip()
            if model:
                updates[f"{prefix}_MODEL"] = model

            if section.api_key != UNCHANGED:
                updates[f"{prefix}_BINDING_API_KEY"] = section.api_key.strip()

            if kind == "embedding" and section.dim:
                updates["EMBEDDING_DIM"] = str(section.dim)

        if self.language is not None:
            idioma = self.language.strip()
            if idioma:
                updates["SUMMARY_LANGUAGE"] = idioma

        return updates


class SaveSettingsResponse(BaseModel):
    saved: bool
    env_path: str
    changed: list[str]
    restart_required: bool
    message: str


class RestartResponse(BaseModel):
    restarting: bool
    supervised: bool = Field(
        description="True si el lanzador de escritorio volverá a levantar el motor"
    )
    message: str


# ---------------------------------------------------------------------------
# Factoría
# ---------------------------------------------------------------------------


def create_bimnemo_settings_routes(rag, api_key: Optional[str] = None) -> APIRouter:
    """Router de la configuración de IA.

    **Sin prefijo propio a propósito.** Se incluye dentro del router de
    BIMNEMO, que ya aporta ``/bimnemo``; declararlo aquí también lo duplicaría
    y las rutas saldrían en ``/bimnemo/bimnemo/…``.
    """
    combined_auth = get_combined_auth_dependency(api_key)
    router = APIRouter(tags=["bimnemo"])

    # -- Configuración de la IA -------------------------------------------

    @router.get(
        "/providers",
        response_model=ProvidersResponse,
        dependencies=[Depends(combined_auth)],
        summary="Catálogo de proveedores de IA seleccionables",
    )
    async def get_providers() -> ProvidersResponse:
        """Proveedores, modelos sugeridos y a qué binding real corresponde cada uno.

        Un preajuste no es un binding nuevo: casi todos los de la nube hablan
        el protocolo de OpenAI y se resuelven con el binding ``openai``
        cambiando el host.
        """
        catalog = catalog_payload()
        return ProvidersResponse(
            llm=catalog["llm"],
            embedding=catalog["embedding"],
            rerank=catalog["rerank"],
        )

    @router.get(
        "/settings",
        response_model=SettingsResponse,
        dependencies=[Depends(combined_auth)],
        summary="Configuración de IA guardada en el .env",
    )
    async def get_settings() -> SettingsResponse:
        """Lo que hay escrito en el ``.env``, con las claves enmascaradas.

        De una clave de API solo se dice si está puesta. Su valor no sale de
        la máquina ni siquiera hacia la propia ventana.
        """
        values = read_env(_env_path())
        return SettingsResponse(
            env_path=str(_env_path()),
            env_exists=_env_path().is_file(),
            llm=_section_view(values, "llm"),
            embedding=_section_view(values, "embedding"),
            rerank=_section_view(values, "rerank"),
            language=values.get("SUMMARY_LANGUAGE", "") or DEFAULT_LANGUAGE,
            restart_required=_settings_differ_from_running(values),
        )

    @router.post(
        "/settings",
        response_model=SaveSettingsResponse,
        dependencies=[Depends(combined_auth)],
        summary="Guardar la configuración de IA en el .env",
    )
    async def save_settings(request: SaveSettingsRequest) -> SaveSettingsResponse:
        """Escribe el ``.env`` y dice que hay que reiniciar.

        **No aplica nada en caliente, y no puede.** El motor construye sus
        funciones de LLM y de embeddings al arrancar, a partir de estas
        variables; cambiarlas en memoria dejaría una instancia mintiendo sobre
        lo que usa. Por eso la respuesta lleva ``restart_required`` y la vista
        ofrece reiniciar.

        Solo se tocan las claves del formulario: el resto del fichero —
        comentarios, orden y ajustes que BIMNEMO no enseña — se conserva.
        """
        updates = request.to_env_updates()

        unknown = sorted(set(updates) - WRITABLE_ENV_KEYS)
        if unknown:
            # Lista blanca: este endpoint configura la IA, no es una vía para
            # reescribir cualquier variable del despliegue.
            raise HTTPException(
                status_code=400,
                detail=f"Claves no configurables desde aquí: {', '.join(unknown)}",
            )

        try:
            changed = write_env(_env_path(), updates)
        except OSError as exc:
            logger.error("BIMNEMO: no se pudo escribir el .env: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"No se pudo escribir {_env_path()}: {exc}",
            )

        logger.info(
            "BIMNEMO: configuración guardada (%s)", ", ".join(changed) or "sin cambios"
        )
        return SaveSettingsResponse(
            saved=True,
            env_path=str(_env_path()),
            changed=changed,
            restart_required=bool(changed),
            message=(
                "Configuración guardada. Reinicia BIMNEMO para que el motor la use."
                if changed
                else "No había nada que cambiar."
            ),
        )

    @router.post(
        "/access",
        response_model=AccessResponse,
        dependencies=[Depends(combined_auth)],
        summary="Exigir —o dejar de exigir— una clave para usar la API",
    )
    async def set_access(request: AccessRequest) -> AccessResponse:
        """Escribe o borra ``LIGHTRAG_API_KEY`` y pide un reinicio.

        Va aparte de ``/settings`` a propósito: aquello configura **la IA**
        —qué modelo, qué proveedor, qué idioma— y esto decide **quién puede
        entrar**. Meterlo en el mismo formulario habría obligado a añadirle un
        campo que no tiene nada que ver con lo que ese formulario significa.

        **No aplica nada en caliente, y no puede.** El guardia de las rutas se
        construye al arrancar, leyendo esta variable del entorno. Por eso la
        respuesta pide reinicio, igual que un cambio de proveedor.

        Quien llame a esto con la API ya protegida tiene que presentar la clave
        actual: la ruta lleva el mismo guardia que las demás. Es lo que impide
        que una página cualquiera del navegador apague la protección.
        """
        if request.enabled and not request.key:
            raise HTTPException(
                status_code=400,
                detail="Para exigir clave hay que decir cuál.",
            )

        nueva = request.key.strip() if (request.enabled and request.key) else ""

        # Al apagar se escribe cadena vacía, **no** ``None``.
        #
        # ``write_env`` con ``None`` comenta la línea en vez de borrarla, para
        # que el usuario vea qué había y pueda devolverlo a mano. Es la regla
        # correcta para un modelo o un host; para una credencial que se acaba
        # de retirar es justo la contraria: dejaría la clave en texto plano
        # dentro del fichero, viva para quien lo lea y muerta para el motor.
        #
        # `LIGHTRAG_API_KEY=` vacío es falso al arrancar, así que la API queda
        # abierta igual y no sobrevive ningún secreto.
        try:
            changed = write_env(_env_path(), {"LIGHTRAG_API_KEY": nueva})
        except OSError as exc:
            logger.error("BIMNEMO: no se pudo escribir el .env: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"No se pudo escribir {_env_path()}: {exc}",
            )

        # El valor NUNCA se registra: el log de una aplicación de escritorio se
        # comparte para pedir ayuda, y una clave en él ya no es una clave.
        logger.info(
            "BIMNEMO: acceso a la API %s",
            "protegido con clave" if nueva else "abierto (sin clave)",
        )
        return AccessResponse(
            enabled=bool(nueva),
            changed=bool(changed),
            restart_required=bool(changed),
            message=(
                "Clave guardada. Al reiniciar, la API la pedirá."
                if nueva
                else "Clave retirada. Al reiniciar, la API quedará abierta."
            ),
        )

    @router.post(
        "/restart",
        response_model=RestartResponse,
        dependencies=[Depends(combined_auth)],
        summary="Reiniciar el motor para aplicar la configuración",
    )
    async def restart_engine() -> RestartResponse:
        """Termina el proceso del motor para que el lanzador lo levante de nuevo.

        Es la única forma honesta de aplicar un cambio de proveedor: las
        funciones de LLM y de embeddings se construyen al arrancar, y no hay
        manera de sustituirlas en caliente sin dejar una instancia que miente
        sobre lo que usa.

        **Se niega si el pipeline está ocupado** (HTTP 409). Cortar a mitad de
        una ingesta dejaría documentos a medio indexar, y los almacenes
        respaldados por fichero publican el espacio de nombres entero en cada
        confirmación.

        Solo reinicia de verdad cuando BIMNEMO se lanzó como aplicación
        (``BIMNEMO.bat``), que es quien supervisa el proceso. Arrancado a mano
        con ``lightrag-server``, esto lo apaga y hay que volver a lanzarlo.
        """
        await check_pipeline_busy_or_raise(rag)

        supervised = os.getenv("BIMNEMO_SUPERVISED") == "1"

        async def _exit_soon() -> None:
            # Da tiempo a que la respuesta salga por el socket antes de morir:
            # sin esto el navegador ve la conexión cortada en lugar del 200, y
            # no sabe si el reinicio llegó a pedirse.
            await asyncio.sleep(0.6)
            try:
                await rag.finalize_storages()
            except Exception as exc:  # cerrar mal es peor que no cerrar
                logger.warning("BIMNEMO: fallo al cerrar los almacenes: %s", exc)
            logger.info("BIMNEMO: reinicio solicitado; terminando el proceso")
            os._exit(RESTART_EXIT_CODE)

        asyncio.create_task(_exit_soon())

        return RestartResponse(
            restarting=True,
            supervised=supervised,
            message=(
                "Reiniciando el motor. La ventana volverá sola en unos segundos."
                if supervised
                else "El motor se está cerrando. Vuelve a abrir BIMNEMO para usarlo."
            ),
        )

    return router


# ---------------------------------------------------------------------------
# Ayudantes
# ---------------------------------------------------------------------------


_SECTION_PREFIX = {"llm": "LLM", "embedding": "EMBEDDING", "rerank": "RERANK"}

#: Lo que usa el motor cuando ``SUMMARY_LANGUAGE`` no está puesto. Se enseña
#: tal cual para que la pantalla nunca aparezca vacía diciendo otra cosa que
#: lo que de verdad va a pasar al indexar.
DEFAULT_LANGUAGE = "English"


def _env_path() -> Path:
    """El ``.env`` que el servidor lee al arrancar: el del directorio de trabajo.

    Se resuelve igual que lo hace LightRAG — ``load_dotenv()`` desde el
    directorio donde se lanzó el proceso — para que la pantalla edite el mismo
    fichero que el motor lee, y no otro que parezca correcto.
    """
    return Path(os.getcwd()) / ".env"


def _section_view(values: dict[str, str], kind: str) -> dict[str, Any]:
    """Un bloque del formulario, tal y como está guardado en el ``.env``."""
    prefix = _SECTION_PREFIX[kind]
    binding = values.get(f"{prefix}_BINDING", "")
    host = values.get(f"{prefix}_BINDING_HOST", "")

    view: dict[str, Any] = {
        "binding": binding,
        "provider": match_provider(kind, binding, host) if binding else "",
        "host": host,
        "model": values.get(f"{prefix}_MODEL", ""),
        "api_key_set": bool(values.get(f"{prefix}_BINDING_API_KEY", "")),
    }
    if kind == "embedding":
        raw_dim = values.get("EMBEDDING_DIM", "")
        view["dim"] = int(raw_dim) if raw_dim.isdigit() else None
    return view


def _settings_differ_from_running(values: dict[str, str]) -> bool:
    """¿Lo escrito en el ``.env`` ya no es lo que el proceso está usando?

    El motor lee estas variables una vez, al arrancar, y las deja en el
    entorno del proceso. Si el fichero dice otra cosa es que alguien guardó y
    todavía no ha reiniciado — y la vista debe decirlo, porque si no el
    usuario cree que su cambio ya está en vigor.
    """
    for key in (
        "LLM_BINDING",
        "LLM_MODEL",
        "LLM_BINDING_HOST",
        "EMBEDDING_BINDING",
        "EMBEDDING_MODEL",
        "EMBEDDING_BINDING_HOST",
        "EMBEDDING_DIM",
        "RERANK_BINDING",
        "RERANK_MODEL",
        "SUMMARY_LANGUAGE",
    ):
        stored = values.get(key)
        if stored is None:
            continue
        if os.getenv(key, "") != stored:
            return True
    return False


__all__ = ["RESTART_EXIT_CODE", "create_bimnemo_settings_routes"]
