"""add smoke layer runs table

Revision ID: c7d1e5b9a204
Revises: 610907c14e50
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c7d1e5b9a204'
down_revision: Union[str, None] = '610907c14e50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'smoke_layer_runs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('project_name', sa.Text(), nullable=True),
        sa.Column('inputs', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_smoke_layer_run_name'),
    )


def downgrade() -> None:
    op.drop_table('smoke_layer_runs')
