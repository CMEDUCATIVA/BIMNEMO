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
BIMNEMO_VERSION = "1.0.0"

__all__ = ["BIMNEMO_NAME", "BIMNEMO_VERSION"]
