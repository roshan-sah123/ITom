"""Shared knowledge content and files in the configured database."""
from alembic import op
import sqlalchemy as sa

revision = "0013_knowledge_content"
down_revision = "0012_asset_inventory_reviews"
branch_labels = depends_on = None


def upgrade():
    op.create_table("knowledge_content",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(32), nullable=False, unique=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("file_name", sa.String(150), nullable=False),
        sa.Column("file_type", sa.String(120), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_data", sa.LargeBinary(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("validated_by", sa.String(128)),
        sa.Column("validated_on", sa.DateTime(timezone=True)),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade():
    op.drop_table("knowledge_content")
