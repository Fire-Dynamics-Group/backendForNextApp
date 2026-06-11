"""add fee_text_block + fee_text_block_history tables and seed

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-06-11 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from services.fee_text_blocks import get_seed_blocks

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fee_text_block',
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('default_content', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('label', sa.Text(), nullable=False, server_default=''),
        sa.Column('group_name', sa.Text(), nullable=False, server_default=''),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('placeholders', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_table(
        'fee_text_block_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('edited_by', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['key'], ['fee_text_block.key']),
        sa.PrimaryKeyConstraint('id'),
    )

    # Seed the editable text blocks from the constants module (one source of truth).
    fee_text_block = sa.table(
        'fee_text_block',
        sa.column('key', sa.Text),
        sa.column('default_content', sa.Text),
        sa.column('content', sa.Text),
        sa.column('kind', sa.Text),
        sa.column('label', sa.Text),
        sa.column('group_name', sa.Text),
        sa.column('sort_order', sa.Integer),
        sa.column('placeholders', sa.JSON),
    )
    rows = get_seed_blocks()
    if rows:
        op.bulk_insert(fee_text_block, rows)


def downgrade() -> None:
    op.drop_table('fee_text_block_history')
    op.drop_table('fee_text_block')
