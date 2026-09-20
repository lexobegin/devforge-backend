# app/schemas/auditoria_schema.py
"""
Esquemas Pydantic del módulo de Auditoría:

- BitacoraSistemaResponse → salida de eventos de bitácora
- DTOs para exportación (no se serializan, la respuesta es un archivo)
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BitacoraSistemaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_usuario: Optional[int] = None
    tipo_evento: str
    descripcion: str
    entidad_afectada: Optional[str] = None
    id_entidad_afectada: Optional[int] = None
    created_at: datetime