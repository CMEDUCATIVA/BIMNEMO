"""Cuánto se ha gastado en IA: tokens y coste por día, tarea y modelo.

Aparte del resto de rutas de BIMNEMO porque responde a otra pregunta: no
«qué hay en la memoria» sino «cuánto me está costando». Los datos los reúne
``bimnemo/consumo.py`` en cada llamada real al proveedor.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from lightrag.api.bimnemo import consumo

from ..utils_api import get_combined_auth_dependency


class UsageResponse(BaseModel):
    rows: list[dict[str, Any]] = Field(
        description=(
            "Una fila por día, tipo (llm/embedding), tarea y modelo: llamadas, "
            "tokens de entrada y salida, coste en USD y si falta el precio"
        )
    )
    totals: dict[str, dict[str, Any]] = Field(
        description="Totales de hoy (today), 7 días (week) y 30 días (month)"
    )
    prices_checked: str = Field(description="Fecha en que se comprobaron los precios")
    revision: int = Field(
        description="Cambia con cada llamada contada; sirve para saber si repintar"
    )


def create_bimnemo_usage_routes(api_key: Optional[str] = None) -> APIRouter:
    """Sin prefijo propio: se monta dentro del router de BIMNEMO."""
    combined_auth = get_combined_auth_dependency(api_key)
    router = APIRouter(tags=["bimnemo"])

    @router.get(
        "/usage",
        response_model=UsageResponse,
        dependencies=[Depends(combined_auth)],
        summary="Consumo y coste de la IA por día y modelo",
    )
    async def get_usage(
        days: int = Query(default=30, ge=1, le=366, description="Días hacia atrás"),
    ) -> UsageResponse:
        """Lo que se ha gastado, medido con el ``usage`` que devuelve cada proveedor.

        El coste es un techo: no descuenta la entrada que el proveedor sirve
        desde su caché, porque el contador no recibe ese dato.
        """
        return UsageResponse(**consumo.REGISTRO.resumen(days))

    return router


__all__ = ["create_bimnemo_usage_routes"]
