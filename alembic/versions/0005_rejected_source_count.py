"""Track records rejected during source normalization."""
from alembic import op
import sqlalchemy as sa

revision = "0005_rejected_source_count"
down_revision = "0004_sqlite_query_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sync_runs", sa.Column("items_rejected", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("sync_runs", "items_rejected")
