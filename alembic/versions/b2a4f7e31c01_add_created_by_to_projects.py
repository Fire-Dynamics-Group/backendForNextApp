"""add created_by to projects

Revision ID: b2a4f7e31c01
Revises: 9e0b3c93119a
Create Date: 2026-03-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2a4f7e31c01'
down_revision: Union[str, None] = '9e0b3c93119a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('created_by', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('projects', 'created_by')
