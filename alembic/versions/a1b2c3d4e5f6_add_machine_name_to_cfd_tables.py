"""add machine_name to cfd tables

Revision ID: a1b2c3d4e5f6
Revises: 610907c14e50
Create Date: 2026-03-31 22:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '610907c14e50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cfd_simulations', sa.Column('machine_name', sa.Text(), nullable=True))
    op.add_column('cfd_runner_state', sa.Column('machine_name', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('cfd_simulations', 'machine_name')
    op.drop_column('cfd_runner_state', 'machine_name')
