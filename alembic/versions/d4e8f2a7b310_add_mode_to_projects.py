"""add mode to projects

Each canvas mode (fdsGen, timeEq, ...) gets its own project dashboard. Existing
rows predate the column and were all created by the FDS generator, so they
default to fdsGen.

Revision ID: d4e8f2a7b310
Revises: c7d1e5b9a204
Create Date: 2026-09-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e8f2a7b310'
down_revision: Union[str, None] = 'c7d1e5b9a204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: uvicorn boot may already have added the column via
    # _ensure_projects_mode_column (Railway does not run alembic on start).
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("projects")}
    if "mode" not in cols:
        op.add_column(
            'projects',
            sa.Column('mode', sa.Text(), nullable=False, server_default='fdsGen'),
        )
    indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("projects")}
    if "ix_projects_mode" not in indexes:
        op.create_index('ix_projects_mode', 'projects', ['mode'])


def downgrade() -> None:
    op.drop_index('ix_projects_mode', table_name='projects')
    op.drop_column('projects', 'mode')
