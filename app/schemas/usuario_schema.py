# app/schemas/usuario_schema.py
"""
Esquemas Pydantic del módulo A. Usuarios y Seguridad.

Convención:
- *Base       → campos compartidos
- *Create     → entrada para creación
- *Update     → entrada para actualización parcial (todos opcionales)
- *Response   → salida hacia el cliente (nunca expone password_hash)

Cambios respecto al Ciclo 1:
- id pasa de int (serial de PostgreSQL) a PydanticObjectId; Beanie lo
  serializa como string hex en JSON, así que el frontend y el móvil
  siguen recibiendo un string.
- RolGlobal incorpora "LIDER": el modelo Usuario del Ciclo 2 reconoce
  explícitamente al Líder de Proyecto (además de ADMIN y DESARROLLADOR).
- from_attributes=True sigue siendo válido: los Document de Beanie son
  modelos pydantic, por lo que UsuarioResponse.model_validate(usuario)
  funciona directo y NUNCA expone password_hash (el campo no se declara
  en el esquema de salida).
"""

from datetime import datetime
from typing import Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# Tipos reutilizables (alineados con app/models/usuario.py)
RolGlobal = Literal["ADMIN", "LIDER", "DESARROLLADOR"]


# ======================================================================
# Base
# ======================================================================
class UsuarioBase(BaseModel):
    nombre_completo: str = Field(
        ..., min_length=1, max_length=150, description="Nombre visible del usuario"
    )
    email: EmailStr = Field(..., description="Correo usado para login")


# ======================================================================
# Create
# ======================================================================
class UsuarioCreate(UsuarioBase):
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Contraseña en texto plano (se hashea antes de persistir)",
    )
    rol: RolGlobal = Field(
        default="DESARROLLADOR",
        description="Rol global del usuario en la plataforma",
    )


# ======================================================================
# Update (parcial)
# ======================================================================
class UsuarioUpdate(BaseModel):
    nombre_completo: Optional[str] = Field(None, min_length=1, max_length=150)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    rol: Optional[RolGlobal] = None
    activo: Optional[bool] = None


# ======================================================================
# Response
# ======================================================================
class UsuarioResponse(UsuarioBase):
    model_config = ConfigDict(from_attributes=True)

    id: PydanticObjectId  # string hex en JSON (antes int serial)
    rol: RolGlobal
    activo: bool
    created_at: datetime


# ======================================================================
# Autenticación
# ======================================================================
class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """Respuesta estándar del endpoint de login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(
        ..., description="Segundos de validez del access token"
    )
    usuario: UsuarioResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PasswordChange(BaseModel):
    """Cambio de contraseña por el propio usuario autenticado."""

    password_actual: str = Field(..., min_length=1, max_length=128)
    password_nueva: str = Field(..., min_length=8, max_length=128)