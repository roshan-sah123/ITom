"""Schema boundary for Vendor, Knowledge and workbook inventory persistence."""
from sqlalchemy import MetaData

from app.models.base import Base

MODULE_TABLE_NAMES = frozenset({
    "vendor_submissions", "knowledge_content", "asset_inventory_batches",
    "asset_inventory_records", "asset_inventory_audit",
})


def module_metadata() -> MetaData:
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name in MODULE_TABLE_NAMES:
            table.to_metadata(metadata)
    return metadata
