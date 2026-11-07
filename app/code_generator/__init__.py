# app/code_generator/__init__.py
"""
Paquete de GENERACIÓN AUTOMÁTICA DE CÓDIGO de DevForge AI — CICLO 2.

En el Ciclo 1 este paquete generaba SOLO el backend (Spring Boot + JPA +
PostgreSQL, GENERATED_BACKEND_* del config) con generator_service y
mapping_engine. En el Ciclo 2 el módulo F se extiende al FRONTEND (CU24):
generador_frontend_service (Tanda 17, en app/services/) produce un
proyecto React + Vite + TypeScript con CRUD por cada clase UML del
diagrama, usando las plantillas Jinja2 de templates_react/.

Contenido por tanda (Ciclo 2):
- Tanda 17: templates_react/ (plantillas .j2 del frontend React) y
  app/services/generador_frontend_service.py (el service que las consume).
- Tanda 18: generator_service.py ⭐ y mapping_engine.py ⭐ RECONVERTIDOS
  desde los textos del Ciclo 1 (SQLAlchemy → Beanie: el trabajo se
  registra como TrabajoGeneracionCodigo con entidades_generadas +
  reglas_mapeo EMBEBIDAS), postman_export.py (igual que el Ciclo 1, es
  puro) y el paquete app/utils (validadores + GATE FORMAL
  ProblemaModelo). templates/ conserva las 8 plantillas .jinja del
  backend Spring Boot con el MISMO contrato de contextos que el Ciclo 1
  (package_base, artifact, java_version, spring_boot_version,
  postgres_version, diagrama_nombre, trabajo_id, entidad).

Exports (mismos nombres que el Ciclo 1 para no romper a los routers):
- MappingEngine / mapping_engine: motor de mapeo UML → Java/SQL.
- GeneratorService: orquestador de la generación Spring Boot.

Convención de la carpeta de salida: settings.GENERATED_PROJECTS_DIR es la
raíz; cada generación crea su propia subcarpeta (fecha + id del diagrama:
NUNCA sobrescribe) y el ZIP junto a ella.
TrabajoGeneracionCodigo.ruta_salida guarda la ruta RELATIVA a
GENERATED_PROJECTS_DIR (el nombre del ZIP).
"""

from app.code_generator.mapping_engine import MappingEngine, mapping_engine
from app.code_generator.generator_service import GeneratorService

__all__ = ["MappingEngine", "mapping_engine", "GeneratorService"]