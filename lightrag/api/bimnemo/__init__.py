"""BIMNEMO — capa de aplicación local sobre el motor LightRAG.

BIMNEMO no reimplementa nada del motor: clasifica lo que el usuario sube,
agrega métricas sobre lo que LightRAG ya almacena, y publica una superficie
de memoria estable para que otros agentes se conecten.

El paquete es estrictamente aditivo. Si se elimina, el servidor LightRAG se
comporta exactamente igual que antes.

Módulos:
- ``catalog``: extensión de fichero -> categoría y tipo (catálogo BIM).
- ``stats``: agregación de las métricas del panel a partir del disco y de
  los almacenes del motor.

La superficie REST vive en ``lightrag.api.routers.bimnemo_routes``, siguiendo
el patrón de factoría por router del proyecto.
"""

from __future__ import annotations

BIMNEMO_NAME = "BIMNEMO"
def _version() -> str:
    """La versión instalada, del fichero ``VERSION`` de la raíz.

    Una sola fuente. Antes esto era una constante y el fichero ``VERSION`` era
    otra cosa: la constante se quedó en «1.0.0» mientras se publicaba la
    v1.1.0, así que la pestaña Motor llevaba una versión entera mintiendo sin
    que nadie lo notara.

    El fichero es el que escribe el instalador y el que compara el
    actualizador, así que es el que manda. Se le quita la ``v`` de la etiqueta
    porque un número de versión no la lleva.

    Si no existe —ejecutando desde una copia sin empaquetar— se cae a
    ``FALLBACK``, que es peor que el fichero pero mejor que reventar al
    arrancar.
    """
    from pathlib import Path

    fichero = Path(__file__).resolve().parents[3] / "VERSION"
    try:
        crudo = fichero.read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK
    if not crudo:
        return _FALLBACK
    return crudo[1:] if crudo.startswith("v") else crudo


#: Lo que se dice cuando no hay fichero `VERSION` que leer.
_FALLBACK = "0.0.0-desarrollo"

BIMNEMO_VERSION = _version()

__all__ = ["BIMNEMO_NAME", "BIMNEMO_VERSION"]
