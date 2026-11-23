"""Replace one Assets Analytics category with the rows of a single source file.

Dry run by default. With --apply the category is rewritten in one transaction:
records match by --key, take the source values verbatim (blank cells stay empty),
records absent from the source are retired (soft-deleted, audited), and the
stored columns become the source columns minus completely empty ones and any
--drop columns. Before committing, the stored records are re-read and compared
cell by cell with the source; any mismatch rolls everything back.

Example:
    python scripts/replace_asset_inventory.py --category network \
        --source "network-inventory v1.2.xlsx" --sheet "network-inventory%20v1.1 (1)" --key S.N \
        --drop "AMC PROVIDER NAME=Identical to PROVIDER" --apply
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.database import ModuleSessionLocal, module_engine, verify_module_schema
from app.models.asset_review import AssetInventoryBatch, AssetInventoryRecord
from app.services.asset_workbook_import import (
    EXPORT_RENAMES, _same_value, _source_value, apply_replace, network_identifiers_agree, prune_source_columns,
    telecom_identifiers_agree,
    read_csv_source, read_sheet_source, verify_by_column)


def pair(text, option):
    if "=" not in text:
        raise argparse.ArgumentTypeError(f"{option} expects NAME=VALUE")
    left, right = text.split("=", 1)
    return left.strip(), right.strip()


def load_source(args):
    if args.source.suffix.lower() == ".csv":
        source = read_csv_source(args.source)
    else:
        if not args.sheet:
            raise SystemExit("--sheet is required for workbook sources")
        source = read_sheet_source(args.source, args.sheet)
    original_columns = list(source["columns"])
    overrides = []
    for column, value in args.set:
        if column not in source["columns"]:
            raise SystemExit(f"--set column {column!r} is not a source column")
        overrides.append({"column": column, "value": value})
        for row in source["rows"]:
            row["values"][column] = value
    for column, origin in args.copy:
        if column not in source["columns"] or origin not in source["columns"]:
            raise SystemExit(f"--copy needs source columns, got {column!r} <- {origin!r}")
        overrides.append({"column": column, "copied_from": origin})
        for row in source["rows"]:
            row["values"][column] = row["values"].get(origin)
    source = prune_source_columns(source, drop=args.drop)
    source["overrides"] = overrides
    return source, original_columns


async def verify_stored(session, category, source, plan):
    """Compare stored active records with the source rows before committing."""
    batch = (await session.execute(select(AssetInventoryBatch).where(
        AssetInventoryBatch.category == category).execution_options(populate_existing=True))).scalar_one()
    expected_columns = [EXPORT_RENAMES.get(column, column) for column in source["columns"]]
    rows = (await session.execute(select(AssetInventoryRecord).where(
        AssetInventoryRecord.category == category, AssetInventoryRecord.is_deleted.is_(False))
        .execution_options(populate_existing=True))).scalars().all()
    skipped = {item["source_row"] for item in plan.review if item.get("outcome") == "not_added"}
    expected_rows = {row["source_row"]: row["values"] for row in source["rows"] if row["source_row"] not in skipped}
    problems = []
    if batch.columns != expected_columns:
        problems.append(f"stored columns {batch.columns} != {expected_columns}")
    if len(rows) != len(expected_rows):
        problems.append(f"{len(rows)} active records != {len(expected_rows)} source rows")
    seen = set()
    for row in rows:
        values = expected_rows.get(row.source_row)
        if values is None or row.source_row in seen:
            problems.append(f"record {row.name} (row {row.source_row}) is not a unique source row")
            continue
        seen.add(row.source_row)
        if [cell["header"] for cell in row.data] != expected_columns:
            problems.append(f"record {row.name} has a different column layout")
        stored = {cell["header"]: cell["value"] for cell in row.data}
        for column, value in values.items():
            stored_value = stored.get(EXPORT_RENAMES.get(column, column))
            if not _same_value(stored_value, _source_value(value)):
                problems.append(f"row {row.source_row} {column}: stored {stored_value!r} != source {value!r}")
    if problems:
        raise RuntimeError("Verification failed; nothing was saved:\n  " + "\n  ".join(problems[:20]))
    return {"columns": len(expected_columns), "records": len(rows), "cells_checked": len(rows) * len(expected_columns)}


async def run(args):
    source, original_columns = load_source(args)
    when = datetime.now(timezone.utc)
    try:
        async with ModuleSessionLocal() as session:
            try:
                await verify_module_schema(session)
                confirm = ({"network": network_identifiers_agree, "telecom": telecom_identifiers_agree}.get(args.category)
                           if args.key == "S.N" else None)
                plan = await apply_replace(session, args.category, source, identity_column=args.key,
                                           confirm=confirm, allow_drop=True)
                verification = await verify_stored(session, args.category, source, plan)
                verified = None
                if args.verify_by or args.verify_as:
                    verified = await verify_by_column(session, args.category, args.verify_by, when,
                                                      args.verify_note or "Verified on operator instruction.",
                                                      reviewer_name=args.verify_as)
                await (session.commit() if args.apply else session.rollback())
            except BaseException:
                await session.rollback()
                raise
    finally:
        await module_engine.dispose()
    summary = plan.summary()
    report = {
        "generated_at": when.isoformat(), "applied": args.apply, "category": args.category,
        "source": {"file": source["source_file"], "sheet": source["source_sheet"], "sha256": source["sha256"],
                   "rows": len(source["rows"]), "columns": original_columns},
        "column_mapping": [{"source": column, "stored": EXPORT_RENAMES.get(column, column)}
                           for column in source["columns"]],
        "removed_columns": source["removed_columns"], "overrides": source["overrides"],
        "summary": summary, "verification": verification, "owner_verification": verified,
        "new_records": [{"source_row": item["source_row"], "name": item["name"]} for item in plan.creates],
        "retired_records": [record["name"] for record in plan.retired], "needs_review": plan.review,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"{args.category}: source rows={len(source['rows'])} columns {len(original_columns)} -> {len(source['columns'])}")
    for item in source["removed_columns"]:
        print(f"  removed column {item['column']!r}: {item['reason']}")
    for item in source["overrides"]:
        print(f"  override {item}")
    print(f"  matched={summary['matched_records']} updated={summary['records_updated']} new={summary['new_records']} "
          f"retired={summary['retired_records']} needs_review={summary['needs_review']} "
          f"cells_changed={summary['cells_changed']} cells_cleared={summary['cells_cleared']}")
    print(f"  verification: {verification}" + (f" owner verification: verified={verified['verified']} "
                                                  f"skipped={len(verified['skipped_without_reviewer'])}" if verified else ""))
    print(("Changes committed." if args.apply else "Dry run only; nothing was saved.") + f" Report: {args.report}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--category", required=True, choices=["server", "network", "telecom"])
    parser.add_argument("--source", required=True, type=Path, help=".xlsx or .csv source file")
    parser.add_argument("--sheet", help="worksheet name for .xlsx sources")
    parser.add_argument("--key", default="HOST NAME", help="matching column (HOST NAME, or S.N for network)")
    parser.add_argument("--drop", action="append", default=[], type=lambda text: pair(text, "--drop"),
                        help='redundant column to remove: "COLUMN=reason" (repeatable)')
    parser.add_argument("--set", action="append", default=[], type=lambda text: pair(text, "--set"),
                        help='operator-instructed constant value: "COLUMN=value" (repeatable)')
    parser.add_argument("--copy", action="append", default=[], type=lambda text: pair(text, "--copy"),
                        help='operator-instructed copy: "COLUMN=FROM_COLUMN" (repeatable)')
    parser.add_argument("--verify-by", help="mark every record verified by the value of this column")
    parser.add_argument("--verify-as", help="mark every record verified by this named reviewer")
    parser.add_argument("--verify-note", help="audit note for --verify-by/--verify-as")
    parser.add_argument("--apply", action="store_true", help="commit (default is a dry run)")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error(f"{args.source} does not exist")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.report = (args.report or Path(__file__).resolve().parents[1] / "logs" /
                   f"asset-replace-{args.category}-{stamp}.json").resolve()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
