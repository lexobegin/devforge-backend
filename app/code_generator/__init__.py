# app/code_generator/__init__.py
"""
Motor de generación automática de backend Spring Boot (Capa 2).

Módulo independiente al mismo nivel que `services/`:
- mapping_engine: traduce tipos UML a tipos Java/PostgreSQL y aplica reglas
  de mapeo objeto-relacional.
- generator_service: orquesta el proceso completo a partir de un Diagrama
  ORM y produce una carpeta autocontenida en `generated_projects/{id}/`.
- postman_export: genera la colección Postman del backend producido.
- templates: plantillas Jinja2 para cada archivo Java del proyecto generado.

No acumula estado entre generaciones: cada ejecución produce una carpeta
autocontenida y descargable.
"""

from app.code_generator.mapping_engine import MappingEngine, mapping_engine
from app.code_generator.generator_service import GeneratorService

__all__ = ["MappingEngine", "mapping_engine", "GeneratorService"]