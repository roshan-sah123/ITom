"""Independent baseline using the immutable, previously shipped module schemas."""
from pathlib import Path

from alembic.script import ScriptDirectory

revision = "0001_module_storage"
down_revision = None
branch_labels = depends_on = None

LEGACY_REVISIONS = (
    "0011_vendor_submissions", "0012_asset_inventory_reviews", "0013_knowledge_content",
)


def upgrade():
    # Reuse frozen migration definitions, not mutable ORM create_all schemas.
    legacy = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "alembic"))
    for identifier in LEGACY_REVISIONS:
        legacy.get_revision(identifier).module.upgrade()


def downgrade():
    legacy = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "alembic"))
    for identifier in reversed(LEGACY_REVISIONS):
        legacy.get_revision(identifier).module.downgrade()
