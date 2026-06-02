"""add mode to elements

Tags each element with the owning analysis mode (fdsGen / radiation / timeEq)
so one floor can hold geometry for multiple modes. Nullable; existing rows
(NULL) are treated as legacy/fdsGen.

Revision ID: c3d5e7f9a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-06-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d5e7f9a1b2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('elements', sa.Column('mode', sa.Text(), nullable=True))
    # Supports filtering a floor's elements by mode (GET .../elements?mode=)
    op.create_index('ix_elements_floor_mode', 'elements', ['floor_id', 'mode'])


def downgrade() -> None:
    op.drop_index('ix_elements_floor_mode', table_name='elements')
    op.drop_column('elements', 'mode')
