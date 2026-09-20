"""init schema — DevForge AI (25 tablas)

Revision ID: 0001_init
Revises:
Create Date: 2025-01-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ======================================================================
# UPGRADE
# ======================================================================
def upgrade() -> None:
    # ------------------------------------------------------------------
    # A. USUARIOS
    # ------------------------------------------------------------------
    op.create_table(
        "usuarios",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("nombre_completo", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("rol", sa.String(length=20), nullable=False, server_default="DESARROLLADOR"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_usuarios_email"),
        sa.CheckConstraint("rol IN ('ADMIN','DESARROLLADOR')", name="ck_usuarios_rol"),
    )
    op.create_index("ix_usuarios_email", "usuarios", ["email"])

    # ------------------------------------------------------------------
    # B. PROYECTOS
    # ------------------------------------------------------------------
    op.create_table(
        "proyectos",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("id_propietario", sa.BigInteger(), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="ACTIVO"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_propietario"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("estado IN ('ACTIVO','ARCHIVADO')", name="ck_proyectos_estado"),
    )
    op.create_index("ix_proyectos_id_propietario", "proyectos", ["id_propietario"])

    op.create_table(
        "miembros_proyecto",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_proyecto", sa.BigInteger(), nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), nullable=False),
        sa.Column("rol_en_proyecto", sa.String(length=20), nullable=False, server_default="EDITOR"),
        sa.Column("joined_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_proyecto"], ["proyectos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_proyecto", "id_usuario", name="uq_miembro_proyecto_usuario"),
        sa.CheckConstraint(
            "rol_en_proyecto IN ('PROPIETARIO','EDITOR','LECTOR')",
            name="ck_miembros_rol",
        ),
    )
    op.create_index("ix_miembros_id_proyecto", "miembros_proyecto", ["id_proyecto"])
    op.create_index("ix_miembros_id_usuario", "miembros_proyecto", ["id_usuario"])

    # ------------------------------------------------------------------
    # C. DIAGRAMAS
    # ------------------------------------------------------------------
    op.create_table(
        "diagramas",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_proyecto", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("version_uml", sa.String(length=10), nullable=False, server_default="2.5.1"),
        sa.Column("numero_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id_creador", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_proyecto"], ["proyectos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_creador"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_diagramas_id_proyecto", "diagramas", ["id_proyecto"])
    op.create_index("ix_diagramas_id_creador", "diagramas", ["id_creador"])

    # ------------------------------------------------------------------
    # B. COLABORACIÓN (sesiones_colaboracion depende de diagramas)
    # ------------------------------------------------------------------
    op.create_table(
        "sesiones_colaboracion",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_proyecto", sa.BigInteger(), nullable=False),
        sa.Column("id_diagrama", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["id_proyecto"], ["proyectos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["id_diagrama"], ["diagramas.id"],
            name="fk_sesion_diagrama", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sesiones_id_proyecto", "sesiones_colaboracion", ["id_proyecto"])
    op.create_index("ix_sesiones_id_diagrama", "sesiones_colaboracion", ["id_diagrama"])

    op.create_table(
        "participantes_sesion",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_sesion", sa.BigInteger(), nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("left_at", sa.DateTime(), nullable=True),
        sa.Column("posicion_cursor", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["id_sesion"], ["sesiones_colaboracion.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_participantes_id_sesion", "participantes_sesion", ["id_sesion"])
    op.create_index("ix_participantes_id_usuario", "participantes_sesion", ["id_usuario"])

    # ------------------------------------------------------------------
    # AUDITORÍA
    # ------------------------------------------------------------------
    op.create_table(
        "bitacora_sistema",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), nullable=True),
        sa.Column("tipo_evento", sa.String(length=50), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=False),
        sa.Column("entidad_afectada", sa.String(length=30), nullable=True),
        sa.Column("id_entidad_afectada", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bitacora_fecha", "bitacora_sistema", ["created_at"])
    op.create_index("ix_bitacora_usuario", "bitacora_sistema", ["id_usuario"])

    # ------------------------------------------------------------------
    # C. UML — clases, atributos, operaciones, parámetros
    # ------------------------------------------------------------------
    op.create_table(
        "clases_uml",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_diagrama", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("es_abstracta", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("estereotipo", sa.String(length=50), nullable=True),
        sa.Column("pos_x", sa.Numeric(10, 2), nullable=True, server_default="0"),
        sa.Column("pos_y", sa.Numeric(10, 2), nullable=True, server_default="0"),
        sa.Column("id_creador", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_diagrama"], ["diagramas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_creador"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_clases_uml_diagrama", "clases_uml", ["id_diagrama"])

    op.create_table(
        "atributos_uml",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_clase", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("tipo_dato", sa.String(length=50), nullable=False),
        sa.Column("visibilidad", sa.String(length=1), nullable=False, server_default="-"),
        sa.Column("es_estatico", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("valor_defecto", sa.String(length=100), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["id_clase"], ["clases_uml.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("visibilidad IN ('+','-','#','~')", name="ck_atributo_visibilidad"),
    )
    op.create_index("ix_atributos_id_clase", "atributos_uml", ["id_clase"])

    op.create_table(
        "operaciones_uml",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_clase", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("tipo_retorno", sa.String(length=50), nullable=False, server_default="void"),
        sa.Column("visibilidad", sa.String(length=1), nullable=False, server_default="+"),
        sa.Column("es_estatico", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["id_clase"], ["clases_uml.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("visibilidad IN ('+','-','#','~')", name="ck_operacion_visibilidad"),
    )
    op.create_index("ix_operaciones_id_clase", "operaciones_uml", ["id_clase"])

    op.create_table(
        "parametros_operacion_uml",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_operacion", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("tipo_dato", sa.String(length=50), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["id_operacion"], ["operaciones_uml.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_parametros_id_operacion", "parametros_operacion_uml", ["id_operacion"]
    )

    op.create_table(
        "interfaces_uml",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_diagrama", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("pos_x", sa.Numeric(10, 2), nullable=True, server_default="0"),
        sa.Column("pos_y", sa.Numeric(10, 2), nullable=True, server_default="0"),
        sa.ForeignKeyConstraint(["id_diagrama"], ["diagramas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interfaces_id_diagrama", "interfaces_uml", ["id_diagrama"])

    op.create_table(
        "operaciones_interfaz_uml",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_interfaz", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("tipo_retorno", sa.String(length=50), nullable=False, server_default="void"),
        sa.ForeignKeyConstraint(["id_interfaz"], ["interfaces_uml.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ops_interfaz_id_interfaz", "operaciones_interfaz_uml", ["id_interfaz"]
    )

    op.create_table(
        "relaciones_uml",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_diagrama", sa.BigInteger(), nullable=False),
        sa.Column("id_clase_origen", sa.BigInteger(), nullable=False),
        sa.Column("id_clase_destino", sa.BigInteger(), nullable=False),
        sa.Column("tipo_relacion", sa.String(length=20), nullable=False),
        sa.Column("multiplicidad_origen", sa.String(length=10), nullable=True),
        sa.Column("multiplicidad_destino", sa.String(length=10), nullable=True),
        sa.Column("nombre_asociacion", sa.String(length=100), nullable=True),
        sa.Column("rol_origen", sa.String(length=100), nullable=True),
        sa.Column("rol_destino", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["id_diagrama"], ["diagramas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_clase_origen"], ["clases_uml.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_clase_destino"], ["clases_uml.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "tipo_relacion IN ('ASOCIACION','AGREGACION','COMPOSICION',"
            "'DEPENDENCIA','GENERALIZACION','REALIZACION')",
            name="ck_relacion_tipo",
        ),
    )
    op.create_index("idx_relaciones_uml_diagrama", "relaciones_uml", ["id_diagrama"])

    # ------------------------------------------------------------------
    # D. TRAZABILIDAD
    # ------------------------------------------------------------------
    op.create_table(
        "historial_cambios_diagrama",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_diagrama", sa.BigInteger(), nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), nullable=False),
        sa.Column("tipo_cambio", sa.String(length=20), nullable=False),
        sa.Column("tipo_entidad", sa.String(length=30), nullable=False),
        sa.Column("id_entidad", sa.BigInteger(), nullable=False),
        sa.Column("datos_cambio", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_diagrama"], ["diagramas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "tipo_cambio IN ('CREAR','MODIFICAR','ELIMINAR')",
            name="ck_historial_tipo_cambio",
        ),
    )
    op.create_index(
        "idx_historial_cambios_diagrama",
        "historial_cambios_diagrama",
        ["id_diagrama", "created_at"],
    )

    op.create_table(
        "versiones_diagrama",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_diagrama", sa.BigInteger(), nullable=False),
        sa.Column("numero_version", sa.Integer(), nullable=False),
        sa.Column("contenido_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), nullable=False),
        sa.Column("comentario", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_diagrama"], ["diagramas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_diagrama", "numero_version", name="uq_version_diagrama_numero"),
    )
    op.create_index(
        "idx_versiones_diagrama", "versiones_diagrama", ["id_diagrama", "numero_version"]
    )

    op.create_table(
        "comentarios_diagrama",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_diagrama", sa.BigInteger(), nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), nullable=False),
        sa.Column("tipo_entidad", sa.String(length=30), nullable=True),
        sa.Column("id_entidad", sa.BigInteger(), nullable=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("resuelto", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_diagrama"], ["diagramas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comentarios_id_diagrama", "comentarios_diagrama", ["id_diagrama"])
    op.create_index("ix_comentarios_id_usuario", "comentarios_diagrama", ["id_usuario"])

    # ------------------------------------------------------------------
    # E. INTERCAMBIO
    # ------------------------------------------------------------------
    op.create_table(
        "exportaciones_diagrama",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_diagrama", sa.BigInteger(), nullable=False),
        sa.Column("formato", sa.String(length=10), nullable=False, server_default="XMI"),
        sa.Column("ruta_archivo", sa.String(length=255), nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), nullable=False),
        sa.Column("exported_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_diagrama"], ["diagramas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exportaciones_id_diagrama", "exportaciones_diagrama", ["id_diagrama"])

    op.create_table(
        "importaciones_diagrama",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_diagrama", sa.BigInteger(), nullable=False),
        sa.Column("formato", sa.String(length=10), nullable=False, server_default="XMI"),
        sa.Column("archivo_origen", sa.String(length=255), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="PENDIENTE"),
        sa.Column("id_usuario", sa.BigInteger(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_diagrama"], ["diagramas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE','EXITOSO','FALLIDO')",
            name="ck_importacion_estado",
        ),
    )
    op.create_index("ix_importaciones_id_diagrama", "importaciones_diagrama", ["id_diagrama"])

    # ------------------------------------------------------------------
    # F. GENERACIÓN
    # ------------------------------------------------------------------
    op.create_table(
        "trabajos_generacion_codigo",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_diagrama", sa.BigInteger(), nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), nullable=False),
        sa.Column(
            "stack_destino", sa.String(length=30), nullable=False,
            server_default="SPRING_BOOT_JPA_POSTGRES",
        ),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="PENDIENTE"),
        sa.Column("ruta_salida", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_diagrama"], ["diagramas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE','EN_PROCESO','EXITOSO','FALLIDO')",
            name="ck_trabajo_generacion_estado",
        ),
    )
    op.create_index("ix_trabajos_id_diagrama", "trabajos_generacion_codigo", ["id_diagrama"])
    op.create_index("ix_trabajos_id_usuario", "trabajos_generacion_codigo", ["id_usuario"])

    op.create_table(
        "entidades_generadas",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_trabajo", sa.BigInteger(), nullable=False),
        sa.Column("id_clase_uml", sa.BigInteger(), nullable=False),
        sa.Column("nombre_clase_java", sa.String(length=150), nullable=False),
        sa.Column("nombre_tabla", sa.String(length=150), nullable=False),
        sa.ForeignKeyConstraint(
            ["id_trabajo"], ["trabajos_generacion_codigo.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["id_clase_uml"], ["clases_uml.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entidades_id_trabajo", "entidades_generadas", ["id_trabajo"])
    op.create_index("ix_entidades_id_clase_uml", "entidades_generadas", ["id_clase_uml"])

    op.create_table(
        "reglas_mapeo",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_entidad_generada", sa.BigInteger(), nullable=False),
        sa.Column("id_atributo_uml", sa.BigInteger(), nullable=False),
        sa.Column("nombre_columna", sa.String(length=100), nullable=False),
        sa.Column("tipo_sql", sa.String(length=50), nullable=False),
        sa.Column("es_clave_primaria", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("es_nulleable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(
            ["id_entidad_generada"], ["entidades_generadas.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["id_atributo_uml"], ["atributos_uml.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reglas_id_entidad", "reglas_mapeo", ["id_entidad_generada"])
    op.create_index("ix_reglas_id_atributo", "reglas_mapeo", ["id_atributo_uml"])

    # ------------------------------------------------------------------
    # G. IA
    # ------------------------------------------------------------------
    op.create_table(
        "interacciones_ia",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_proyecto", sa.BigInteger(), nullable=False),
        sa.Column("id_diagrama", sa.BigInteger(), nullable=True),
        sa.Column("id_usuario", sa.BigInteger(), nullable=False),
        sa.Column("canal", sa.String(length=10), nullable=False),
        sa.Column("texto_prompt", sa.Text(), nullable=False),
        sa.Column("respuesta_ia", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("accion_aplicada", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_proyecto"], ["proyectos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_diagrama"], ["diagramas.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("canal IN ('VOZ','TEXTO')", name="ck_interaccion_ia_canal"),
    )
    op.create_index("ix_interacciones_id_proyecto", "interacciones_ia", ["id_proyecto"])
    op.create_index("ix_interacciones_id_diagrama", "interacciones_ia", ["id_diagrama"])
    op.create_index("ix_interacciones_id_usuario", "interacciones_ia", ["id_usuario"])

    # ------------------------------------------------------------------
    # H. SINCRONIZACIÓN
    # ------------------------------------------------------------------
    op.create_table(
        "cola_sincronizacion_movil",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_dispositivo", sa.String(length=100), nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), nullable=False),
        sa.Column("id_diagrama", sa.BigInteger(), nullable=True),
        sa.Column("id_temporal_local", sa.String(length=100), nullable=True),
        sa.Column("tipo_operacion", sa.String(length=20), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="PENDIENTE"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["id_diagrama"], ["diagramas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE','SINCRONIZADO','CONFLICTO')",
            name="ck_cola_sync_estado",
        ),
    )
    op.create_index("ix_cola_sync_id_dispositivo", "cola_sincronizacion_movil", ["id_dispositivo"])
    op.create_index("ix_cola_sync_id_usuario", "cola_sincronizacion_movil", ["id_usuario"])
    op.create_index("idx_cola_sync_estado", "cola_sincronizacion_movil", ["estado"])

    # ------------------------------------------------------------------
    # I. NOTIFICACIONES
    # ------------------------------------------------------------------
    op.create_table(
        "notificaciones",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("mensaje", sa.String(length=255), nullable=False),
        sa.Column("id_referencia", sa.BigInteger(), nullable=True),
        sa.Column("leida", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_notificaciones_usuario", "notificaciones", ["id_usuario", "leida"])


# ======================================================================
# DOWNGRADE
# ======================================================================
def downgrade() -> None:
    # Orden inverso al upgrade
    op.drop_table("notificaciones")
    op.drop_table("cola_sincronizacion_movil")
    op.drop_table("interacciones_ia")
    op.drop_table("reglas_mapeo")
    op.drop_table("entidades_generadas")
    op.drop_table("trabajos_generacion_codigo")
    op.drop_table("importaciones_diagrama")
    op.drop_table("exportaciones_diagrama")
    op.drop_table("comentarios_diagrama")
    op.drop_table("versiones_diagrama")
    op.drop_table("historial_cambios_diagrama")
    op.drop_table("relaciones_uml")
    op.drop_table("operaciones_interfaz_uml")
    op.drop_table("interfaces_uml")
    op.drop_table("parametros_operacion_uml")
    op.drop_table("operaciones_uml")
    op.drop_table("atributos_uml")
    op.drop_table("clases_uml")
    op.drop_table("bitacora_sistema")
    op.drop_table("participantes_sesion")
    op.drop_table("sesiones_colaboracion")
    op.drop_table("diagramas")
    op.drop_table("miembros_proyecto")
    op.drop_table("proyectos")
    op.drop_table("usuarios")