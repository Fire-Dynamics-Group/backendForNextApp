"""add tool search analytics tables

Revision ID: d8e4a1c0b7f2
Revises: c7d1e5b9a204
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d8e4a1c0b7f2"
down_revision: Union[str, None] = "c7d1e5b9a204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_search_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_search_id", sa.Uuid(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("query_normalized", sa.Text(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("top_ids", sa.JSON(), nullable=False),
        sa.Column("suggestion_id", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Text(), nullable=True),
        sa.Column("mode", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("anon_id", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("user_email", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_search_logs_client_search_id", "tool_search_logs", ["client_search_id"])
    op.create_index("ix_tool_search_logs_query_normalized", "tool_search_logs", ["query_normalized"])
    op.create_index("ix_tool_search_logs_created_at", "tool_search_logs", ["created_at"])

    op.create_table(
        "tool_search_clicks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_search_id", sa.Uuid(), nullable=False),
        sa.Column("part_id", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("anon_id", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("user_email", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_search_clicks_client_search_id", "tool_search_clicks", ["client_search_id"])
    op.create_index("ix_tool_search_clicks_part_id", "tool_search_clicks", ["part_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_search_clicks_part_id", table_name="tool_search_clicks")
    op.drop_index("ix_tool_search_clicks_client_search_id", table_name="tool_search_clicks")
    op.drop_table("tool_search_clicks")
    op.drop_index("ix_tool_search_logs_created_at", table_name="tool_search_logs")
    op.drop_index("ix_tool_search_logs_query_normalized", table_name="tool_search_logs")
    op.drop_index("ix_tool_search_logs_client_search_id", table_name="tool_search_logs")
    op.drop_table("tool_search_logs")
