# app/code_generator/templates_react/__init__.py
"""
Plantillas Jinja2 del FRONTEND React generado (módulo F, CU24) — CICLO 2.

ARCHIVO NUEVO del Ciclo 2: generador_frontend_service renderiza estas
plantillas para producir un proyecto React + Vite + TypeScript con un
CRUD (listado + formulario + cliente API + tipos) por cada clase UML del
diagrama. Jinja2 ya estaba en requirements ("Plantillas (generación
Spring Boot Ciclo 1 + React CRUD Ciclo 2): jinja2").

Convenciones:
- Nombres PLANOS de archivo .j2 (src_main.tsx.j2 → src/main.tsx): el
  FileSystemLoader no anida carpetas y el mapa de salida lo decide el
  service (ruta destino por plantilla).
- El entorno se crea con trim_blocks/lstrip_blocks (salida limpia al
  recorrer entidades con {% for %}), keep_trailing_newline y autoescape
  desactivado (se genera CÓDIGO, no HTML para servir).
- Los contextos los arma el service (entidades con nombre PascalCase,
  recurso kebab-case, atributos con tipo_ts/tipo_input ya mapeados).

Listas de plantillas (el service las recorre por si el árbol cambia):
- PLANTILLAS_PROYECTO: se renderizan UNA vez por generación (esqueleto).
- PLANTILLAS_ENTIDAD: se renderizan UNA vez POR clase UML del diagrama.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# Carpeta de las plantillas .j2 (este mismo directorio del paquete).
CARPETA_PLANTILLAS = Path(__file__).resolve().parent

# Esqueleto del proyecto (una sola vez por generación).
PLANTILLAS_PROYECTO: tuple = (
    "package.json.j2",
    "vite.config.ts.j2",
    "index.html.j2",
    "src_main.tsx.j2",
    "src_App.tsx.j2",
    "src_api_client.ts.j2",
    "README.md.j2",
)

# CRUD por cada clase UML del diagrama (una renderización por entidad).
PLANTILLAS_ENTIDAD: tuple = (
    "src_tipos_entidad.ts.j2",
    "src_api_entidad.ts.j2",
    "src_componentes_lista.tsx.j2",
    "src_componentes_formulario.tsx.j2",
)


def entorno_jinja() -> Environment:
    """
    Entorno Jinja2 de las plantillas React (autoescape OFF: se genera
    código fuente, no HTML para servir; trim/lstrip para que los
    {% for %} de entidades no dejen líneas en blanco).
    """
    return Environment(
        loader=FileSystemLoader(str(CARPETA_PLANTILLAS)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )