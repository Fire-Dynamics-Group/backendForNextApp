"""add macs_results table (i-macs MACS+ results per project)

Also merges the two existing heads (d4e8f2a7b310 add mode to projects,
d8e4a1c0b7f2 tool search analytics), which both revised c7d1e5b9a204.

Revision ID: e5f1a9c3d7b2
Revises: d4e8f2a7b310, d8e4a1c0b7f2
Create Date: 2026-11-02 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f1a9c3d7b2'
down_revision: str | Sequence[str] | None = ('d4e8f2a7b310', 'd8e4a1c0b7f2')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent: uvicorn boot may already have created the table via
    # _ensure_macs_results_table (Railway does not run alembic on start).
    bind = op.get_bind()
    if "macs_results" not in sa.inspect(bind).get_table_names():
        op.create_table(
            'macs_results',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('project_id', sa.Uuid(), nullable=False),
            sa.Column('schema', sa.Text(), nullable=False),
            sa.Column('envelope', sa.JSON(), nullable=False),
            sa.Column('critical_temp', sa.Float(), nullable=False),
            sa.Column('section_factor', sa.Float(), nullable=False),
            sa.Column('governing_side', sa.Text(), nullable=False),
            sa.Column('section', sa.Text(), nullable=False),
            sa.Column('exposure', sa.Text(), nullable=False),
            sa.Column('windows_user', sa.Text(), nullable=False),
            sa.Column('client_timestamp', sa.DateTime(timezone=True), nullable=False),
            sa.Column('client_version', sa.Text(), nullable=True),
            sa.Column('run_id', sa.Text(), nullable=True),
            sa.Column('label', sa.Text(), nullable=True),
            sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
    indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("macs_results")}
    if "ix_macs_results_project_id" not in indexes:
        op.create_index('ix_macs_results_project_id', 'macs_results', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_macs_results_project_id', table_name='macs_results')
    op.drop_table('macs_results')
