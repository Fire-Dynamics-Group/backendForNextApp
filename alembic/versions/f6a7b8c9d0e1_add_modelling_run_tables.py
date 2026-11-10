"""add modelling-run tables (machines, runs, run_events, run_commands)

Chained from the current head e5f1a9c3d7b2. a1b2c3d4e5f6 already has a child
(c3d4e5f6a7b8), so revising it would fork alembic.

Idempotent: uvicorn boot may already have created the tables via
_ensure_modelling_run_tables (Railway does not run alembic on start).

Revision ID: f6a7b8c9d0e1
Revises: e5f1a9c3d7b2
Create Date: 2026-11-10 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = 'e5f1a9c3d7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if "machines" not in tables:
        op.create_table(
            "machines",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("target_type", sa.Text(), nullable=False),
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.Text(), nullable=False),
            sa.CheckConstraint(
                "target_type IN ('local', 'cloudhpc')", name="ck_machines_target_type"
            ),
            sa.CheckConstraint(
                "status IN ('online', 'idle', 'offline')", name="ck_machines_status"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    if "runs" not in tables:
        op.create_table(
            "runs",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("target", sa.Text(), nullable=False),
            sa.Column("machine_id", sa.Uuid(), nullable=True),
            sa.Column("case_name", sa.Text(), nullable=False),
            sa.Column("input_file_ref", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("progress_pct", sa.Float(), nullable=True),
            sa.Column("sim_time", sa.Float(), nullable=True),
            sa.Column("end_time", sa.Float(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("results_link", sa.Text(), nullable=True),
            sa.Column("cost_estimate", sa.Float(), nullable=True),
            sa.Column("cost_actual", sa.Float(), nullable=True),
            sa.Column("cost_currency", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Text(), nullable=True),
            sa.Column("external_id", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("target IN ('local', 'cloudhpc')", name="ck_runs_target"),
            sa.CheckConstraint(
                "status IN ('queued', 'running', 'stopped', 'failed', 'completed')",
                name="ck_runs_status",
            ),
            sa.ForeignKeyConstraint(["machine_id"], ["machines.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_runs_machine_id", "runs", ["machine_id"])

    if "run_events" not in tables:
        op.create_table(
            "run_events",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("run_id", sa.Uuid(), nullable=True),
            sa.Column("machine_id", sa.Uuid(), nullable=True),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["machine_id"], ["machines.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_run_events_run_id", "run_events", ["run_id"])
        op.create_index("ix_run_events_machine_id", "run_events", ["machine_id"])

    if "run_commands" not in tables:
        op.create_table(
            "run_commands",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("machine_id", sa.Uuid(), nullable=False),
            sa.Column("run_id", sa.Uuid(), nullable=True),
            sa.Column("command", sa.Text(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "command IN ('submit', 'stop', 'restart')",
                name="ck_run_commands_command",
            ),
            sa.CheckConstraint(
                "status IN ('pending', 'acked', 'done', 'failed')",
                name="ck_run_commands_status",
            ),
            sa.ForeignKeyConstraint(["machine_id"], ["machines.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_run_commands_machine_id", "run_commands", ["machine_id"])
        op.create_index("ix_run_commands_run_id", "run_commands", ["run_id"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "run_commands" in tables:
        op.drop_table("run_commands")
    if "run_events" in tables:
        op.drop_table("run_events")
    if "runs" in tables:
        op.drop_table("runs")
    if "machines" in tables:
        op.drop_table("machines")
