"""Tablas del catálogo de proveedores de BIMNEMO.

Solo datos: qué proveedores se ofrecen, a qué binding real corresponde cada
uno, qué host, qué modelos sugiere y dónde se saca su clave. La lógica —
validación, búsqueda y emparejado — vive en
:mod:`lightrag.api.bimnemo.providers`, que es quien importa esto.

Están separados porque cambian por motivos distintos y a ritmos distintos:
estas tablas se tocan cada vez que un proveedor saca un modelo nuevo; la
lógica, casi nunca.

**Al editar:** el campo ``binding`` solo admite los valores que declara
``providers.VALID_BINDINGS``. Inventar uno hace que el servidor se niegue a
arrancar, y el usuario lo ve como «BIMNEMO no abre».

## Los modelos son sugerencias, no una validación

El catálogo de cada proveedor cambia cada pocas semanas. Los nombres de aquí
son un punto de partida para el desplegable; el campo admite escribir
cualquier otro. Por eso cada proveedor lleva ``key_url``: esa misma página es
donde el usuario ve qué modelos tiene disponibles hoy.

## Direcciones: cuándo se rellenan y cuándo no

``host`` solo lleva valor cuando **existe una dirección universal** para ese
proveedor. Cuando no la hay, el campo va vacío y ``host_hint`` dice qué
escribir — el endpoint de Azure es distinto para cada inquilino, y el de
Bedrock depende de la región de AWS.

Caso aparte: ``host_used=False`` significa que **el binding ni siquiera mira
la dirección**. Solo le pasa a Voyage, cuya biblioteca construye el cliente
con la clave y nada más (``voyageai.AsyncClient(api_key=...)``). Dejar ahí un
campo editable invitaría a configurar algo que no tiene ningún efecto.

Gemini sí acepta dirección: el servidor se la pasa como ``base_url``, y
``lightrag/llm/gemini.py`` reconoce ``https://generativelanguage.googleapis.com``
—con o sin ``/v1`` o ``/v1beta``— como la de por defecto y la trata igual que
si estuviera vacía. Por eso se rellena: el usuario ve a dónde se conecta, y el
motor se comporta exactamente igual.

## Por qué Claude aparece bajo el binding ``openai``

LightRAG no tiene binding ``anthropic``. Pero Anthropic publica un endpoint
compatible con la API de OpenAI (``https://api.anthropic.com/v1/``), así que
Claude funciona con el binding ``openai`` apuntando ahí. Es la capa de
compatibilidad, no la API nativa: funciona para chat, y las funciones propias
de Anthropic —pensamiento extendido, caché de prompt— no están expuestas por
esa vía.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

Kind = Literal["llm", "embedding", "rerank"]


class Provider(NamedTuple):
    """Un preajuste de proveedor tal y como lo consume la vista."""

    key: str
    label: str
    binding: str  # binding REAL del motor; ver el aviso del encabezado
    group: str  # agrupación del desplegable
    host: str  # host sugerido; "" = no hay uno universal (ver host_hint)
    models: tuple[str, ...]  # sugerencias para el campo de modelo
    needs_key: bool
    key_hint: str = ""  # texto corto de dónde se consigue la clave
    key_url: str = ""  # enlace directo a esa página
    note: str = ""  # aviso que la vista enseña al elegirlo
    dims: tuple[int, ...] = ()  # dimensiones válidas (solo embeddings)
    host_hint: str = ""  # qué escribir cuando no hay host universal
    host_used: bool = True  # False = el binding ignora la dirección


# --- Grupos -----------------------------------------------------------------

LOCAL = "En tu equipo"
DIRECT = "Nube, integración propia"
COMPATIBLE = "Nube, compatible OpenAI"


# --- Modelos de lenguaje ----------------------------------------------------

LLM_PROVIDERS: tuple[Provider, ...] = (
    Provider(
        key="ollama",
        label="Ollama",
        binding="ollama",
        group=LOCAL,
        host="http://localhost:11434",
        models=(
            "qwen3:8b",
            "qwen3:14b",
            "gemma3:12b",
            "llama3.1:8b",
            "mistral-nemo:latest",
            "phi4:latest",
            "deepseek-r1:14b",
        ),
        needs_key=False,
        key_hint="No necesita clave",
        key_url="https://ollama.com/library",
        note="Sin coste y sin enviar nada fuera. La indexación es bastante más lenta.",
    ),
    Provider(
        key="lmstudio",
        label="LM Studio",
        binding="openai",
        group=LOCAL,
        host="http://localhost:1234/v1",
        models=("modelo-cargado-en-lm-studio",),
        needs_key=False,
        key_hint="No necesita clave",
        key_url="https://lmstudio.ai/models",
        note="Arranca el servidor local de LM Studio antes de guardar.",
    ),
    Provider(
        key="vllm",
        label="vLLM",
        binding="openai",
        group=LOCAL,
        host="http://localhost:8000/v1",
        models=("Qwen/Qwen3-8B-Instruct", "meta-llama/Llama-3.1-8B-Instruct"),
        needs_key=False,
        key_hint="No necesita clave",
        key_url="https://docs.vllm.ai/",
    ),
    Provider(
        key="localai",
        label="LocalAI",
        binding="openai",
        group=LOCAL,
        host="http://localhost:8080/v1",
        models=(),
        needs_key=False,
        key_hint="No necesita clave",
        key_url="https://localai.io/models/",
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
        label="OpenAI (ChatGPT)",
        binding="openai",
        group=DIRECT,
        host="https://api.openai.com/v1",
        models=(
            "gpt-5.6-luna",
            "gpt-5-nano",
            "gpt-5.6-terra",
            "gpt-5.6-sol",
            "gpt-6-astra",
        ),
        needs_key=True,
        key_hint="platform.openai.com/api-keys",
        key_url="https://platform.openai.com/api-keys",
        note=(
            "«nano» es el más barato; «luna» basta de sobra para extraer "
            "entidades, que es lo que más se gasta; «astra» es el más capaz."
        ),
    ),
    Provider(
        key="anthropic",
        label="Anthropic (Claude)",
        binding="openai",
        group=DIRECT,
        host="https://api.anthropic.com/v1/",
        models=(
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-haiku-4-5",
            "claude-opus-4-8",
            "claude-sonnet-4-6",
        ),
        needs_key=True,
        key_hint="console.anthropic.com/settings/keys",
        key_url="https://console.anthropic.com/settings/keys",
        note=(
            "Vía la capa compatible con OpenAI de Anthropic: LightRAG no trae "
            "binding propio. Sirve para chat y extracción; el pensamiento "
            "extendido y la caché de prompt no están expuestos por ahí. "
            "claude-haiku-4-5 es el barato para indexar."
        ),
    ),
    Provider(
        key="azure_openai",
        label="Azure OpenAI",
        binding="azure_openai",
        group=DIRECT,
        host="",
        host_hint="https://TU-RECURSO.openai.azure.com",
        models=("gpt-4.1-mini", "gpt-4o-mini", "gpt-4o"),
        needs_key=True,
        key_hint="portal.azure.com",
        key_url="https://portal.azure.com/",
        note=(
            "El modelo es el nombre de tu *deployment*, no el del modelo base. "
            "El host es tu endpoint de Azure."
        ),
    ),
    Provider(
        key="gemini",
        label="Google Gemini",
        binding="gemini",
        group=DIRECT,
        host="https://generativelanguage.googleapis.com",
        models=(
            "gemini-3.8-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ),
        needs_key=True,
        key_hint="aistudio.google.com/apikey",
        key_url="https://aistudio.google.com/apikey",
        note="Los «flash» son los baratos y rápidos; el «pro», el de razonar.",
    ),
    Provider(
        key="bedrock",
        label="Amazon Bedrock",
        binding="bedrock",
        group=DIRECT,
        host="",
        host_hint="Vacío: boto3 elige el endpoint de tu región de AWS",
        models=(
            "anthropic.claude-sonnet-5",
            "anthropic.claude-haiku-4-5",
            "anthropic.claude-opus-5",
            "amazon.nova-pro-v1:0",
            "amazon.nova-lite-v1:0",
        ),
        needs_key=False,
        key_hint="Credenciales de AWS, no clave de API",
        key_url="https://console.aws.amazon.com/bedrock/home#/modelaccess",
        note=(
            "Bedrock NO usa clave de API: se autentica con tus credenciales de "
            "AWS (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION). "
            "Antes hay que pedir acceso a cada modelo en la consola."
        ),
    ),
    Provider(
        key="deepseek",
        label="DeepSeek",
        binding="openai",
        group=COMPATIBLE,
        host="https://api.deepseek.com/v1",
        models=("deepseek-flash", "deepseek-v4-pro"),
        needs_key=True,
        key_hint="platform.deepseek.com/api_keys",
        key_url="https://platform.deepseek.com/api_keys",
        note=(
            "Muy barato para extraer entidades. Los nombres antiguos "
            "deepseek-chat y deepseek-reasoner ya no son los vigentes."
        ),
    ),
    Provider(
        key="xai",
        label="xAI (Grok)",
        binding="openai",
        group=COMPATIBLE,
        host="https://api.x.ai/v1",
        models=("grok-4.6", "grok-4.5", "grok-4.3"),
        needs_key=True,
        key_hint="console.x.ai",
        key_url="https://console.x.ai/",
    ),
    Provider(
        key="groq",
        label="Groq",
        binding="openai",
        group=COMPATIBLE,
        host="https://api.groq.com/openai/v1",
        # llama-3.1-8b-instant, qwen3-32b y kimi-k2 los retiró Groq en 2026;
        # su sustituto oficial es gpt-oss.
        models=(
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "llama-3.3-70b-versatile",
        ),
        needs_key=True,
        key_hint="console.groq.com/keys",
        key_url="https://console.groq.com/keys",
        note=(
            "El más rápido del mercado; acorta mucho la indexación. gpt-oss "
            "siempre razona: bájalo a «Bajo» en la barra."
        ),
    ),
    Provider(
        key="openrouter",
        label="OpenRouter",
        binding="openai",
        group=COMPATIBLE,
        host="https://openrouter.ai/api/v1",
        models=(
            "anthropic/claude-sonnet-5",
            "anthropic/claude-haiku-4-5",
            "openai/gpt-5.6-luna",
            "google/gemini-3.5-flash",
            "deepseek/deepseek-flash",
            "x-ai/grok-4.6",
        ),
        needs_key=True,
        key_hint="openrouter.ai/keys",
        key_url="https://openrouter.ai/keys",
        note="Una sola clave para modelos de casi todos los proveedores.",
    ),
    Provider(
        key="mistral",
        label="Mistral AI",
        binding="openai",
        group=COMPATIBLE,
        host="https://api.mistral.ai/v1",
        # Las versiones con fecha que había aquí (2508, 2506, 2411, 2410) las
        # retiró Mistral en 2025-2026. Los alias `-latest` apuntan siempre a
        # la vigente y no caducan.
        models=(
            "mistral-small-latest",
            "mistral-medium-latest",
            "mistral-large-latest",
            "ministral-8b-latest",
        ),
        needs_key=True,
        key_hint="console.mistral.ai/api-keys",
        key_url="https://console.mistral.ai/api-keys/",
    ),
    Provider(
        key="together",
        label="Together AI",
        binding="openai",
        group=COMPATIBLE,
        host="https://api.together.xyz/v1",
        # Qwen2.5-72B-Instruct-Turbo ya no está en el catálogo sin servidor.
        models=(
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "deepseek-ai/DeepSeek-V3",
        ),
        needs_key=True,
        key_hint="api.together.ai/settings/api-keys",
        key_url="https://api.together.ai/settings/api-keys",
    ),
    Provider(
        key="fireworks",
        label="Fireworks AI",
        binding="openai",
        group=COMPATIBLE,
        host="https://api.fireworks.ai/inference/v1",
        models=(
            "accounts/fireworks/models/llama-v3p3-70b-instruct",
            "accounts/fireworks/models/qwen3-235b-a22b",
        ),
        needs_key=True,
        key_hint="fireworks.ai/account/api-keys",
        key_url="https://fireworks.ai/account/api-keys",
    ),
    Provider(
        key="qwen",
        label="Alibaba Qwen (DashScope)",
        binding="openai",
        group=COMPATIBLE,
        host="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        models=("qwen3.7-flash", "qwen-turbo", "qwen-plus", "qwen-max", "qwen3-max"),
        needs_key=True,
        key_hint="dashscope.console.aliyun.com/apiKey",
        key_url="https://dashscope.console.aliyun.com/apiKey",
        note=(
            "qwen3.7-flash es de lo más barato del mercado para indexar; "
            "piensa por defecto, apágalo en la barra de razonamiento."
        ),
    ),
    Provider(
        key="zhipu",
        label="Zhipu AI (GLM)",
        binding="openai",
        group=COMPATIBLE,
        host="https://open.bigmodel.cn/api/paas/v4",
        models=("glm-4.6", "glm-4.5-air", "glm-4-plus", "glm-4-flash"),
        needs_key=True,
        key_hint="open.bigmodel.cn/usercenter/apikeys",
        key_url="https://open.bigmodel.cn/usercenter/apikeys",
    ),
    Provider(
        key="moonshot",
        label="Moonshot (Kimi)",
        binding="openai",
        group=COMPATIBLE,
        host="https://api.moonshot.cn/v1",
        # La serie K2 y moonshot-v1 se retiraron en 2026.
        models=("kimi-k2.6", "kimi-k3"),
        needs_key=True,
        key_hint="platform.moonshot.cn/console/api-keys",
        key_url="https://platform.moonshot.cn/console/api-keys",
    ),
    Provider(
        key="siliconflow",
        label="SiliconFlow",
        binding="openai",
        group=COMPATIBLE,
        host="https://api.siliconflow.cn/v1",
        models=("Qwen/Qwen3-8B", "deepseek-ai/DeepSeek-V3"),
        needs_key=True,
        key_hint="cloud.siliconflow.cn/account/ak",
        key_url="https://cloud.siliconflow.cn/account/ak",
    ),
    Provider(
        key="nebius",
        label="Nebius AI Studio",
        binding="openai",
        group=COMPATIBLE,
        host="https://api.studio.nebius.ai/v1",
        models=("Qwen/Qwen3-30B-A3B", "meta-llama/Llama-3.3-70B-Instruct"),
        needs_key=True,
        key_hint="studio.nebius.ai",
        key_url="https://studio.nebius.ai/settings/api-keys",
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
        note="Escribe a mano el host (con /v1 al final si tu proveedor lo pide) y el modelo.",
    ),
)
