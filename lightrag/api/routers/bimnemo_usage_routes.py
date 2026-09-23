"""Cuánto se ha gastado en IA: tokens y coste por día, tarea y modelo.

Aparte del resto de rutas de BIMNEMO porque responde a otra pregunta: no
«qué hay en la memoria» sino «cuánto me está costando». Los datos los reúne
``bimnemo/consumo.py`` en cada llamada real al proveedor.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from lightrag.api.bimnemo import consumo

from ..utils_api import get_combined_auth_dependency


class UsageResponse(BaseModel):
    rows: list[dict[str, Any]] = Field(
        description=(
            "Una fila por día, tipo (llm/embedding), tarea, modelo y archivo "
            "(vacío fuera de una indexación): llamadas, tokens de entrada y "
            "salida, coste en USD y si falta el precio"
        )
    )
    totals: dict[str, dict[str, Any]] = Field(
        description="Totales de hoy (today), 7 días (week) y 30 días (month)"
    )
    nemo: str = Field(
        default="", description="NEMO de la que se está contando el gasto"
    )
    nemo_name: str = Field(default="", description="Su nombre, para la pantalla")
    scope: str = Field(
        default="nemo",
        description="`nemo`: solo esta memoria. `all`: todas, más lo de antes de medirlas",
    )
    other_rows: int = Field(
        default=0,
        description=(
            "Filas del periodo que quedan fuera del filtro: de otras memorias "
            "o de antes de que se midiera por memoria"
        ),
    )
    prices_checked: str = Field(description="Fecha en que se comprobaron los precios")
    revision: int = Field(
        description="Cambia con cada llamada contada; sirve para saber si repintar"
    )
    restart_required: bool = Field(
        default=False,
        description=(
            "Hay configuración guardada que el motor todavía no usa: lo que se "
            "gaste ahora se gasta con lo de antes"
        ),
    )
    running_model: str = Field(
        default="", description="Modelo de lenguaje con el que corre el motor"
    )
    saved_model: str = Field(
        default="", description="Modelo de lenguaje guardado en la configuración"
    )


def create_bimnemo_usage_routes(
    api_key: Optional[str] = None, registry=None
) -> APIRouter:
    """Sin prefijo propio: se monta dentro del router de BIMNEMO.

    ``registry`` es el índice de NEMOs; sirve para dos cosas: dar por buena
    la memoria que se pide y poner su nombre. Sin él —un servidor sin
    memorias múltiples— todo el gasto es de la memoria heredada.
    """
    combined_auth = get_combined_auth_dependency(api_key)
    router = APIRouter(tags=["bimnemo"])

    def _nombre_de(nemo_id: str) -> str:
        if registry is None:
            return ""
        entrada = registry.get(nemo_id)
        return getattr(entrada, "name", "") if entrada is not None else ""

    @router.get(
        "/usage",
        response_model=UsageResponse,
        dependencies=[Depends(combined_auth)],
        summary="Consumo y coste de la IA por día y modelo",
    )
    async def get_usage(
        days: int = Query(default=30, ge=1, le=366, description="Días hacia atrás"),
        nemo: Optional[str] = Query(
            default=None, description="NEMO a contar; por defecto, la activa"
        ),
        scope: str = Query(
            default="nemo",
            pattern="^(nemo|all)$",
            description="`nemo`: solo esta memoria. `all`: la cuenta entera",
        ),
    ) -> UsageResponse:
        """Lo que se ha gastado, medido con el ``usage`` que devuelve cada proveedor.

        **Por memoria.** Cada llamada apunta en qué NEMO se gastó, y por
        defecto se cuenta solo la abierta: con varias memorias, «cuánto me
        cuesta esta» es la pregunta que se hace quien mira. ``scope=all`` da
        la cuenta entera, que es la que cuadra con la factura del proveedor,
        y es donde sale lo contado antes de que se midiera por memoria.

        El coste es un techo: no descuenta la entrada que el proveedor sirve
        desde su caché, porque el contador no recibe ese dato.

        Dice también si lo guardado no es lo que usa el motor. Existe por un
        caso real: se guardó `deepseek-flash`, no se reinició, y la tabla
        enseñaba `deepseek-v4-pro` sin que nada explicara por qué.
        """
        from lightrag.api.bimnemo.envfile import read_env

        from .bimnemo_settings_routes import _env_path, _settings_differ_from_running

        nemo_id = nemo or ""
        if registry is not None:
            try:
                nemo_id = registry.resolve(nemo)
            except Exception as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        datos = consumo.REGISTRO.resumen(
            days, nemo=nemo_id, solo_de_una=scope != "all"
        )
        # En la vista de todas, cada fila dice de qué memoria es. Con el
        # identificador no basta: la memoria heredada es la cadena vacía.
        nombres = (
            {n.id: n.name for n in registry.list()} if registry is not None else {}
        )
        for fila in datos["rows"]:
            marca = fila.get("nemo")
            fila["nemo_name"] = (
                nombres.get(marca, "") if isinstance(marca, str) else ""
            )

        guardado = read_env(_env_path())
        return UsageResponse(
            **datos,
            nemo=nemo_id,
            nemo_name=_nombre_de(nemo_id),
            scope=scope,
            restart_required=_settings_differ_from_running(guardado),
            running_model=os.getenv("LLM_MODEL", ""),
            saved_model=guardado.get("LLM_MODEL", ""),
        )

    @router.delete(
        "/usage",
        dependencies=[Depends(combined_auth)],
        summary="Quitar una fila de la tabla de consumo",
    )
    async def delete_usage(
        id: str = Query(description="El `id` de la fila, tal como lo da GET /usage"),
    ) -> dict[str, Any]:
        """Borra una fila del registro de consumo de BIMNEMO.

        Solo del registro: lo que el proveedor ya cobró sigue cobrado. Sirve
        para limpiar pruebas o lo que ya no interesa seguir mirando.
        """
        if not consumo.REGISTRO.borrar(id):
            raise HTTPException(status_code=404, detail="Esa fila ya no está.")
        return {"status": "deleted", "message": "Fila quitada de la tabla."}

    return router


__all__ = ["create_bimnemo_usage_routes"]
