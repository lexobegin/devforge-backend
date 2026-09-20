# alembic/env.py
"""
Entorno de Alembic para DevForge AI.

- Usa SQLAlchemy async (asyncpg) para coincidir con el engine de la app.
- Importa `app.models` para que todas las tablas queden registradas en
  `Base.metadata` antes de autogenerar migraciones.
- Toma la URL de conexión desde `app.config.settings`, no desde alembic.ini.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# --- Importar Settings y la metadata de los modelos ---
from app.config import settings
from app.database import Base  # noqa: F401

# Este import es CLAVE: registra todas las clases en Base.metadata.
# Sin él, Alembic no "vería" las tablas al autogenerar.
import app.models  # noqa: F401


# ----------------------------------------------------------------------
# Configuración de Alembic (tomada de alembic.ini)
# ----------------------------------------------------------------------
config = context.config

# Sobrescribimos la URL vacía de alembic.ini con la real desde Settings.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Configurar logging desde alembic.ini (si existe)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Metadata objetivo para autogenerate
target_metadata = Base.metadata


# ----------------------------------------------------------------------
# Modo offline (sin conexión real): genera SQL a partir del contexto
# ----------------------------------------------------------------------
def run_migrations_offline() -> None:
    """
    Ejecuta migraciones en modo 'offline'.
    Solo emite el SQL a stdout; no se conecta a la base de datos.
    Útil para revisar el SQL antes de aplicarlo en producción.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ----------------------------------------------------------------------
# Modo online (async)
# ----------------------------------------------------------------------
def do_run_migrations(connection: Connection) -> None:
    """Configura el contexto de Alembic sobre una conexión sync (interna)."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Incluir los CHECK constraints definidos como __table_args__
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Crea el engine async y ejecuta las migraciones."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Punto de entrada del modo online: dispara la versión async."""
    asyncio.run(run_async_migrations())


# ----------------------------------------------------------------------
# Selección de modo
# ----------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()