"""Reconcile Assets Analytics records with operator-supplied Excel workbooks.

Dry run by default: prints what would change and writes a JSON report. With
--apply, all categories are written in one transaction against DATABASE_URL_2.
Matched records only receive values for empty cells; existing portal values,
operator edits and deleted assets are preserved.

Example:
    python scripts/import_asset_workbooks.py \
        --server "03Backup.xlsx" --server-sheet "V.2" \
        --network "Encora Sites Combined Inventory List.xlsx" --network-sheet Sheet1 \
        --telecom "Telcom Inventory.xlsx" --telecom-sheet "WAN Circuit Detail"
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import ModuleSessionLocal, module_engine, verify_module_schema
from app.services.asset_workbook_import import (
    apply_cost_center_reference, apply_plan, apply_replace, load_plan, read_portal_export, read_sheet_export,
    read_workbook)

CATEGORIES = ("server", "network", "telecom")


async def run(sources, apply, report_path, add_new=True, export_path=None):
    reference = digest = None
    if export_path:
        workbooks, reference, digest = read_portal_export(export_path)
    else:
        workbooks = {category: read_workbook(path, sheet) for category, (path, sheet) in sources.items()}
    export = export_path is not None
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "applied": apply, "categories": {}}
    try:
        async with ModuleSessionLocal() as session:
            try:
                await verify_module_schema(session)
                for category, workbook in workbooks.items():
                    plan = await apply_plan(session, category, workbook, add_new, export) if apply else (
                        await load_plan(session, category, workbook, add_new=add_new, export=export))[0]
                    report["categories"][category] = {
                        "summary": plan.summary(), "new_records": [
                            {"source_row": item["source_row"], "name": item["name"]} for item in plan.creates],
                        "ambiguous": plan.ambiguous, "skipped": plan.skipped, "conflicts_kept": plan.conflicts,
                        "updated_records": [{"name": item["name"], "source_row": item["source_row"],
                                             "filled": item["fills_by_header"],
                                             "reviews_imported": len(item.get("reviews") or {})} for item in plan.updates],
                    }
                if reference:
                    report["cost_center_reference"] = await apply_cost_center_reference(
                        session, reference, export_path.name, digest)
                await (session.commit() if apply else session.rollback())
            except BaseException:
                await session.rollback()
                raise
    finally:
        await module_engine.dispose()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    for category, details in report["categories"].items():
        summary = details["summary"]
        print(f"{category}: {summary['source_file']} [{summary['source_sheet']}] rows={summary['source_rows']} "
              f"matched={summary['matched_records']} updated={summary['records_updated']} "
              f"cells_filled={summary['cells_filled']} conflicts_kept={summary['conflicts_kept']} "
              f"new={summary['new_records']} ambiguous={summary['ambiguous_rows']} skipped={summary['skipped_rows']} "
              f"reviews_imported={summary['reviews_imported']} added_columns={summary['added_columns']}")
    if "cost_center_reference" in report:
        reference_result = report["cost_center_reference"]
        print(f"cost-center reference: rows={reference_result['rows']} added={reference_result['added']} "
              f"unchanged={reference_result['unchanged']} conflicts={len(reference_result['conflicts'])}")
    print(("Changes committed." if apply else "Dry run only; nothing was saved.") + f" Report: {report_path}")


async def run_replace(category, export_path, apply, report_path):
    source = read_sheet_export(export_path)
    try:
        async with ModuleSessionLocal() as session:
            try:
                await verify_module_schema(session)
                plan = await apply_replace(session, category, source)
                await (session.commit() if apply else session.rollback())
            except BaseException:
                await session.rollback()
                raise
    finally:
        await module_engine.dispose()
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "applied": apply, "summary": plan.summary(),
              "new_records": [{"source_row": item["source_row"], "name": item["name"]} for item in plan.creates],
              "retired_records": [{"name": record["name"]} for record in plan.retired],
              "needs_review": plan.review,
              "updated_records": [{"name": item["record"]["name"], "source_row": item["source_row"],
                                   "changes": {header: {"before": before, "after": after}
                                               for header, (before, after) in item["changes"].items()}}
                                  for item in plan.matched if item["changes"]]}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    summary = plan.summary()
    print(f"{category} replace from {summary['source_file']} [{summary['source_sheet']}]: "
          f"matched={summary['matched_records']} updated={summary['records_updated']} "
          f"cells_changed={summary['cells_changed']} cells_cleared={summary['cells_cleared']} "
          f"new={summary['new_records']} retired={summary['retired_records']} needs_review={summary['needs_review']}")
    print(("Changes committed." if apply else "Dry run only; nothing was saved.") + f" Report: {report_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for category in CATEGORIES:
        parser.add_argument(f"--{category}", type=Path, help=f"{category} workbook path")
        parser.add_argument(f"--{category}-sheet", help=f"worksheet to read from the {category} workbook")
    parser.add_argument("--portal-export", type=Path,
                        help="Assets Analytics JSON export; imports all categories and the cost-center reference")
    parser.add_argument("--replace", choices=CATEGORIES,
                        help="make this category hold exactly the rows of --sheet-export (other categories untouched)")
    parser.add_argument("--sheet-export", type=Path, help="single-sheet JSON export used with --replace")
    parser.add_argument("--apply", action="store_true", help="commit the changes (default is a dry run)")
    parser.add_argument("--fill-only", action="store_true", help="only fill empty cells of matched records; add no new assets")
    parser.add_argument("--report", type=Path, help="JSON report path (default: logs/asset-workbook-import-*.json)")
    args = parser.parse_args()
    sources = {}
    for category in CATEGORIES:
        path, sheet = getattr(args, category), getattr(args, f"{category}_sheet")
        if path is None:
            continue
        if not sheet:
            parser.error(f"--{category}-sheet is required with --{category}")
        if not path.is_file():
            parser.error(f"{path} does not exist")
        sources[category] = (path.resolve(), sheet)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.replace:
        if sources or args.portal_export or not args.sheet_export or not args.sheet_export.is_file():
            parser.error("--replace needs an existing --sheet-export file and no other sources")
        report = args.report or Path(__file__).resolve().parents[1] / "logs" / f"asset-replace-{args.replace}-{stamp}.json"
        asyncio.run(run_replace(args.replace, args.sheet_export.resolve(), args.apply, report.resolve()))
        return
    if args.portal_export and sources:
        parser.error("use either --portal-export or workbook paths, not both")
    if args.portal_export and not args.portal_export.is_file():
        parser.error(f"{args.portal_export} does not exist")
    if not sources and not args.portal_export:
        parser.error("provide at least one workbook or --portal-export")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = args.report or Path(__file__).resolve().parents[1] / "logs" / f"asset-workbook-import-{stamp}.json"
    asyncio.run(run(sources, args.apply, report.resolve(), add_new=not args.fill_only,
                    export_path=args.portal_export.resolve() if args.portal_export else None))


if __name__ == "__main__":
    main()
