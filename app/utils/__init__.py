# app/utils/__init__.py
"""
Utilidades transversales de DevForge AI — CICLO 2 (paquete NUEVO).

En el Ciclo 1 existía app/utils/validators.py suelto para los routers del
módulo C. En el Ciclo 2 el paquete se formaliza porque el generador de
backend (CU6, Tanda 18) comparte el mismo gate de validación:

- validators.validar_identificador_uml / validar_multiplicidad /
  validar_visibilidad / validar_estereotipo / validar_tipo_dato
  → validadores puntuales que LANZAN ValidationError (mismos mensajes
  que el Ciclo 1).
- validators.ProblemaModelo + validar_diagrama_para_generar + hay_errores
  + formatear_problemas → GATE FORMAL de generación: recorre el diagrama,
  COLECTA todos los hallazgos (ERROR/ADVERTENCIA) y el generador rechaza
  si hay al menos un ERROR.

El paquete NO depende de Beanie: todo lo de aquí es puro (testeable sin
base de datos).
"""

from app.utils.validators import (
    ProblemaModelo,
    formatear_problemas,
    hay_errores,
    validar_diagrama_para_generar,
    validar_estereotipo,
    validar_identificador_uml,
    validar_multiplicidad,
    validar_tipo_dato,
    validar_visibilidad,
)

__all__ = [
    "ProblemaModelo",
    "formatear_problemas",
    "hay_errores",
    "validar_diagrama_para_generar",
    "validar_estereotipo",
    "validar_identificador_uml",
    "validar_multiplicidad",
    "validar_tipo_dato",
    "validar_visibilidad",
]