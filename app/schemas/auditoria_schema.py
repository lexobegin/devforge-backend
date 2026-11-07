# app/schemas/auditoria_schema.py
"""
Esquemas Pydantic del módulo de Auditoría — CICLO 2:

- BitacoraSistemaResponse → salida de eventos de bitácora
- DTOs para exportación (no se serializan, la respuesta es un archivo)

Cambios respecto al Ciclo 1 (SQLAlchemy → Beanie/MongoDB):
- id (serial int) → PydanticObjectId: se serializa como string hex en JSON.
- id_usuario (int, FK con ondelete SET NULL) → Optional[PydanticObjectId]:
  None significa que el evento lo disparó el propio sistema (mismo
  significado que el NULL del Ciclo 1, sin ON DELETE).
- id_entidad_afectada (BIGINT polimórfico, sin FK) → Optional[str]:
  str(id) de un Document o id uuid de un elemento embebido, según
  `entidad_afectada`.
"""

from datetime import datetime
from typing import Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict


class BitacoraSistemaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId
    id_usuario: Optional[PydanticObjectId] = None
    tipo_evento: str
    descripcion: str
    entidad_afectada: Optional[str] = None
    id_entidad_afectada: Optional[str] = None
    created_at: datetime