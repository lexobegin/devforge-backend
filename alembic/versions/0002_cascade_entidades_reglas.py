"""cascade ondelete for entidades_generadas and reglas_mapeo

Revision ID: 0002_cascade
Revises: 0001_init
Create Date: 2026-09-18 00:00:00.000000

Cambia las FK de entidades_generadas.id_clase_uml y reglas_mapeo.id_atributo_uml
de RESTRICT a CASCADE, para que al eliminar una clase UML (o un atributo) se
borren en cascada las entidades y reglas de mapeo asociadas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_cascade"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) entidades_generadas.id_clase_uml → CASCADE
    # ------------------------------------------------------------------
    op.drop_constraint(
        "entidades_generadas_id_clase_uml_fkey",
        "entidades_generadas",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "entidades_generadas_id_clase_uml_fkey",
        "entidades_generadas",
        "clases_uml",
        ["id_clase_uml"],
        ["id"],
        ondelete="CASCADE",
    )

    # ------------------------------------------------------------------
    # 2) reglas_mapeo.id_atributo_uml → CASCADE
    # ------------------------------------------------------------------
    op.drop_constraint(
        "reglas_mapeo_id_atributo_uml_fkey",
        "reglas_mapeo",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "reglas_mapeo_id_atributo_uml_fkey",
        "reglas_mapeo",
        "atributos_uml",
        ["id_atributo_uml"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 1) entidades_generadas.id_clase_uml → RESTRICT
    # ------------------------------------------------------------------
    op.drop_constraint(
        "entidades_generadas_id_clase_uml_fkey",
        "entidades_generadas",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "entidades_generadas_id_clase_uml_fkey",
        "entidades_generadas",
        "clases_uml",
        ["id_clase_uml"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ------------------------------------------------------------------
    # 2) reglas_mapeo.id_atributo_uml → RESTRICT
    # ------------------------------------------------------------------
    op.drop_constraint(
        "reglas_mapeo_id_atributo_uml_fkey",
        "reglas_mapeo",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "reglas_mapeo_id_atributo_uml_fkey",
        "reglas_mapeo",
        "atributos_uml",
        ["id_atributo_uml"],
        ["id"],
        ondelete="RESTRICT",
    )