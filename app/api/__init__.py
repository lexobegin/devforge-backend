# app/api/__init__.py
"""
Paquete de la capa API de DevForge AI.

Contiene los routers de FastAPI organizados por versión (v1).

CICLO 2: los routers delegan en los services SIN sesión (los services del
Ciclo 2 no reciben AsyncSession: la conexión la lleva Beanie tras
app/mongo.init_db()), los ids de ruta son PydanticObjectId (se validan y
serializan como str) y los errores de dominio (NotFoundError,
ValidationError, ForbiddenError, ConflictError…) se traducen a HTTP por
los manejadores de app/core/exceptions.py registrados en main.py.
"""