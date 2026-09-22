"""Cuánto «piensa» el modelo antes de contestar: de la barra a las variables.

Existe por una factura: `deepseek-v4-pro` piensa por defecto, y ese
razonamiento oculto se cobra como tokens de salida. Una ley de 49 fragmentos
costó unos 4 USD; sin razonar, el mismo trabajo cuesta céntimos.

## Dos barras, no una

- **Al extraer** (roles ``EXTRACT`` y ``KEYWORD``): indexar documentos y sacar
  las palabras clave de cada pregunta. Es casi todo el gasto, y es rellenar
  una plantilla: pensar apenas aporta.
- **Al responder** (rol ``QUERY``): la respuesta del chat. Pocos tokens, y ahí
  sí se nota.

## Cómo llega al proveedor

No se inventa nada: LightRAG ya lee opciones por rol con el patrón
``{ROL}_{BINDING}_{CAMPO}`` (``binding_options.options_dict_for_role``), y el
conector de OpenAI reenvía ``reasoning_effort`` y ``extra_body`` tal cual.
Este módulo solo traduce un nivel elegido a esas variables.

## Por modelo, no por proveedor

Dentro de OpenAI, ``minimal`` da un 400 en ``gpt-5.6-*`` y ``none`` da un 400
en ``gpt-5-nano``. Un nivel que un modelo no admite no es «un poco peor»: es
**que falle cada llamada**. Por eso cada modelo lleva sus propios niveles, y
un modelo que no está aquí no enseña barra.

**«Lo que decida el modelo» no escribe nada.** Es la única opción que no
puede romper nada, y la que queda si se cambia a un modelo sin control.

Valores comprobados en la documentación oficial de cada proveedor el
2026-09-21 (DeepSeek, OpenAI, Google, Alibaba, Z.ai, OpenRouter, xAI,
Ollama). Anthropic se deja fuera: su capa compatible con OpenAI ignora
``reasoning_effort`` sin avisar.
"""

from __future__ import annotations

import json
from typing import Any, NamedTuple, Optional

# --- Variables ---------------------------------------------------------------

EFFORT = "OPENAI_LLM_REASONING_EFFORT"
EXTRA_BODY = "OPENAI_LLM_EXTRA_BODY"
GEMINI = "GEMINI_LLM_THINKING_CONFIG"
OLLAMA = "OLLAMA_LLM_THINK"
BASES = (EFFORT, EXTRA_BODY, GEMINI, OLLAMA)

#: Cada barra y los roles del motor que gobierna.
BARRAS = {
    "indexar": ("EXTRACT", "KEYWORD"),
    "responder": ("QUERY",),
}

#: Todas las variables que esta pantalla escribe. Se comentan TODAS en cada
#: guardado antes de escribir las que tocan: si no, pasar de DeepSeek a
#: OpenAI dejaría ``{"thinking": …}`` puesto y OpenAI contestaría 400.
GESTIONADAS = frozenset(
    f"{rol}_{base}" for roles in BARRAS.values() for rol in roles for base in BASES
)

#: El nivel que no escribe nada.
DEFECTO = ""
#: Hay algo puesto a mano que no es ningún nivel de la barra: se conserva.
MANUAL = "manual"


class Nivel(NamedTuple):
    id: str
    rotulo: str
    variables: dict[str, str]  # variable base (sin rol) -> valor


class Esquema(NamedTuple):
    niveles: tuple[Nivel, ...]
    nota: str = ""


def _json(valor: dict[str, Any]) -> str:
    return json.dumps(valor, separators=(",", ":"))


def _defecto() -> Nivel:
    return Nivel(DEFECTO, "Lo que decida el modelo", {})


def _effort(*valores: tuple[str, str], nota: str = "") -> Esquema:
    return Esquema((_defecto(), *(Nivel(v, r, {EFFORT: v}) for v, r in valores)), nota)


APAGADO = "Apagado"
MINIMO, BAJO, MEDIO, ALTO, MUY_ALTO = "Mínimo", "Bajo", "Medio", "Alto", "Muy alto"

# --- Esquemas ----------------------------------------------------------------

_DEEPSEEK = Esquema(
    (
        _defecto(),
        Nivel("off", APAGADO, {EXTRA_BODY: _json({"thinking": {"type": "disabled"}})}),
        Nivel(
            "low",
            BAJO,
            {EXTRA_BODY: _json({"thinking": {"type": "enabled"}}), EFFORT: "low"},
        ),
        Nivel(
            "high",
            ALTO,
            {EXTRA_BODY: _json({"thinking": {"type": "enabled"}}), EFFORT: "high"},
        ),
    ),
    "DeepSeek piensa por defecto, a nivel alto.",
)

_QWEN = Esquema(
    (
        _defecto(),
        Nivel("off", APAGADO, {EXTRA_BODY: _json({"enable_thinking": False})}),
        Nivel("on", "Encendido", {EXTRA_BODY: _json({"enable_thinking": True})}),
    ),
    "Pensando, Qwen puede devolver JSON mal formado al indexar.",
)

_GLM = Esquema(
    (
        _defecto(),
        Nivel("off", APAGADO, {EXTRA_BODY: _json({"thinking": {"type": "disabled"}})}),
        Nivel(
            "on", "Encendido", {EXTRA_BODY: _json({"thinking": {"type": "enabled"}})}
        ),
    ),
)

_OPENROUTER = Esquema(
    (
        _defecto(),
        *(
            Nivel(v, r, {EXTRA_BODY: _json({"reasoning": {"effort": v}})})
            for v, r in (
                ("none", APAGADO),
                ("low", BAJO),
                ("medium", MEDIO),
                ("high", ALTO),
            )
        ),
    ),
    "Con un modelo que no razona, OpenRouter lo ignora.",
)


def _gemini_presupuesto(*valores: tuple[int, str], nota: str = "") -> Esquema:
    return Esquema(
        (
            _defecto(),
            *(
                Nivel(str(n), r, {GEMINI: _json({"thinking_budget": n})})
                for n, r in valores
            ),
        ),
        nota,
    )


def _gemini_nivel(*valores: tuple[str, str], nota: str = "") -> Esquema:
    return Esquema(
        (
            _defecto(),
            *(Nivel(v, r, {GEMINI: _json({"thinking_level": v})}) for v, r in valores),
        ),
        nota,
    )


_GEMINI_25_FLASH = _gemini_presupuesto(
    (0, APAGADO), (1024, BAJO), (8192, MEDIO), (24576, ALTO)
)
_GEMINI_3_MIN = _gemini_nivel(
    ("minimal", MINIMO),
    ("low", BAJO),
    ("medium", MEDIO),
    ("high", ALTO),
    nota="En la serie 3 «Mínimo» es casi no pensar; apagarlo del todo no se puede.",
)
_GEMINI_3 = _gemini_nivel(
    ("low", BAJO),
    ("medium", MEDIO),
    ("high", ALTO),
    nota="Este modelo no deja apagar el razonamiento; lo mínimo es «Bajo».",
)

_OLLAMA_SI_NO = Esquema(
    (
        _defecto(),
        Nivel("off", APAGADO, {OLLAMA: "false"}),
        Nivel("on", "Encendido", {OLLAMA: "true"}),
    ),
)
_OLLAMA_NIVELES = Esquema(
    (
        _defecto(),
        *(
            Nivel(v, r, {OLLAMA: v})
            for v, r in (("low", BAJO), ("medium", MEDIO), ("high", ALTO))
        ),
    ),
    "gpt-oss no deja apagarlo; lo mínimo es «Bajo».",
)


def esquema(proveedor: str, modelo: str) -> Optional[Esquema]:
    """Los niveles que admite ``modelo`` en ``proveedor``; ``None`` si no hay control."""
    m = (modelo or "").strip().lower()
    base = m.rsplit("/", 1)[-1]

    if proveedor == "openai":
        if m == "gpt-5-nano":
            return _effort(
                ("minimal", MINIMO), ("low", BAJO), ("medium", MEDIO), ("high", ALTO)
            )
        if m.startswith("gpt-5.6-"):
            return _effort(
                ("none", APAGADO),
                ("low", BAJO),
                ("medium", MEDIO),
                ("high", ALTO),
                ("xhigh", MUY_ALTO),
            )
        if m == "gpt-6-astra":
            return _effort(
                ("low", BAJO),
                ("medium", MEDIO),
                ("high", ALTO),
                ("xhigh", MUY_ALTO),
                nota="Este modelo no deja apagar el razonamiento; lo mínimo es «Bajo».",
            )
        if m.startswith(("gpt-5", "gpt-6", "o3", "o4")):
            # Uno que el catálogo no conoce: solo los tres niveles que admite
            # toda la familia.
            return _effort(("low", BAJO), ("medium", MEDIO), ("high", ALTO))
        return None
    if proveedor == "deepseek":
        return _DEEPSEEK if m.startswith("deepseek-") else None
    if proveedor == "qwen":
        return _QWEN if m.startswith(("qwen-", "qwen3")) else None
    if proveedor == "zhipu":
        return _GLM if m.startswith(("glm-4.5", "glm-4.6", "glm-4.7")) else None
    if proveedor == "openrouter":
        return _OPENROUTER
    if proveedor == "gemini":
        if m in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
            return _GEMINI_25_FLASH
        if m == "gemini-2.5-pro":
            return _gemini_presupuesto(
                (1024, BAJO),
                (8192, MEDIO),
                (32768, ALTO),
                nota="Este modelo no deja apagar el razonamiento.",
            )
        if m.startswith(("gemini-3.5-flash", "gemini-3-flash")):
            return _GEMINI_3_MIN
        if m.startswith("gemini-3"):
            return _GEMINI_3
        return None
    if proveedor == "xai":
        if m in ("grok-4.5", "grok-4.6", "grok-4.7"):
            return _effort(
                ("low", BAJO),
                ("medium", MEDIO),
                ("high", ALTO),
                nota="Grok no deja apagar el razonamiento; lo mínimo es «Bajo».",
            )
        return None
    if proveedor == "groq":
        return (
            _effort(("low", BAJO), ("medium", MEDIO), ("high", ALTO))
            if "gpt-oss" in m
            else None
        )
    if proveedor == "ollama":
        # Ollama comprueba `think` al arrancar: a un modelo sin soporte, el
        # motor no arranca. Solo los que se sabe que piensan.
        if base.startswith(("qwen3", "deepseek-r1")):
            return _OLLAMA_SI_NO
        if base.startswith("gpt-oss"):
            return _OLLAMA_NIVELES
        return None
    return None


# --- Del .env a la barra y de la barra al .env --------------------------------


def valor_efectivo(crudo: Optional[str]) -> str:
    """Lo que verá el proceso tras cargar el ``.env``; ``""`` si no está.

    ``envfile`` guarda el JSON entre comillas dobles y con las internas
    escapadas; ``python-dotenv`` lo deshace al arrancar, aquí se deshace igual.
    """
    return (crudo or "").replace('\\"', '"').replace("\\\\", "\\")


def _valor(crudo: str) -> Any:
    """Lo que hay en el ``.env``, comparable con lo que escribiría la barra."""
    texto = valor_efectivo(crudo)
    try:
        return json.loads(texto)
    except ValueError:
        return texto


def leer(valores: dict[str, str], proveedor: str, modelo: str) -> dict[str, str]:
    """Qué nivel está puesto en cada barra: su id, ``""`` o :data:`MANUAL`."""
    e = esquema(proveedor, modelo)
    resultado: dict[str, str] = {}
    for barra, roles in BARRAS.items():
        rol = roles[0]
        puesto = {
            base: _valor(valores[f"{rol}_{base}"])
            for base in BASES
            if valores.get(f"{rol}_{base}")
        }
        if not puesto:
            resultado[barra] = DEFECTO
            continue
        encontrado = MANUAL
        for nivel in e.niveles if e else ():
            if nivel.variables and puesto == {
                k: _valor(v) for k, v in nivel.variables.items()
            }:
                encontrado = nivel.id
                break
        resultado[barra] = encontrado
    return resultado


def a_variables(
    proveedor: str, modelo: str, elegidos: dict[str, str]
) -> dict[str, Optional[str]]:
    """Las variables a escribir: ``None`` comenta la línea (``write_env``).

    Nunca se escribe una cadena vacía: ``options_dict_for_role`` la mandaría
    al proveedor como ``extra_body=""``. Una barra en :data:`MANUAL` no se
    toca: es un ajuste hecho a mano que la barra no sabe representar.
    """
    e = esquema(proveedor, modelo)
    cambios: dict[str, Optional[str]] = {}
    for barra, roles in BARRAS.items():
        elegido = elegidos.get(barra, DEFECTO)
        if elegido == MANUAL:
            continue
        for rol in roles:
            for base in BASES:
                cambios[f"{rol}_{base}"] = None
        nivel = next((n for n in (e.niveles if e else ()) if n.id == elegido), None)
        if nivel is None:
            continue
        for rol in roles:
            for base, valor in nivel.variables.items():
                cambios[f"{rol}_{base}"] = valor
    return cambios


#: Cada variable, con el nombre del campo que le llega al binding tras
#: ``options_dict_for_role`` (el sufijo en minúsculas).
_CAMPO = {
    EFFORT: "reasoning_effort",
    EXTRA_BODY: "extra_body",
    GEMINI: "thinking_config",
    OLLAMA: "think",
}

#: Rótulos para la tabla de consumo cuando no hay un nivel de la barra.
SIN_CONTROL = "Sin control"
A_MANO = "Ajuste a mano"


def nivel_de_opciones(proveedor: str, modelo: str, opciones: dict[str, Any]) -> str:
    """El nivel, en palabras, que corresponde a las opciones con que se llama.

    Es el camino de vuelta de :func:`a_variables`: la tabla de consumo lo
    apunta en cada llamada, para ver después con qué nivel se gastó qué.
    """
    e = esquema(proveedor, modelo)
    puestas = {
        base: opciones[campo]
        for base, campo in _CAMPO.items()
        if opciones.get(campo) not in (None, "", {})
    }
    if e is None:
        return A_MANO if puestas else SIN_CONTROL
    if not puestas:
        return e.niveles[0].rotulo
    for nivel in e.niveles:
        if nivel.variables and puestas == {
            k: _valor(v) for k, v in nivel.variables.items()
        }:
            return nivel.rotulo
    return A_MANO


def aplicar_en_caliente(
    instancias: list[Any], cambios: dict[str, Optional[str]]
) -> list[str]:
    """Aplica el nuevo nivel a las memorias abiertas, **sin reiniciar**.

    Existe porque el usuario movió la barra con un documento indexándose y
    no pasó nada: el motor solo leía estas variables al arrancar, y reiniciar
    se niega con la tubería ocupada. LightRAG sí sabe cambiar las opciones de
    un rol en marcha (``update_llm_role_config``): monta la función nueva con
    el constructor registrado y retira la cola vieja **dejando terminar** lo
    que ya estaba en ella. Las llamadas siguientes salen con el nivel nuevo.

    ``cambios`` es lo que :func:`a_variables` escribió en el ``.env``. Se
    reflejan también en ``os.environ``: así una memoria que se abra después
    —que construye sus roles leyendo el entorno— nace ya con el nivel nuevo,
    y «hay configuración sin aplicar» deja de ser verdad.

    Devuelve los roles que se actualizaron.
    """
    import os

    hechos: list[str] = []
    for roles in BARRAS.values():
        for rol in roles:
            campos = {
                campo: cambios[f"{rol}_{base}"]
                for base, campo in _CAMPO.items()
                if f"{rol}_{base}" in cambios
            }
            if not campos:
                continue
            for instancia in instancias:
                actual = instancia.get_llm_role_config(rol.lower())
                opciones = dict(
                    (actual.get("metadata") or {}).get("provider_options") or {}
                )
                for campo, valor in campos.items():
                    if valor is None:
                        opciones.pop(campo, None)
                    else:
                        opciones[campo] = _valor(valor)
                instancia.update_llm_role_config(rol.lower(), provider_options=opciones)
            hechos.append(rol.lower())

    for clave, valor in cambios.items():
        if clave not in GESTIONADAS:
            continue
        if valor is None:
            os.environ.pop(clave, None)
        else:
            os.environ[clave] = valor_efectivo(valor)
    return hechos


def para_catalogo(proveedor: str, modelos: tuple[str, ...]) -> dict[str, Any]:
    """Los niveles de cada modelo, tal como los pinta la ventana."""
    salida: dict[str, Any] = {}
    for modelo in modelos:
        e = esquema(proveedor, modelo)
        if e is not None:
            salida[modelo] = {
                "levels": [{"id": n.id, "label": n.rotulo} for n in e.niveles],
                "note": e.nota,
            }
    return salida


def niveles_de(proveedor: str, modelo: str) -> Optional[dict[str, Any]]:
    """Los niveles de un modelo cualquiera, también uno escrito a mano."""
    e = esquema(proveedor, modelo)
    if e is None:
        return None
    return {
        "levels": [{"id": n.id, "label": n.rotulo} for n in e.niveles],
        "note": e.nota,
    }


__all__ = [
    "BARRAS",
    "aplicar_en_caliente",
    "DEFECTO",
    "GESTIONADAS",
    "MANUAL",
    "a_variables",
    "esquema",
    "leer",
    "nivel_de_opciones",
    "niveles_de",
    "para_catalogo",
    "valor_efectivo",
]
