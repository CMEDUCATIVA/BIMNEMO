"""Proveedores de recuperación: embeddings y reordenado.

La otra mitad del catálogo. ``provider_catalog`` tiene los modelos de
lenguaje —los que generan texto— y aquí están los que lo convierten en
vectores para poder buscarlo, y los que reordenan lo recuperado.

Separados porque se editan por motivos distintos: la tabla de modelos de
lenguaje cambia cada vez que alguien saca un modelo nuevo, que es cada pocas
semanas; los de embeddings, mucho menos a menudo.

El tipo ``Provider`` y los grupos viven en ``provider_catalog``, que es quien
importa esto.
"""

from __future__ import annotations

from lightrag.api.bimnemo.provider_catalog import COMPATIBLE, DIRECT, LOCAL, Provider

# --- Embeddings -------------------------------------------------------------
#
# La dimensión importa más de lo que parece: si cambias de modelo de
# embeddings, los vectores ya guardados dejan de ser comparables. Hay que
# vaciar el directorio de datos y reindexar. La vista lo avisa.
#
# Anthropic NO publica modelo de embeddings propio: recomienda Voyage AI, que
# sí está aquí abajo. Por eso Claude aparece en modelos de lenguaje y no aquí.

EMBEDDING_PROVIDERS: tuple[Provider, ...] = (
    Provider(
        key="ollama",
        label="Ollama",
        binding="ollama",
        group=LOCAL,
        host="http://localhost:11434",
        models=(
            "bge-m3:latest",
            "embeddinggemma",
            "nomic-embed-text",
            "mxbai-embed-large",
        ),
        needs_key=False,
        key_hint="No necesita clave",
        key_url="https://ollama.com/search?c=embedding",
        dims=(1024, 768, 768, 1024),
        note="bge-m3 (1024) es multilingüe y va muy bien en español.",
    ),
    Provider(
        key="lmstudio",
        label="LM Studio",
        binding="openai",
        group=LOCAL,
        host="http://localhost:1234/v1",
        models=("text-embedding-bge-m3",),
        needs_key=False,
        key_hint="No necesita clave",
        key_url="https://lmstudio.ai/models",
        dims=(1024,),
    ),
    Provider(
        key="lollms",
        label="LoLLMs",
        binding="lollms",
        group=LOCAL,
        host="http://localhost:9600",
        models=(),
        needs_key=False,
        key_hint="No necesita clave",
        key_url="https://github.com/ParisNeo/lollms",
    ),
    Provider(
        key="openai",
        label="OpenAI",
        binding="openai",
        group=DIRECT,
        host="https://api.openai.com/v1",
        models=("text-embedding-3-small", "text-embedding-3-large"),
        needs_key=True,
        key_hint="platform.openai.com/api-keys",
        key_url="https://platform.openai.com/api-keys",
        dims=(1536, 3072),
        note="El «small» cuesta 6 veces menos y rinde de sobra para buscar.",
    ),
    Provider(
        key="voyageai",
        label="Voyage AI",
        binding="voyageai",
        group=DIRECT,
        host="",
        host_used=False,
        models=(
            "voyage-4",
            "voyage-4-lite",
            "voyage-4-large",
            "voyage-4-nano",
            "voyage-code-4",
        ),
        needs_key=True,
        key_hint="dashboard.voyageai.com/api-keys",
        key_url="https://dashboard.voyageai.com/api-keys",
        dims=(1024, 1024, 1024, 1024, 1024),
        note="Es el que recomienda Anthropic: si usas Claude, encaja bien.",
    ),
    Provider(
        key="gemini",
        label="Google Gemini",
        binding="gemini",
        group=DIRECT,
        host="https://generativelanguage.googleapis.com",
        models=("gemini-embedding-001", "gemini-embedding-2-preview"),
        needs_key=True,
        key_hint="aistudio.google.com/apikey",
        key_url="https://aistudio.google.com/apikey",
        dims=(3072, 1536),
    ),
    Provider(
        key="jina",
        label="Jina AI",
        binding="jina",
        group=DIRECT,
        host="https://api.jina.ai/v1/embeddings",
        models=(
            "jina-embeddings-v5-text-small",
            "jina-embeddings-v5-text-nano",
            "jina-embeddings-v4",
            "jina-embeddings-v3",
        ),
        needs_key=True,
        key_hint="jina.ai/embeddings",
        key_url="https://jina.ai/embeddings/",
        dims=(1024, 768, 2048, 1024),
    ),
    Provider(
        key="azure_openai",
        label="Azure OpenAI",
        binding="azure_openai",
        group=DIRECT,
        host="",
        host_hint="https://TU-RECURSO.openai.azure.com",
        models=("text-embedding-3-small", "text-embedding-3-large"),
        needs_key=True,
        key_hint="portal.azure.com",
        key_url="https://portal.azure.com/",
        dims=(1536, 3072),
        note="El modelo es el nombre de tu *deployment* de Azure.",
    ),
    Provider(
        key="bedrock",
        label="Amazon Bedrock",
        binding="bedrock",
        group=DIRECT,
        host="",
        host_hint="Vacío: boto3 elige el endpoint de tu región de AWS",
        models=("amazon.titan-embed-text-v2:0", "cohere.embed-multilingual-v3"),
        needs_key=False,
        key_hint="Credenciales de AWS, no clave de API",
        key_url="https://console.aws.amazon.com/bedrock/home#/modelaccess",
        dims=(1024, 1024),
        note="Se autentica con credenciales de AWS, no con clave de API.",
    ),
    Provider(
        key="siliconflow",
        label="SiliconFlow",
        binding="openai",
        group=COMPATIBLE,
        host="https://api.siliconflow.cn/v1",
        models=("BAAI/bge-m3",),
        needs_key=True,
        key_hint="cloud.siliconflow.cn/account/ak",
        key_url="https://cloud.siliconflow.cn/account/ak",
        dims=(1024,),
    ),
    Provider(
        key="deepinfra",
        label="DeepInfra",
        binding="openai",
        group=COMPATIBLE,
        host="https://api.deepinfra.com/v1/openai",
        models=("BAAI/bge-m3", "intfloat/multilingual-e5-large"),
        needs_key=True,
        key_hint="deepinfra.com/dash/api_keys",
        key_url="https://deepinfra.com/dash/api_keys",
        dims=(1024, 1024),
    ),
    Provider(
        key="openai_compatible",
        label="Otro compatible con OpenAI",
        binding="openai",
        group=COMPATIBLE,
        host="",
        host_hint="https://tu-servidor/v1",
        models=(),
        needs_key=True,
        key_hint="La que te dé tu proveedor",
        note="Comprueba la dimensión que devuelve tu modelo: si no cuadra, la ingesta falla.",
    ),
)


# --- Reordenado -------------------------------------------------------------

RERANK_PROVIDERS: tuple[Provider, ...] = (
    Provider(
        key="null",
        label="Desactivado",
        binding="null",
        group="",
        host="",
        models=(),
        needs_key=False,
        note="Sin reordenado. El modo «mix» funciona, pero rinde bastante menos.",
    ),
    Provider(
        key="cohere",
        label="Cohere Rerank",
        binding="cohere",
        group=DIRECT,
        host="https://api.cohere.com/v2/rerank",
        models=("rerank-v3.5", "rerank-multilingual-v3.0"),
        needs_key=True,
        key_hint="dashboard.cohere.com/api-keys",
        key_url="https://dashboard.cohere.com/api-keys",
    ),
    Provider(
        key="jina",
        label="Jina Rerank",
        binding="jina",
        group=DIRECT,
        host="https://api.jina.ai/v1/rerank",
        models=(
            "jina-reranker-v3.5",
            "jina-reranker-v3",
            "jina-reranker-m0",
        ),
        needs_key=True,
        key_hint="jina.ai/reranker",
        key_url="https://jina.ai/reranker/",
    ),
    Provider(
        key="aliyun",
        label="Alibaba (DashScope)",
        binding="aliyun",
        group=DIRECT,
        host="https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
        models=("gte-rerank-v2",),
        needs_key=True,
        key_hint="dashscope.console.aliyun.com/apiKey",
        key_url="https://dashscope.console.aliyun.com/apiKey",
    ),
)
