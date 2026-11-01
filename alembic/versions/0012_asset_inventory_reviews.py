"""Independent spreadsheet inventory edits and review history; no telemetry changes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012_asset_inventory_reviews"
down_revision = "0011_vendor_submissions"
branch_labels = depends_on = None
JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade():
    op.create_table("asset_inventory_batches",
        sa.Column("category", sa.String(16), primary_key=True),
        sa.Column("source_file", sa.String(255), nullable=False),
        sa.Column("source_sheet", sa.String(255), nullable=False),
        sa.Column("columns", JSON, nullable=False), *timestamps())
    op.create_table("asset_inventory_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("source_key", sa.String(512), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("source_file", sa.String(255), nullable=False),
        sa.Column("source_sheet", sa.String(255), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.Column("data", JSON, nullable=False),
        sa.Column("field_reviews", JSON, nullable=False),
        sa.Column("is_validated", sa.Boolean(), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True)),
        sa.Column("validated_by", sa.String(128)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False), *timestamps(),
        sa.UniqueConstraint("category", "source_key", name="uq_asset_inventory_source"))
    op.create_table("asset_inventory_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("record_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("details", JSON, nullable=False), *timestamps())


def downgrade():
    for table in ["asset_inventory_audit", "asset_inventory_records", "asset_inventory_batches"]:
        op.drop_table(table)
