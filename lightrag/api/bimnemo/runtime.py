"""Constantes que comparten el lanzador y el motor.

**Este módulo no importa nada a propósito**, y es la razón de que exista.

El lanzador necesitaba dos cosas del módulo de configuración: el código de
salida con el que el motor pide reiniciarse y la lista de variables que la
pantalla de configuración puede escribir. Importarlas de allí arrastraba
``lightrag.api.config``, que llama a ``load_dotenv()`` **al importarse** y deja
el contenido del ``.env`` metido en el entorno del lanzador.

Eso rompía la configuración de una forma difícil de ver: el lanzador se
quedaba con los valores que había en el ``.env`` cuando arrancó, se los pasaba
a cada motor que levantaba, y el motor —que hace ``load_dotenv(override=False)``
— no podía pisarlos. Resultado: guardar la configuración y pulsar «Reiniciar»
no cambiaba nada, y solo cerrar y volver a abrir BIMNEMO surtía efecto.

Mientras aquí no haya un solo ``import`` de LightRAG, eso no puede repetirse.
"""

from __future__ import annotations

#: Con este código de salida el motor le pide al supervisor que lo levante de
#: nuevo. Un número alto y poco común, para no chocar con los que usan el
#: intérprete o el sistema.
RESTART_EXIT_CODE = 77

#: Las variables que la pantalla de configuración puede escribir en el ``.env``.
#:
#: Sirve para dos cosas a la vez, y las dos importan:
#:
#: 1. Es la lista blanca del endpoint que guarda: configurar la IA no puede ser
#:    una vía para reescribir cualquier variable del despliegue.
#: 2. Es lo que el lanzador **quita** del entorno antes de arrancar el motor,
#:    para que el fichero mande sobre lo que el proceso heredó.
CONFIGURABLE_ENV_KEYS: frozenset[str] = frozenset(
    {
        "LLM_BINDING",
        "LLM_BINDING_HOST",
        "LLM_BINDING_API_KEY",
        "LLM_MODEL",
        "EMBEDDING_BINDING",
        "EMBEDDING_BINDING_HOST",
        "EMBEDDING_BINDING_API_KEY",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIM",
        "RERANK_BINDING",
        "RERANK_BINDING_HOST",
        "RERANK_BINDING_API_KEY",
        "RERANK_MODEL",
        # Idioma de extraccion. No es un proveedor, pero se configura en la
        # misma pantalla y sufre el mismo problema de entorno heredado.
        "SUMMARY_LANGUAGE",
        # Perfil de tipos de entidad. Se escribe junto al idioma porque forma
        # parte de lo mismo: en qué idioma queda el grafo.
        "ENTITY_TYPE_PROMPT_FILE",
        # Clave de acceso a la API de BIMNEMO. No configura ningún proveedor:
        # decide si las rutas piden credencial o están abiertas.
        #
        # Está aquí por las dos razones de esta lista, y la segunda es la que
        # importa: el lanzador **quita estas claves del entorno del hijo** al
        # reiniciar, así que manda el fichero. Sin eso, apagar el interruptor
        # no apagaría nada — la clave heredada del proceso padre seguiría
        # ganando y la API seguiría pidiéndola.
        "LIGHTRAG_API_KEY",
    }
)


__all__ = ["CONFIGURABLE_ENV_KEYS", "RESTART_EXIT_CODE"]
