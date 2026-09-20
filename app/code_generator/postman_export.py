# app/code_generator/postman_export.py
"""
Generador de la colección Postman para el backend Spring Boot generado.

Estructura de la colección (schema v2.1.0):
{
  "info": {...},
  "variable": [
    {"key": "baseUrl", "value": "http://localhost:8080"}
  ],
  "item": [
    {
      "name": "<Entidad>",
      "item": [
        {"name": "List all", "request": {...}},
        {"name": "Get by id", "request": {...}},
        {"name": "Create", "request": {...}},
        {"name": "Update", "request": {...}},
        {"name": "Delete", "request": {...}}
      ]
    },
    ...
  ]
}

Cada entidad genera un folder con 5 requests: GET all, GET by id, POST,
PUT, DELETE. Los bodies de ejemplo se construyen a partir de los campos
mapeados (sin el id, que lo genera la base).

La colección resultante se serializa como JSON y se guarda en
`backend/postman/<artifact>.postman_collection.json`.
"""

import json
from typing import Any

from app.code_generator.mapping_engine import JavaEntity, MappingResult


# ======================================================================
# API pública
# ======================================================================
def generar_coleccion_postman(
    *,
    mapeo: MappingResult,
    nombre_proyecto: str = "backend",
    base_url: str = "http://localhost:8080",
) -> str:
    """
    Devuelve el contenido JSON (string) de la colección Postman
    correspondiente al backend generado.
    """
    coleccion = {
        "info": {
            "_postman_id": _uuid_like(),
            "name": f"{nombre_proyecto} — API generada por DevForge AI",
            "description": (
                "Colección autogenerada por DevForge AI. Contiene un folder "
                "por entidad con las operaciones CRUD básicas (GET all, "
                "GET by id, POST, PUT, DELETE)."
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [
            {
                "key": "baseUrl",
                "value": base_url,
                "type": "string",
            }
        ],
        "item": [
            _folder_entidad(entidad) for entidad in mapeo.entidades
        ],
    }
    return json.dumps(coleccion, indent=2, ensure_ascii=False)


# ======================================================================
# Construcción de un folder por entidad
# ======================================================================
def _folder_entidad(entidad: JavaEntity) -> dict[str, Any]:
    recurso = entidad.nombre_tabla      # ya está en plural y snake_case
    return {
        "name": entidad.nombre_clase_java,
        "description": f"CRUD para la entidad {entidad.nombre_clase_java} (tabla {entidad.nombre_tabla})",
        "item": [
            _req_list_all(entidad, recurso),
            _req_get_by_id(entidad, recurso),
            _req_create(entidad, recurso),
            _req_update(entidad, recurso),
            _req_delete(entidad, recurso),
        ],
    }


# ======================================================================
# Requests individuales
# ======================================================================
def _req_list_all(entidad: JavaEntity, recurso: str) -> dict[str, Any]:
    return {
        "name": f"List all {entidad.nombre_clase_java}",
        "request": {
            "method": "GET",
            "header": [],
            "url": {
                "raw": "{{baseUrl}}/api/" + recurso,
                "host": ["{{baseUrl}}"],
                "path": ["api", recurso],
            },
            "description": f"Devuelve todas las filas de {entidad.nombre_tabla}.",
        },
        "response": [],
    }


def _req_get_by_id(entidad: JavaEntity, recurso: str) -> dict[str, Any]:
    return {
        "name": f"Get {entidad.nombre_clase_java} by id",
        "request": {
            "method": "GET",
            "header": [],
            "url": {
                "raw": "{{baseUrl}}/api/" + recurso + "/:id",
                "host": ["{{baseUrl}}"],
                "path": ["api", recurso, ":id"],
                "variable": [
                    {
                        "key": "id",
                        "value": "1",
                        "description": "ID de la entidad a consultar",
                    }
                ],
            },
            "description": f"Devuelve una fila de {entidad.nombre_tabla} por su id.",
        },
        "response": [],
    }


def _req_create(entidad: JavaEntity, recurso: str) -> dict[str, Any]:
    body = _construir_body_ejemplo(entidad, incluir_id=False)
    return {
        "name": f"Create {entidad.nombre_clase_java}",
        "request": {
            "method": "POST",
            "header": [
                {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {
                "mode": "raw",
                "raw": json.dumps(body, indent=2, ensure_ascii=False),
                "options": {"raw": {"language": "json"}},
            },
            "url": {
                "raw": "{{baseUrl}}/api/" + recurso,
                "host": ["{{baseUrl}}"],
                "path": ["api", recurso],
            },
            "description": (
                f"Crea una nueva fila en {entidad.nombre_tabla}. "
                "El id lo genera la base de datos."
            ),
        },
        "response": [],
    }


def _req_update(entidad: JavaEntity, recurso: str) -> dict[str, Any]:
    body = _construir_body_ejemplo(entidad, incluir_id=False)
    return {
        "name": f"Update {entidad.nombre_clase_java}",
        "request": {
            "method": "PUT",
            "header": [
                {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {
                "mode": "raw",
                "raw": json.dumps(body, indent=2, ensure_ascii=False),
                "options": {"raw": {"language": "json"}},
            },
            "url": {
                "raw": "{{baseUrl}}/api/" + recurso + "/:id",
                "host": ["{{baseUrl}}"],
                "path": ["api", recurso, ":id"],
                "variable": [
                    {"key": "id", "value": "1"}
                ],
            },
            "description": f"Actualiza una fila de {entidad.nombre_tabla} por su id.",
        },
        "response": [],
    }


def _req_delete(entidad: JavaEntity, recurso: str) -> dict[str, Any]:
    return {
        "name": f"Delete {entidad.nombre_clase_java}",
        "request": {
            "method": "DELETE",
            "header": [],
            "url": {
                "raw": "{{baseUrl}}/api/" + recurso + "/:id",
                "host": ["{{baseUrl}}"],
                "path": ["api", recurso, ":id"],
                "variable": [
                    {"key": "id", "value": "1"}
                ],
            },
            "description": f"Elimina una fila de {entidad.nombre_tabla} por su id.",
        },
        "response": [],
    }


# ======================================================================
# Construcción del body de ejemplo
# ======================================================================
def _construir_body_ejemplo(
    entidad: JavaEntity, *, incluir_id: bool = False
) -> dict[str, Any]:
    """
    Arma un JSON de ejemplo con los campos de la entidad, usando valores
    por defecto según el tipo Java.
    """
    body: dict[str, Any] = {}
    for campo in entidad.campos:
        if campo.es_clave_primaria and not incluir_id:
            continue
        body[campo.nombre_java] = _valor_ejemplo(campo.tipo_java)
    return body


def _valor_ejemplo(tipo_java: str) -> Any:
    """Devuelve un valor de ejemplo coherente con el tipo Java."""
    t = (tipo_java or "").strip()
    if t in ("Integer", "int"):
        return 0
    if t in ("Long", "long"):
        return 1
    if t in ("Short", "short"):
        return 0
    if t in ("Float", "Double", "double", "float"):
        return 0.0
    if t == "BigDecimal":
        return "0.00"
    if t in ("Boolean", "boolean"):
        return True
    if t == "LocalDate":
        return "2025-01-01"
    if t == "LocalDateTime":
        return "2025-01-01T10:00:00"
    if t == "LocalTime":
        return "10:00:00"
    if t == "UUID":
        return "00000000-0000-0000-0000-000000000000"
    if t == "byte[]":
        return ""
    # String y fallback
    return "texto de ejemplo"


# ======================================================================
# Helpers
# ======================================================================
def _uuid_like() -> str:
    """Genera un id pseudo-UUID para la metadata de Postman."""
    import uuid

    return str(uuid.uuid4())