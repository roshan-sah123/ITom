"""Initial schema establishing core ITOM relational tables and indexes.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-09-02 06:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create configuration_items table
    op.create_table(
        "configuration_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("ci_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("health_tier", sa.String(length=16), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("mac_address", sa.String(length=64), nullable=True),
        sa.Column("vendor", sa.String(length=64), nullable=False, server_default="Other"),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("serial_number", sa.String(length=128), nullable=True),
        sa.Column("operating_system", sa.String(length=128), nullable=True),
        sa.Column("location", sa.String(length=128), nullable=True),
        sa.Column("last_sync_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=True),
        sa.Column("attributes", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "source_id", name="uq_ci_source_system_source_id"),
    )
    op.create_index("ix_ci_source_system_type_status", "configuration_items", ["source_system", "ci_type", "status"], unique=False)
    op.create_index("ix_ci_source_system_created", "configuration_items", ["source_system", "created_at"], unique=False)
    op.create_index("ix_ci_health_tier", "configuration_items", ["health_tier"], unique=False)
    op.create_index("ix_ci_ip_address", "configuration_items", ["ip_address"], unique=False)
    op.create_index("ix_ci_vendor", "configuration_items", ["vendor"], unique=False)
    op.create_index("ix_ci_serial_number", "configuration_items", ["serial_number"], unique=False)
    op.create_index("ix_ci_name", "configuration_items", ["name"], unique=False)
    op.create_index("ix_ci_source_id", "configuration_items", ["source_id"], unique=False)
    op.create_index("ix_ci_ci_type", "configuration_items", ["ci_type"], unique=False)
    op.create_index("ix_ci_status", "configuration_items", ["status"], unique=False)

    # 2. Create ci_relationships table
    op.create_table(
        "ci_relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_ci_id", sa.Uuid(), nullable=False),
        sa.Column("target_ci_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=64), nullable=False),
        sa.Column("attributes", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["source_ci_id"], ["configuration_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_ci_id"], ["configuration_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ci_rel_source_target", "ci_relationships", ["source_ci_id", "target_ci_id"], unique=False)
    op.create_index("ix_ci_rel_type", "ci_relationships", ["relationship_type"], unique=False)

    # 3. Create ci_status_history table
    op.create_table(
        "ci_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ci_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("health_tier", sa.String(length=16), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("previous_health_tier", sa.String(length=16), nullable=True),
        sa.Column("cpu_utilization", sa.Float(), nullable=True),
        sa.Column("memory_utilization", sa.Float(), nullable=True),
        sa.Column("storage_used_pct", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("changed_attributes", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ci_id"], ["configuration_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_status_history_ci_recorded", "ci_status_history", ["ci_id", "recorded_at"], unique=False)
    op.create_index("ix_status_history_recorded_at", "ci_status_history", ["recorded_at"], unique=False)

    # 4. Create sync_runs table
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("records_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_extracted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_persisted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_runs_source_completed", "sync_runs", ["source_system", "completed_at"], unique=False)
    op.create_index("ix_sync_runs_status", "sync_runs", ["status"], unique=False)

    # 5. Create sync_error_logs table
    op.create_table(
        "sync_error_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sync_run_id", sa.Uuid(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=False, server_default="GENERAL_ERROR"),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("context_data", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_error_logs_run_id", "sync_error_logs", ["sync_run_id"], unique=False)
    op.create_index("ix_sync_error_logs_occurred_at", "sync_error_logs", ["occurred_at"], unique=False)


def downgrade() -> None:
    op.drop_table("sync_error_logs")
    op.drop_table("sync_runs")
    op.drop_table("ci_status_history")
    op.drop_table("ci_relationships")
    op.drop_table("configuration_items")
