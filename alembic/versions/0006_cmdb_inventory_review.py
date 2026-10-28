"""Add isolated spreadsheet CMDB inventory and review audit tables."""

from alembic import op
import sqlalchemy as sa

revision = "0006_cmdb_inventory_review"
down_revision = "0005_rejected_source_count"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cmdb_inventory_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inventory_type", sa.String(length=16), nullable=False),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("source_sheet", sa.String(length=255), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("field_reviews", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("is_validated", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inventory_type", "source_key", name="uq_cmdb_inventory_source_key"),
    )
    op.create_index("ix_cmdb_inventory_type_name", "cmdb_inventory_records", ["inventory_type", "name"])
    op.create_index("ix_cmdb_inventory_validation", "cmdb_inventory_records", ["inventory_type", "is_validated"])

    op.create_table(
        "cmdb_inventory_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inventory_type", sa.String(length=16), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("imported_by", sa.String(length=255), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cmdb_inventory_imports_inventory_type", "cmdb_inventory_imports", ["inventory_type"])

    op.create_table(
        "cmdb_inventory_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inventory_type", sa.String(length=16), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cmdb_inventory_audit_inventory_type", "cmdb_inventory_audit", ["inventory_type"])
    op.create_index("ix_cmdb_inventory_audit_record_id", "cmdb_inventory_audit", ["record_id"])


def downgrade():
    op.drop_index("ix_cmdb_inventory_audit_record_id", table_name="cmdb_inventory_audit")
    op.drop_index("ix_cmdb_inventory_audit_inventory_type", table_name="cmdb_inventory_audit")
    op.drop_table("cmdb_inventory_audit")
    op.drop_index("ix_cmdb_inventory_imports_inventory_type", table_name="cmdb_inventory_imports")
    op.drop_table("cmdb_inventory_imports")
    op.drop_index("ix_cmdb_inventory_validation", table_name="cmdb_inventory_records")
    op.drop_index("ix_cmdb_inventory_type_name", table_name="cmdb_inventory_records")
    op.drop_table("cmdb_inventory_records")