"""Add the synchronized Intune compliance-reason cache.

Revision ID: 0002_intune_remediation_cache
Revises: 0001_initial_schema
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_intune_remediation_cache"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "intune_compliance_reason_cache" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "intune_compliance_reason_cache",
        sa.Column("summary_id", sa.String(length=512), nullable=False),
        sa.Column("setting_name", sa.String(length=512), nullable=False),
        sa.Column("platform", sa.String(length=128), nullable=False),
        sa.Column("noncompliant_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("conflict_count", sa.Integer(), nullable=False),
        sa.Column("affected_count", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("devices", sa.JSON(), nullable=False),
        sa.Column("catalog_refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("worklist_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("summary_id"),
    )


def downgrade() -> None:
    if "intune_compliance_reason_cache" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("intune_compliance_reason_cache")
