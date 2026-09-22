"""Cuánto cobra cada proveedor por millón de tokens, para la tabla de consumo.

Solo datos y una función que los consulta. **Los precios cambian**: la tabla
lleva la fecha en que se comprobó (:data:`COMPROBADO`) y la pantalla la
enseña, para que nadie tome un coste viejo por una factura.

## De dónde sale cada cifra

Páginas oficiales de precios, consultadas el 2026-09-21:

- DeepSeek — https://api-docs.deepseek.com/quick_start/pricing
- OpenAI — https://developers.openai.com/api/docs/pricing
- Google — https://ai.google.dev/gemini-api/docs/pricing
- Alibaba (internacional) — https://www.alibabacloud.com/help/en/model-studio/model-pricing
- Anthropic — https://platform.claude.com/docs/en/about-claude/pricing
- xAI — https://docs.x.ai/docs/models
- Z.ai — https://docs.z.ai/guides/overview/pricing
- Mistral — https://mistral.ai/pricing/api
- AWS Bedrock y Azure — sus API públicas de precios

Un modelo que no está aquí **se mide igual** (tokens y llamadas) y su coste
sale como «sin precio». Es preferible a inventar una cifra.

## Lo que no se descuenta

Los proveedores cobran menos por la entrada que ya tienen en su caché. El
contador de LightRAG no recibe ese dato, así que el coste que se enseña es el
de **toda la entrada a precio normal**: un techo, nunca menos de lo real.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple, Optional

#: Cuándo se comprobaron los precios de esta tabla.
COMPROBADO = "2026-09-21"


class Precio(NamedTuple):
    """USD por millón de tokens."""

    entrada: float
    salida: float = 0.0


#: Modelos de lenguaje. La clave es el nombre tal como se escribe en BIMNEMO.
LENGUAJE: dict[str, Precio] = {
    # DeepSeek: aquí va la tarifa FUERA de hora punta; la punta es el doble
    # (ver `_es_punta_deepseek`).
    "deepseek-flash": Precio(0.15, 0.60),
    "deepseek-v4-pro": Precio(0.66, 1.98),
    # OpenAI
    "gpt-5-nano": Precio(0.05, 0.40),
    "gpt-5-mini": Precio(0.25, 2.00),
    "gpt-5.4-nano": Precio(0.20, 1.25),
    "gpt-5.4-mini": Precio(0.75, 4.50),
    "gpt-5.6-luna": Precio(0.20, 1.20),
    "gpt-5.6-terra": Precio(2.00, 12.00),
    "gpt-5.6-sol": Precio(4.00, 20.00),
    "gpt-6-astra": Precio(10.00, 50.00),
    # Google
    "gemini-2.5-flash-lite": Precio(0.10, 0.40),
    "gemini-2.5-flash": Precio(0.30, 2.50),
    "gemini-2.5-pro": Precio(1.25, 10.00),
    "gemini-3.5-flash-lite": Precio(0.30, 2.50),
    "gemini-3.5-flash": Precio(1.50, 9.00),
    "gemini-3.8-flash": Precio(0.75, 3.75),
    # Alibaba Qwen (internacional)
    "qwen3.7-flash": Precio(0.03, 0.13),
    "qwen3.8-flash": Precio(0.15, 0.47),
    "qwen-flash": Precio(0.05, 0.40),
    "qwen-turbo": Precio(0.05, 0.20),
    "qwen-plus": Precio(0.40, 1.20),
    "qwen-max": Precio(1.60, 6.40),
    "qwen3-max": Precio(1.20, 6.00),
    # Anthropic
    "claude-haiku-4-5": Precio(1.00, 5.00),
    "claude-sonnet-5": Precio(2.00, 10.00),
    "claude-sonnet-4-6": Precio(3.00, 15.00),
    "claude-opus-5": Precio(5.00, 25.00),
    "claude-opus-4-8": Precio(5.00, 25.00),
    # xAI
    "grok-4.3": Precio(1.25, 2.50),
    "grok-4.5": Precio(2.00, 6.00),
    "grok-4.6": Precio(2.00, 6.00),
    # Z.ai / Zhipu
    "glm-4-flash": Precio(0.0, 0.0),
    "glm-4.5-air": Precio(0.20, 1.10),
    "glm-4.6": Precio(0.60, 2.20),
    # Groq
    "llama-3.3-70b-versatile": Precio(0.59, 0.79),
    "openai/gpt-oss-20b": Precio(0.075, 0.30),
    "openai/gpt-oss-120b": Precio(0.15, 0.60),
    # Azure (Global Standard)
    "gpt-4o-mini": Precio(0.15, 0.60),
    "gpt-4.1-mini": Precio(0.40, 1.60),
    "gpt-4o": Precio(2.50, 10.00),
    # Amazon Bedrock
    "amazon.nova-micro-v1:0": Precio(0.035, 0.14),
    "amazon.nova-lite-v1:0": Precio(0.06, 0.24),
    "amazon.nova-pro-v1:0": Precio(0.80, 3.20),
}

#: Modelos de embeddings: solo se paga la entrada.
EMBEDDINGS: dict[str, Precio] = {
    "text-embedding-3-small": Precio(0.02),
    "text-embedding-3-large": Precio(0.13),
}

#: Proveedores que en BIMNEMO corren en el propio equipo: no cuestan dinero.
LOCALES = ("localhost", "127.0.0.1", "0.0.0.0")


def _es_punta_deepseek(momento: datetime) -> bool:
    """Hora punta de DeepSeek: 01-04 y 06-10 UTC, de lunes a viernes.

    Excluye los festivos chinos, que aquí no se conocen: en esos días se
    cuenta como punta y el coste sale por encima, nunca por debajo.
    """
    utc = momento.astimezone(timezone.utc)
    if utc.weekday() >= 5:
        return False
    return 1 <= utc.hour < 4 or 6 <= utc.hour < 10


def _nombre_base(modelo: str) -> str:
    """El nombre sin prefijo de proveedor: `deepseek/deepseek-flash` → `deepseek-flash`.

    OpenRouter y Bedrock anteponen el proveedor; el precio es por modelo.
    """
    nombre = (modelo or "").strip()
    if nombre.startswith("openai/gpt-oss"):
        return nombre
    if nombre.startswith("anthropic."):
        return nombre.split(".", 1)[1]
    return nombre.rsplit("/", 1)[-1]


def precio(
    tipo: str, modelo: str, host: str = "", momento: Optional[datetime] = None
) -> Optional[Precio]:
    """El precio vigente de ``modelo``, o ``None`` si no se conoce.

    ``tipo`` es ``"llm"`` o ``"embedding"``. ``host`` sirve para dos cosas:
    lo que corre en el propio equipo cuesta cero, y DeepSeek cobra el doble
    en hora punta.
    """
    if any(local in (host or "") for local in LOCALES):
        return Precio(0.0, 0.0)
    tabla = EMBEDDINGS if tipo == "embedding" else LENGUAJE
    base = _nombre_base(modelo)
    encontrado = tabla.get(base) or tabla.get(modelo)
    if encontrado is None:
        return None
    if base.startswith("deepseek-") and _es_punta_deepseek(
        momento or datetime.now(timezone.utc)
    ):
        return Precio(encontrado.entrada * 2, encontrado.salida * 2)
    return encontrado


def coste(p: Optional[Precio], entrada: int, salida: int) -> Optional[float]:
    """USD de una llamada. ``None`` si no hay precio."""
    if p is None:
        return None
    return (entrada * p.entrada + salida * p.salida) / 1_000_000


__all__ = ["COMPROBADO", "EMBEDDINGS", "LENGUAJE", "Precio", "coste", "precio"]
