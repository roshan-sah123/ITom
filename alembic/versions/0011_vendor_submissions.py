"""Add portal-owned vendor submissions without modifying legacy companion tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_vendor_submissions"
down_revision = "0010_geographic_reporting"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "vendor_submissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(32), nullable=False, unique=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("vendor", sa.String(100), nullable=False),
        sa.Column("method", sa.String(80), nullable=False),
        sa.Column("step_count", sa.Integer(), nullable=False),
        sa.Column("sop_name", sa.String(150)),
        sa.Column("document", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("validated_by", sa.String(128)),
        sa.Column("validated_on", sa.DateTime(timezone=True)),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("vendor_submissions")
