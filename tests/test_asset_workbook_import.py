import uuid

import openpyxl
import pytest
from sqlalchemy import select

from app.models.asset_review import AssetInventoryAudit, AssetInventoryRecord
from app.services.asset_inventory_service import AssetInventoryCategory, AssetInventoryService
from app.services.asset_review_service import AssetReviewConflict, AssetReviewService
from app.services.asset_workbook_import import apply_plan, build_plan, load_plan, read_workbook

SERVER_COLUMNS = ["S.N", "HOST NAME", "IP ADDRESS", "SERIAL NUMBER", "SERVER OWNER"]
NETWORK_COLUMNS = ["S.N", "SITE", "TYPE", "HOST NAME", "IP ADDRESS", "PROVIDER", "MODEL", "SERIAL NUMBER",
                   "EOL", "AMC", "AMC END DATE"]
TELECOM_COLUMNS = ["S.N", "Region", "Location", "Entity", "Provider", "Provider Circuit ID", "Type",
                   "Renewal Start Date", "Renewal End Date"]


def record(identifier, columns, values, revision=1):
    data = [{"index": index, "header": header, "value": values.get(header)} for index, header in enumerate(columns)]
    return {"id": identifier, "name": values.get("HOST NAME") or identifier, "revision": revision, "data": data}


def workbook(columns, rows, sheet="Sheet1"):
    return {"columns": columns, "source_file": "source.xlsx", "source_sheet": sheet,
            "rows": [{"source_row": index + 2, "values": dict(zip(columns, row))} for index, row in enumerate(rows)]}


def cell(plan_item, header):
    return next(cell["value"] for cell in plan_item["data"] if cell["header"] == header)


def test_server_plan_fills_only_blanks_and_reports_conflicts_new_and_unusable_rows():
    records = [record("a", SERVER_COLUMNS, {"S.N": 1, "HOST NAME": "SRV-01", "SERVER OWNER": "Edited Owner"}),
               record("b", SERVER_COLUMNS, {"S.N": 2, "HOST NAME": "srv-02", "IP ADDRESS": "10.0.0.2"})]
    source = workbook(SERVER_COLUMNS + ["Validation", "Validated by", "Validated on"], [
        [9, " srv-01 ", "10.0.0.1", "SN1", "Workbook Owner", "Yes", "Reviewer", None],
        [10, "SRV-02", "10.0.0.99", "N/A", None, "Pending", None, None],
        [11, "SRV-03", "10.0.0.3", "SN3", "Owner", "Yes", "Reviewer", None],
        [12, "?", "?", "SN4", "Owner", "Yes", "Reviewer", None],
        [13, "SRV-DELETED", None, None, None, None, None, None],
    ], sheet="V.2")

    plan = build_plan("server", source, SERVER_COLUMNS, records, frozenset({"SRV-DELETED"}))

    assert plan.added_columns == ["WORKBOOK VALIDATION", "WORKBOOK VALIDATED BY"]
    fills = {item["name"]: item["fills_by_header"] for item in plan.updates}
    assert fills["SRV-01"] == {"IP ADDRESS": "10.0.0.1", "SERIAL NUMBER": "SN1", "WORKBOOK VALIDATION": "Yes",
                               "WORKBOOK VALIDATED BY": "Reviewer"}
    assert fills["srv-02"] == {"WORKBOOK VALIDATION": "Pending"}
    assert {(c["record"], c["header"]) for c in plan.conflicts} == {("SRV-01", "SERVER OWNER"),
                                                                    ("srv-02", "IP ADDRESS")}
    assert [item["name"] for item in plan.creates] == ["SRV-03"]
    created = plan.creates[0]
    assert cell(created, "S.N") is None and cell(created, "WORKBOOK VALIDATED BY") == "Reviewer"
    assert {item["reason"] for item in plan.skipped} == {"Workbook row has no usable host name.",
                                                         "An operator deleted this asset in the portal."}
    assert plan.unused_source_columns == ["Validated on"]


def test_server_plan_never_guesses_when_host_names_repeat():
    records = [record("a", SERVER_COLUMNS, {"HOST NAME": "SRV-01"})]
    source = workbook(SERVER_COLUMNS, [[1, "SRV-01", "10.0.0.1", None, None], [2, "srv-01", "10.0.0.2", None, None]])
    plan = build_plan("server", source, SERVER_COLUMNS, records)
    assert not plan.updates and not plan.creates and len(plan.ambiguous) == 2


def test_fill_only_plan_fills_matches_without_adding_assets():
    records = [record("a", SERVER_COLUMNS, {"HOST NAME": "SRV-01"})]
    source = workbook(SERVER_COLUMNS, [[1, "SRV-01", "10.0.0.1", None, None], [2, "SRV-NEW", "10.0.0.2", None, None]])
    plan = build_plan("server", source, SERVER_COLUMNS, records, add_new=False)
    assert plan.updates[0]["fills_by_header"]["IP ADDRESS"] == "10.0.0.1"
    assert not plan.creates and plan.skipped[0]["identity"] == "SRV-NEW / 10.0.0.2"


ENCORA = ["Location", "Country", "Device", "Hostname", "Host IP", "Make", "Model", "Serial Number", "AMC Status",
          "AMC Expiry Date", "EOL Date", "Firmware/IOS Version", "Login Status"]


def test_network_plan_matches_reliable_identifiers_and_leaves_uncertain_pairs_alone():
    def device(identifier, host, ip, serial, model="FG-400E", eol="Not Announced"):
        return record(identifier, NETWORK_COLUMNS, {"HOST NAME": host, "IP ADDRESS": ip, "SERIAL NUMBER": serial,
                                                    "MODEL": model, "EOL": eol, "SITE": "Pune"})
    records = [
        device("fw1", "PUNE-FW1", "10.0.0.1", "SER-B"), device("fw2", "PUNE-FW2", "10.0.0.1", "SER-A"),
        device("mon", "NA", "NA", "SER-MON", "CISCO2911/K9"),
        device("ap", "Wireless", "10.0.5.5", None, "7 Pro Max"),
        device("stby", "ASA-STBY", "10.0.9.2", "SER-OLD"),
        device("sw2", "SW2", "10.0.7.2", "SER-DUP"),
    ]
    source = workbook(ENCORA, [
        ["Pune", "India", "Firewall", "PUNE-FW1", "10.0.0.1", "Fortinet", "FortiGate-400E", "SER-A", "Covered",
         "2027-01-01T00:00:00", "Not announced", "v7.4", "Able to Login"],
        ["Pune", "India", "Firewall", "PUNE-FW2", "10.0.0.1", "Fortinet", "FortiGate-400E", "SER-B", "Covered",
         None, None, "v7.4", None],
        ["Montreal", "Canada", "Router", "CAN-RT01", "10.21.0.1", "Cisco", "CISCO2911/K9", "SER-MON", "Expired",
         "N/A", None, "15.1", None],
        ["SJC", "USA", "Access Point", "SJC-AP01", "10.0.5.5", "Ubiquiti", "7 Pro Max", "e4:38", "No AMC",
         None, None, "6.8.2", None],
        ["SAB", "Brazil", "Firewall", "ASA-STBY", "10.0.9.2", "Cisco", "ASA", "SER-NEW", "Covered", None, None,
         "9.8", None],
        ["Hermosillo", "Mexico", "Switch", "SW2", "10.0.7.2", "Ubiquiti", "USW", "SER-DUP", "No AMC", None, None,
         "7.1", None],
        ["Hermosillo", "Mexico", "Switch", "SW3", "10.0.7.3", "Ubiquiti", "USW", "SER-DUP", "No AMC", None, None,
         "7.1", None],
        ["Pune", "India", "Analyzer", "PUNE-FAZ", "10.0.0.35", "Fortinet", "FortiAnalyzer VM", "FAZ-1", "Covered",
         None, "Not announced", "7.2", None],
    ])

    plan = build_plan("network", source, NETWORK_COLUMNS, records)

    assert plan.added_columns == ["COUNTRY", "MAKE", "FIRMWARE/IOS VERSION", "LOGIN STATUS"]
    updated = {item["record_id"]: item["fills_by_header"] for item in plan.updates}
    assert set(updated) == {"mon", "ap", "sw2"}
    assert updated["mon"] == {"TYPE": "Router", "PROVIDER": "Cisco", "MAKE": "Cisco", "AMC": "Expired",
                              "COUNTRY": "Canada", "FIRMWARE/IOS VERSION": "15.1"}
    assert updated["ap"]["SERIAL NUMBER"] == "e4:38"
    reasons = {item["identity"].split(" / ")[1]: item["reason"] for item in plan.ambiguous}
    assert reasons["PUNE-FW1"] == reasons["PUNE-FW2"] == "Serial number and host name identify different portal records."
    assert reasons["ASA-STBY"] == "Host name matches, but the serial number differs."
    assert reasons["SW3"] == "Identifiers repeat or point to different portal records."
    assert [item["name"] for item in plan.creates] == ["PUNE-FAZ"]
    assert cell(plan.creates[0], "TYPE") == "Analyzer" and cell(plan.creates[0], "SITE") == "Pune"
    assert any(c["record"] == "NA" and c["header"] == "HOST NAME" for c in plan.conflicts)


def test_telecom_plan_fills_renewal_dates_from_date_values_only():
    records = [
        record("c1", TELECOM_COLUMNS, {"S.N": 1, "Region": "India", "Location": "Pune", "Provider": "TCL",
                                       "Provider Circuit ID": "091PUNE", "Type": "ILL(P2P)"}),
        record("c2", TELECOM_COLUMNS, {"S.N": 2, "Region": "India", "Location": "Noida", "Provider": "Airtel",
                                       "Provider Circuit ID": "Not Available", "Type": "ILL"}),
    ]
    source = workbook(["S.N", "Region", "Site Location", "Entity", "Roles", "Host name", "Provider", "Circuit ID",
                       "AMC Status", "AMC End Date"], [
        [1, "India", "Pune", "Coforge LTD", "ILL", None, "TCL", "091PUNE", "2026-01-01T00:00:00",
         "2026-12-31T00:00:00"],
        [2, "India", "Noida", "Coforge LTD", "ILL", None, "Airtel", "Not Available", "Active", None],
    ], sheet="WAN Circuit Detail")

    plan = build_plan("telecom", source, TELECOM_COLUMNS, records)

    assert plan.added_columns == [] and not plan.creates and not plan.ambiguous
    updated = {item["record_id"]: item["fills_by_header"] for item in plan.updates}
    assert updated["c1"] == {"Entity": "Coforge LTD", "Renewal Start Date": "2026-01-01T00:00:00",
                             "Renewal End Date": "2026-12-31T00:00:00"}
    assert updated["c2"] == {"Entity": "Coforge LTD"}
    assert [(c["header"], c["portal_value"]) for c in plan.conflicts] == [("Type", "ILL(P2P)")]
    assert plan.unused_source_columns == ["Host name"]


def save(path, sheet, rows):
    book = openpyxl.Workbook()
    book.active.title = sheet
    for row in rows:
        book.active.append(row)
    book.save(path)
    book.close()


@pytest.mark.asyncio
async def test_apply_is_transactional_idempotent_and_preserves_operator_state(session, tmp_path):
    save(tmp_path / "server.xlsx", "CHARGEBACK MASTER", [SERVER_COLUMNS, [1, "SRV-01", None, None, "Owner"],
                                                         [2, "SRV-02", "10.0.0.2", None, None]])
    save(tmp_path / "backup.xlsx", "V.2", [SERVER_COLUMNS + ["Validation", "Validated by"],
                                           [7, "SRV-01", "10.0.0.1", "SN1", "Other", "Yes", "Reviewer"],
                                           [8, "SRV-02", "10.0.0.2", "SN2", None, "Yes", "Reviewer"],
                                           [9, "SRV-09", "10.0.0.9", "SN9", "Owner", "Yes", "Reviewer"]])
    reviews = AssetReviewService(session, AssetInventoryService(tmp_path))
    await reviews.ensure_source(AssetInventoryCategory.SERVER)
    listed = await reviews.list(AssetInventoryCategory.SERVER, 1, 25, "")
    first = next(item for item in listed["items"] if item["name"] == "SRV-01")
    validated = await reviews.change(AssetInventoryCategory.SERVER, uuid.UUID(first["id"]),
                                     type("Body", (), {"expected_revision": 1, "actor": "Reviewer"})(), "validate")
    assert validated["is_validated"] is True
    await session.commit()
    source = read_workbook(tmp_path / "backup.xlsx", "V.2")

    plan = await apply_plan(session, "server", source)
    await session.commit()

    assert plan.summary()["new_records"] == 1 and plan.summary()["conflicts_kept"] == 1
    page = await reviews.list(AssetInventoryCategory.SERVER, 1, 25, "")
    assert page["columns"] == SERVER_COLUMNS + ["WORKBOOK VALIDATION", "WORKBOOK VALIDATED BY"]
    rows = {item["name"]: item for item in page["items"]}
    values = {name: {cell["header"]: cell["value"] for cell in row["data"]} for name, row in rows.items()}
    assert values["SRV-01"]["SERVER OWNER"] == "Owner" and values["SRV-01"]["IP ADDRESS"] == "10.0.0.1"
    assert rows["SRV-01"]["revision"] == 3 and rows["SRV-01"]["is_validated"] is False
    assert "2" not in rows["SRV-01"]["field_reviews"] and "1" in rows["SRV-01"]["field_reviews"]
    assert values["SRV-09"]["WORKBOOK VALIDATED BY"] == "Reviewer" and rows["SRV-09"]["source_sheet"] == "V.2"
    actions = (await session.execute(select(AssetInventoryAudit.action))).scalars().all()
    assert actions.count("workbook-import") == 4
    summary = next(item for item in (await reviews.summary())["items"] if item["category"] == "server")
    assert summary["last_import"]["updated"] == 2 and summary["last_import"]["added"] == 1
    assert summary["last_import"]["at"].endswith("+00:00")

    again, _, _ = await load_plan(session, "server", source)
    assert not again.updates and not again.creates and not again.added_columns

    srv09 = rows["SRV-09"]
    await reviews.change(AssetInventoryCategory.SERVER, uuid.UUID(srv09["id"]),
                         type("Body", (), {"expected_revision": 1, "actor": "Operator"})(), "delete")
    await session.commit()
    after_delete, _, _ = await load_plan(session, "server", source)
    assert not after_delete.creates
    assert after_delete.skipped[0]["reason"] == "An operator deleted this asset in the portal."


@pytest.mark.asyncio
async def test_apply_aborts_without_partial_writes_when_layout_changed(session, tmp_path):
    save(tmp_path / "server.xlsx", "CHARGEBACK MASTER", [SERVER_COLUMNS, [1, "SRV-01", None, None, None]])
    save(tmp_path / "backup.xlsx", "V.2", [SERVER_COLUMNS, [1, "SRV-01", "10.0.0.1", None, None]])
    await AssetReviewService(session, AssetInventoryService(tmp_path)).ensure_source(AssetInventoryCategory.SERVER)
    await session.commit()
    row = (await session.execute(select(AssetInventoryRecord))).scalar_one()
    row.data = row.data[:-1]
    await session.commit()
    with pytest.raises(AssetReviewConflict):
        await apply_plan(session, "server", read_workbook(tmp_path / "backup.xlsx", "V.2"))
    await session.rollback()
    stored = (await session.execute(select(AssetInventoryRecord))).scalar_one()
    assert stored.revision == 1 and not (await session.execute(select(AssetInventoryAudit))).scalars().all()


def export_file(tmp_path, categories, reference=None):
    import json
    path = tmp_path / "export.json"
    path.write_text(json.dumps({"exported_at_utc": "2026-11-16T16:32:55+00:00", "categories": categories,
                                "admin_cost_center_reference": reference}), encoding="utf-8")
    return path


def export_record(identifier, columns, values, reviewer=None):
    data = [{"index": index, "header": header, "value": values.get(header)} for index, header in enumerate(columns)]
    reviews = {str(cell["index"]): {"header": cell["header"], "value": cell["value"],
                                    "validated_at": "2026-11-12T09:56:16+00:00", "validated_by": reviewer}
               for cell in data if reviewer and cell["header"] in values}
    return {"id": identifier, "name": values.get("HOST NAME"), "source_file": "network.xlsx", "source_sheet": "v1.1",
            "source_row": values.get("S.N", 0) + 1, "data": data, "field_reviews": reviews,
            "is_validated": bool(reviewer), "validated_at": "2026-11-12T09:56:16+00:00" if reviewer else None,
            "validated_by": reviewer, "revision": 2}


@pytest.mark.asyncio
async def test_portal_export_matches_by_row_imports_reviews_and_keeps_reference_unassigned(session, tmp_path):
    from app.services.asset_workbook_import import apply_cost_center_reference, read_portal_export
    live_columns = ["S.N", "SITE", "HOST NAME", "IP ADDRESS", "MODEL", "SERIAL NUMBER", "OWNER", "AMC"]
    rows = [live_columns, [1, "Pune", "NA", "NA", "C9200", "SER1", None, None],
            [2, "Pune", "NA", "NA", "C9200", "SER2", None, "Covered"],
            [3, "Pune", "SW3", "10.0.0.3", "C9300", "SER3", None, None]]
    save(tmp_path / "network.xlsx", "NETWORK INVENTORY", rows)
    reviews = AssetReviewService(session, AssetInventoryService(tmp_path))
    await reviews.ensure_source(AssetInventoryCategory.NETWORK)
    await session.commit()
    columns = live_columns + ["Validation", "CC Code"]
    def values(number, serial, amc, host="NA", ip="NA", model="C9200"):
        return {"S.N": number, "SITE": "Pune", "HOST NAME": host, "IP ADDRESS": ip, "MODEL": model,
                "SERIAL NUMBER": serial, "OWNER": "Owner", "AMC": amc, "Validation": "Verified"}
    path = export_file(tmp_path, {"network": {"columns": columns, "source_sheet": "v1.1", "total": "3", "records": [
        export_record("a", columns, values(1, "SER1", "Covered"), "Reviewer"),
        export_record("b", columns, values(2, "SER2", "Uncovered"), "Reviewer"),
        export_record("c", columns, values(3, "OTHER", None, "SW3", "10.0.0.3", "C9300"), "Reviewer"),
    ]}}, {"columns": ["Entity", "CC Code", "Cost Center Name"],
          "records": [{"source_row": 1, "Entity": "N001", "CC Code": "998953", "Cost Center Name": ""}]})
    sources, reference, digest = read_portal_export(path)

    plan = await apply_plan(session, "network", sources["network"], export=True)
    added = await apply_cost_center_reference(session, reference, path.name, digest)
    await session.commit()

    assert plan.added_columns == ["WORKBOOK VALIDATION", "CC Code"]
    assert [item["reason"] for item in plan.ambiguous] == [
        "Row number, host name, IP, model and site match, but the serial number differs."]
    page = await reviews.list(AssetInventoryCategory.NETWORK, 1, 25, "")
    rows = {cell(item, "SERIAL NUMBER"): item for item in page["items"]}
    first, second, third = rows["SER1"], rows["SER2"], rows["SER3"]
    assert cell(first, "OWNER") == "Owner" and cell(first, "AMC") == "Covered" and cell(first, "CC Code") is None
    assert first["is_validated"] is True and first["validated_by"] == "Reviewer"
    assert cell(second, "AMC") == "Covered" and second["is_validated"] is False
    assert "7" not in second["field_reviews"] and second["field_reviews"]["6"]["validated_by"] == "Reviewer"
    assert cell(third, "OWNER") is None and third["field_reviews"] == {}
    assert added == {"rows": 1, "added": 1, "unchanged": 0, "conflicts": []}
    stored = await reviews.cost_center_reference()
    assert stored["items"] == [{"source_row": 1, "values": {"Entity": "N001", "CC Code": "998953",
                                                             "Cost Center Name": None}}]
    assert [item["category"] for item in (await reviews.summary())["items"]] == ["server", "network", "telecom"]

    again, _, _ = await load_plan(session, "network", read_portal_export(path)[0]["network"], export=True)
    assert not again.updates and not again.creates and not again.added_columns
    assert (await apply_cost_center_reference(session, reference, path.name, digest))["unchanged"] == 1


@pytest.mark.asyncio
async def test_replace_makes_servers_match_source_only_and_leaves_other_categories(session, tmp_path):
    import json
    from app.services.asset_workbook_import import apply_replace, read_sheet_export
    live = ["S.N", "HOST NAME", "IP ADDRESS", "SERIAL NUMBER", "SERVER OWNER", "WORKBOOK VALIDATION"]
    save(tmp_path / "server.xlsx", "CHARGEBACK MASTER", [live, [1, "SRV-01", "10.0.0.1", "SN1", "Edited", None],
                                                         [2, "SRV-02", "10.0.0.2", "SN2", "Owner", None],
                                                         [3, "SRV-OLD", "10.0.0.3", "SN3", "Owner", None]])
    save(tmp_path / "network.xlsx", "NETWORK INVENTORY", [["HOST NAME", "SITE"], ["SW-01", "Pune"]])
    reviews = AssetReviewService(session, AssetInventoryService(tmp_path))
    await reviews.ensure_source(AssetInventoryCategory.SERVER)
    await reviews.ensure_source(AssetInventoryCategory.NETWORK)
    network_before = (await reviews.list(AssetInventoryCategory.NETWORK, 1, 25, ""))["items"]
    first = next(item for item in (await reviews.list(AssetInventoryCategory.SERVER, 1, 25, ""))["items"]
                 if item["name"] == "SRV-01")
    for index in (1, 4):
        await reviews.change(AssetInventoryCategory.SERVER, uuid.UUID(first["id"]),
                             type("Body", (), {"expected_revision": first["revision"], "actor": "Reviewer"})(),
                             "validate_field", index)
        first["revision"] += 1
    await session.commit()
    source_columns = ["S.N", "HOST NAME", "IP ADDRESS", "SERIAL NUMBER", "SERVER OWNER", "Validation", "Validated by",
                      "Validated on"]
    def row(number, values):
        return {"source_row": number + 1, "name": values[1],
                "data": [{"index": i, "header": h, "value": v} for i, (h, v) in enumerate(zip(source_columns, values))]}
    path = tmp_path / "v2.json"
    path.write_text(json.dumps({"source_file": "backup.xlsx", "source_sheet": "V.2", "source_sha256": "abc",
                                "columns": source_columns, "records": [
        row(7, [7, "srv-01", "10.0.0.1", "SN1", "V2 Owner", "Yes", "Avnish", None]),
        row(8, [8, "SRV-02", "10.0.0.20", "", None, "Pending", None, None]),
        row(9, [9, "?", "?", "SN9", "Owner", "Yes", "Avnish", None])]}), encoding="utf-8")

    plan = await apply_replace(session, "server", read_sheet_export(path))
    await session.commit()

    page = await reviews.list(AssetInventoryCategory.SERVER, 1, 25, "")
    assert page["columns"] == ["S.N", "HOST NAME", "IP ADDRESS", "SERIAL NUMBER", "SERVER OWNER",
                               "WORKBOOK VALIDATION", "WORKBOOK VALIDATED BY", "WORKBOOK VALIDATED ON"]
    assert page["source_sheet"] == "V.2"
    rows = {item["name"]: {cell["header"]: cell["value"] for cell in item["data"]} | {"_": item}
            for item in page["items"]}
    assert set(rows) == {"srv-01", "SRV-02", "SN9 (no host name)"}
    assert rows["srv-01"]["SERVER OWNER"] == "V2 Owner" and rows["srv-01"]["S.N"] == 7
    assert rows["srv-01"]["WORKBOOK VALIDATION"] == "Yes" and rows["srv-01"]["_"]["is_validated"] is False
    assert set(rows["srv-01"]["_"]["field_reviews"]) == {"1"}
    assert rows["SRV-02"]["SERIAL NUMBER"] is None and rows["SRV-02"]["SERVER OWNER"] is None
    assert rows["SN9 (no host name)"]["HOST NAME"] == "?" and rows["SRV-02"]["_"]["source_row"] == 9
    assert [record["name"] for record in plan.retired] == ["SRV-OLD"]
    assert plan.review[0]["reason"].startswith("Added from the source")
    assert (await reviews.list(AssetInventoryCategory.NETWORK, 1, 25, ""))["items"] == network_before
    stored = (await session.execute(select(AssetInventoryRecord).where(AssetInventoryRecord.category == "server"))).scalars().all()
    assert all([cell["header"] for cell in row_.data] == page["columns"] for row_ in stored)

    again = await apply_replace(session, "server", read_sheet_export(path))
    assert not again.creates and not again.retired
    assert not any(item["changes"] for item in again.matched) and len(again.matched) == 3
    assert not again.review


def test_csv_source_skips_blank_lines_and_prune_records_reasons(tmp_path):
    from app.services.asset_workbook_import import prune_source_columns, read_csv_source
    path = tmp_path / "servers.csv"
    path.write_bytes("S.N,HOST NAME,OWNER,Validated on\r\n1,SRV-01,Jos\xe9,\r\n,,,\r\n2,SRV-02,,\r\n".encode("cp1252"))
    source = read_csv_source(path)
    assert [row["source_row"] for row in source["rows"]] == [2, 4]
    assert source["rows"][0]["values"]["OWNER"] == "Jos\xe9"
    pruned = prune_source_columns(source, drop=[("S.N", "Row number only")])
    assert pruned["columns"] == ["HOST NAME", "OWNER"]
    assert pruned["removed_columns"] == [{"column": "S.N", "reason": "Row number only"},
                                         {"column": "Validated on", "reason": "Empty in every row."}]
    assert pruned["rows"][1]["values"] == {"HOST NAME": "SRV-02", "OWNER": ""}
    with pytest.raises(ValueError):
        prune_source_columns(source, drop=[("Missing", "x")])


@pytest.mark.asyncio
async def test_network_replace_by_row_number_drops_columns_and_verifies_by_owner(session, tmp_path):
    from datetime import datetime, timezone
    from app.services.asset_workbook_import import (
        apply_replace, network_identifiers_agree, prune_source_columns, read_sheet_source, verify_by_column)
    live = ["S.N", "SITE", "HOST NAME", "IP ADDRESS", "MODEL", "SERIAL NUMBER", "OWNER", "COUNTRY"]
    save(tmp_path / "network.xlsx", "NETWORK INVENTORY", [live,
        [1, "Pune", "NA", "NA", "C9200", "SER1", None, "India"],
        [2, "Pune", "NA", "NA", "C9200", "SER2", None, None],
        [3, "Pune", "SW3", "10.0.0.3", "C9300", "SER3", None, None]])
    save(tmp_path / "telecom.xlsx", "WAN", [["S.N", "Provider Circuit ID"], [1, "C1"]])
    reviews = AssetReviewService(session, AssetInventoryService(tmp_path))
    await reviews.ensure_source(AssetInventoryCategory.NETWORK)
    await reviews.ensure_source(AssetInventoryCategory.TELECOM)
    telecom_before = (await reviews.list(AssetInventoryCategory.TELECOM, 1, 25, ""))["items"]
    await session.commit()
    columns = ["S.N", "SITE", "HOST NAME", "IP ADDRESS", "MODEL", "SERIAL NUMBER", "OWNER", "AMC PROVIDER NAME",
               "PROJECT", "Validated by"]
    save(tmp_path / "v12.xlsx", "inventory", [columns,
        [1, "Pune", "NA", "NA", "C9200", "SER1", "Owner A", "Cisco", None, "Owner A"],
        [2, "Pune", "NA", "NA", "C9200", "SER9", "Owner B", "Cisco", None, "Owner B"],
        [3, "Pune", "SW3", "10.0.0.3", "C9300", None, "Owner C", "Cisco", None, "Owner C"],
        [4, "Noida", "SW4", "10.0.0.4", "C9300", "SER4", None, "Cisco", None, None]])
    source = prune_source_columns(read_sheet_source(tmp_path / "v12.xlsx", "inventory"),
                                  drop=[("AMC PROVIDER NAME", "Identical to PROVIDER")])
    with pytest.raises(ValueError):
        await apply_replace(session, "network", source, identity_column="S.N", confirm=network_identifiers_agree)
    await session.rollback()

    plan = await apply_replace(session, "network", source, identity_column="S.N",
                               confirm=network_identifiers_agree, allow_drop=True)
    when = datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc)
    verified = await verify_by_column(session, "network", "OWNER", when, "Operator instruction")
    await session.commit()

    assert plan.dropped_columns == ["COUNTRY"] and len(plan.retired) == 1 and len(plan.creates) == 2
    assert [item["outcome"] for item in plan.review] == ["added"]
    page = await reviews.list(AssetInventoryCategory.NETWORK, 1, 25, "")
    assert page["columns"] == ["S.N", "SITE", "HOST NAME", "IP ADDRESS", "MODEL", "SERIAL NUMBER", "OWNER",
                               "WORKBOOK VALIDATED BY"]
    rows = {cell(item, "S.N"): item for item in page["items"]}
    assert sorted(rows) == [1, 2, 3, 4]
    assert cell(rows[3], "SERIAL NUMBER") is None and cell(rows[4], "OWNER") is None
    assert rows[1]["is_validated"] is True and rows[1]["validated_by"] == "Owner A"
    assert rows[1]["field_reviews"]["6"]["validated_by"] == "Owner A"
    assert rows[4]["is_validated"] is False
    assert verified == {"verified": 3, "skipped_without_reviewer": ["SW4"]}
    assert (await reviews.list(AssetInventoryCategory.TELECOM, 1, 25, ""))["items"] == telecom_before


def test_telecom_identifiers_agree_across_old_and_new_headers():
    from app.services.asset_workbook_import import telecom_identifiers_agree
    portal = {"Provider Circuit ID": "00321251BGL", "Location": "Bengaluru", "Provider": "Singtel"}
    assert telecom_identifiers_agree(portal, {"Circuit ID": "00321251bgl ", "Site Location": "Bengaluru", "Provider": "Singtel"})
    assert not telecom_identifiers_agree(portal, {"Circuit ID": "C999", "Site Location": "Bengaluru", "Provider": "Singtel"})
    assert not telecom_identifiers_agree(portal, {"Circuit ID": "00321251BGL", "Site Location": "Pune", "Provider": "Singtel"})


@pytest.mark.asyncio
async def test_verify_with_named_reviewer_marks_every_record(session, tmp_path):
    from datetime import datetime, timezone
    from app.services.asset_workbook_import import verify_by_column
    save(tmp_path / "telecom.xlsx", "WAN", [["S.N", "Circuit ID"], [1, "C1"], [2, None]])
    reviews = AssetReviewService(session, AssetInventoryService(tmp_path))
    await reviews.ensure_source(AssetInventoryCategory.TELECOM)
    when = datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc)
    result = await verify_by_column(session, "telecom", None, when, "Operator instruction", reviewer_name="Roshan Sah")
    await session.commit()
    items = (await reviews.list(AssetInventoryCategory.TELECOM, 1, 25, ""))["items"]
    assert result == {"verified": 2, "skipped_without_reviewer": []}
    assert all(item["is_validated"] and item["validated_by"] == "Roshan Sah" for item in items)
    assert all(review["validated_by"] == "Roshan Sah" for item in items for review in item["field_reviews"].values())
