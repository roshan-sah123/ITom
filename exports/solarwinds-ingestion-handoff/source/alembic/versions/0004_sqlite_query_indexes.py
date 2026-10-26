"""SQLite query indexes already present in deployed SQLite databases."""
from alembic import op

revision = "0004_sqlite_query_indexes"
down_revision = "0002_snapshot_retirement"
branch_labels = None
depends_on = None


def upgrade():
    # This revision is the deployed marker for these indexes. The ORM metadata
    # and bootstrap create_all path add them for new databases.
    pass


def downgrade():
    for name, table in (("ix_sync_runs_started_at", "sync_runs"),
                        ("ix_ci_last_sync_time", "configuration_items"),
                        ("ix_ci_location", "configuration_items")):
        op.drop_index(name, table_name=table)
