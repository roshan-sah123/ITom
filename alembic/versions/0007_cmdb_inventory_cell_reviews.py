"""Preserve workbook source order and validation state per imported cell."""

import json
from alembic import op
import sqlalchemy as sa

revision = "0007_cmdb_inventory_cell_reviews"
down_revision = "0006_cmdb_inventory_review"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("cmdb_inventory_records")}
    if "source_order" not in columns:
        op.add_column("cmdb_inventory_records", sa.Column(
            "source_order", sa.Integer(), server_default="0", nullable=False,
        ))
    if "field_reviews" not in columns:
        op.add_column("cmdb_inventory_records", sa.Column(
            "field_reviews", sa.JSON(), server_default="{}", nullable=False,
        ))

    table = sa.Table(
        "cmdb_inventory_records", sa.MetaData(),
        sa.Column("id", sa.Uuid()),
        sa.Column("inventory_type", sa.String()),
        sa.Column("source_file", sa.String()),
        sa.Column("source_sheet", sa.String()),
        sa.Column("source_row", sa.Integer()),
        sa.Column("source_order", sa.Integer()),
        sa.Column("data", sa.JSON()),
        sa.Column("field_reviews", sa.JSON()),
    )
    rows = connection.execute(sa.select(table).order_by(
        table.c.inventory_type, table.c.source_file, table.c.source_sheet, table.c.source_row,
    )).mappings().all()
    counters = {}
    for row in rows:
        inventory_type = row["inventory_type"]
        source_order = counters.get(inventory_type, 0)
        counters[inventory_type] = source_order + 1
        data = row["data"]
        if isinstance(data, dict):
            data = [
                {"index": index, "header": header, "value": value}
                for index, (header, value) in enumerate(data.items())
            ]
        connection.execute(sa.update(table).where(table.c.id == row["id"]).values(
            source_order=source_order,
            data=data,
            field_reviews={},
        ))


def downgrade():
    op.drop_column("cmdb_inventory_records", "field_reviews")
    op.drop_column("cmdb_inventory_records", "source_order")