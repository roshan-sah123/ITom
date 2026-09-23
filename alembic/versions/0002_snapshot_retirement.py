"""Soft retirement and complete snapshot counters."""
from alembic import op
import sqlalchemy as sa

revision = "0002_snapshot_retirement"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("configuration_items", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("configuration_items", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_ci_source_active", "configuration_items", ["source_system", "is_active"])
    for name in ("records_retired", "records_failed", "items_normalized"):
        op.add_column("sync_runs", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    for name in ("items_normalized", "records_failed", "records_retired"):
        op.drop_column("sync_runs", name)
    op.drop_index("ix_ci_source_active", table_name="configuration_items")
    op.drop_column("configuration_items", "retired_at")
    op.drop_column("configuration_items", "is_active")
