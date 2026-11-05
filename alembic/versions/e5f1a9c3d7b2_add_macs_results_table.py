"""add macs_runs, macs_handoffs, and imacs_job_links tables (i-macs MACS+ run history and links)

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
    # Idempotent: uvicorn boot may already have created the tables via
    # _ensure_macs_tables (Railway does not run alembic on start).
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()

    if "macs_runs" not in tables:
        op.create_table(
            'macs_runs',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('project_id', sa.Uuid(), nullable=True),
            sa.Column('schema', sa.Text(), nullable=False),
            sa.Column('inputs', sa.JSON(), nullable=False),
            sa.Column('section', sa.Text(), nullable=False),
            sa.Column('exposure', sa.Text(), nullable=False),
            sa.Column('critical_temp', sa.Float(), nullable=False),
            sa.Column('section_factor', sa.Float(), nullable=False),
            sa.Column('governing_side', sa.Text(), nullable=False),
            sa.Column('windows_user', sa.Text(), nullable=False),
            sa.Column('machine_name', sa.Text(), nullable=True),
            sa.Column('client_timestamp', sa.DateTime(timezone=True), nullable=False),
            sa.Column('client_version', sa.Text(), nullable=True),
            sa.Column('run_id', sa.Text(), nullable=True),
            sa.Column('label', sa.Text(), nullable=True),
            sa.Column('imacs_job_id', sa.Text(), nullable=True),
            sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )

    runs_indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("macs_runs")}
    if "ix_macs_runs_project_id" not in runs_indexes:
        op.create_index('ix_macs_runs_project_id', 'macs_runs', ['project_id'])
    if "ix_macs_runs_imacs_job_id" not in runs_indexes:
        op.create_index('ix_macs_runs_imacs_job_id', 'macs_runs', ['imacs_job_id'])

    if "macs_handoffs" not in tables:
        op.create_table(
            'macs_handoffs',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('run_id', sa.Uuid(), nullable=False),
            sa.Column('imacs_job_id', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('claimed_project_id', sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(['run_id'], ['macs_runs.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['claimed_project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )

    if "imacs_job_links" not in tables:
        op.create_table(
            'imacs_job_links',
            sa.Column('imacs_job_id', sa.Text(), nullable=False),
            sa.Column('project_id', sa.Uuid(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('imacs_job_id'),
        )

    link_indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("imacs_job_links")}
    if "ix_imacs_job_links_project_id" not in link_indexes:
        op.create_index('ix_imacs_job_links_project_id', 'imacs_job_links', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_imacs_job_links_project_id', table_name='imacs_job_links')
    op.drop_table('imacs_job_links')
    op.drop_table('macs_handoffs')
    op.drop_index('ix_macs_runs_imacs_job_id', table_name='macs_runs')
    op.drop_index('ix_macs_runs_project_id', table_name='macs_runs')
    op.drop_table('macs_runs')
