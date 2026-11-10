"""add live HRR and DEVC series tables

Chained from the phase-1 modelling-run revision. Idempotent: uvicorn boot
may already have created the tables via _ensure_modelling_run_tables.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-10 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if "run_series_columns" not in tables:
        op.create_table(
            "run_series_columns",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("column_id", sa.Text(), nullable=False),
            sa.Column("quantity", sa.Text(), nullable=True),
            sa.Column("unit", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "kind IN ('hrr', 'devc')", name="ck_run_series_columns_kind"
            ),
            sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "run_id", "kind", "column_id", name="uq_run_series_column"
            ),
        )
        op.create_index(
            "ix_run_series_columns_run_id", "run_series_columns", ["run_id"]
        )

    if "run_series_points" not in tables:
        op.create_table(
            "run_series_points",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("column_id", sa.Text(), nullable=False),
            sa.Column("t", sa.Float(), nullable=False),
            sa.Column("value", sa.Float(), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.CheckConstraint(
                "kind IN ('hrr', 'devc')", name="ck_run_series_points_kind"
            ),
            sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "run_id", "kind", "column_id", "t", name="uq_run_series_point_t"
            ),
        )
        op.create_index(
            "ix_run_series_points_cursor",
            "run_series_points",
            ["run_id", "kind", "seq"],
        )
        op.create_index(
            "ix_run_series_points_column",
            "run_series_points",
            ["run_id", "kind", "column_id"],
        )

    if "run_series_counters" not in tables:
        op.create_table(
            "run_series_counters",
            sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("last_seq", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("run_id"),
        )

    if "run_devc_selections" not in tables:
        op.create_table(
            "run_devc_selections",
            sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("column_id", sa.Text(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("run_id", "column_id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "run_devc_selections" in tables:
        op.drop_table("run_devc_selections")
    if "run_series_counters" in tables:
        op.drop_table("run_series_counters")
    if "run_series_points" in tables:
        op.drop_table("run_series_points")
    if "run_series_columns" in tables:
        op.drop_table("run_series_columns")
