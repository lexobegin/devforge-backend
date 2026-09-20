# app/utils/validators.py
"""
Validaciones UML 2.5+ reutilizables por servicios y routers.

Todas lanzan `ValidationError` (de app.core.exceptions) cuando fallan,
y devuelven el valor normalizado cuando pasan.
"""

import re
from typing import Optional

from app.core.exceptions import ValidationError


# ----------------------------------------------------------------------
# Patrones
# ----------------------------------------------------------------------
# Identificador UML: letra inicial, luego letras/dígitos/guion_bajo.
_IDENTIFICADOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# Multiplicidades típicas: 1, 0..1, *, 0..*, 1..*, n, 1..n, 2..5
_MULTIPLICIDADES_FIJAS = {"1", "0..1", "*", "0..*", "1..*", "n", "1..n"}
_MULTIPLICIDAD_RANGO_RE = re.compile(r"^\d+\.\.\d+$")

# Visibilidades UML
_VISIBILIDADES = {"+", "-", "#", "~"}

# Estereotipo: <<nombre>> (guardamos "nombre" sin los ángulos)
_ESTEREOTIPO_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\- ]{0,48}$")


# ----------------------------------------------------------------------
# Validadores
# ----------------------------------------------------------------------
def validar_identificador_uml(nombre: str, *, campo: str = "nombre") -> str:
    """
    Valida que el nombre sea un identificador UML aceptable:
    empieza con letra, sigue con letras/dígitos/_, y no está vacío.
    Devuelve el nombre sin espacios extremos.
    """
    if not nombre or not nombre.strip():
        raise ValidationError(f"El {campo} no puede estar vacío")

    n = nombre.strip()
    if not _IDENTIFICADOR_RE.match(n):
        raise ValidationError(
            f"El {campo} '{nombre}' no es un identificador UML válido "
            "(debe empezar con letra y contener solo letras, dígitos y _)"
        )
    return n


def validar_multiplicidad(multiplicidad: Optional[str]) -> Optional[str]:
    """
    Valida multiplicidad UML. Acepta None (sin multiplicidad).
    Formatos aceptados: 1, 0..1, *, 0..*, 1..*, n, 1..n, 2..5, etc.
    """
    if multiplicidad is None:
        return None

    m = multiplicidad.strip()
    if m in _MULTIPLICIDADES_FIJAS:
        return m
    if _MULTIPLICIDAD_RANGO_RE.match(m):
        return m
    raise ValidationError(f"Multiplicidad inválida: '{multiplicidad}'")


def validar_visibilidad(visibilidad: str) -> str:
    """Valida visibilidad UML: +, -, #, ~."""
    if visibilidad not in _VISIBILIDADES:
        raise ValidationError(
            f"Visibilidad inválida: '{visibilidad}'. "
            "Use uno de: +, -, #, ~"
        )
    return visibilidad


def validar_estereotipo(estereotipo: Optional[str]) -> Optional[str]:
    """
    Valida estereotipo UML. Acepta None.
    Acepta tanto '<<entity>>' como 'entity' (devuelve 'entity').
    """
    if estereotipo is None or not estereotipo.strip():
        return None

    e = estereotipo.strip()
    # Quitar << >> si vienen incluidos
    if e.startswith("<<") and e.endswith(">>"):
        e = e[2:-2].strip()

    if not _ESTEREOTIPO_RE.match(e):
        raise ValidationError(
            f"Estereotipo inválido: '{estereotipo}'"
        )
    return e


def validar_tipo_dato(tipo: str) -> str:
    """
    Valida tipo de dato UML. Es flexible: acepta primitivos (String,
    Integer, Date, Boolean…), tipos genéricos (List<String>), o nombres
    de clases del propio diagrama.
    """
    if not tipo or not tipo.strip():
        raise ValidationError("El tipo de dato no puede estar vacío")
    t = tipo.strip()
    if len(t) > 50:
        raise ValidationError("El tipo de dato excede los 50 caracteres")
    # No hacer regex estricto aquí: permitimos "List<String>", etc.
    return t