"""Reconcile operator-supplied workbooks into persisted Assets Analytics records.

Matched records only receive values for cells that are empty in the portal, so
operator edits and existing values are never overwritten. Matches that cannot be
established reliably are reported and left unchanged. Unmatched rows with a
usable identity are added as workbook-sourced records.
"""

import hashlib
import json
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, update

from app.models.asset_review import AssetInventoryAudit, AssetInventoryBatch, AssetInventoryRecord
from app.services.asset_inventory_service import AssetInventoryCategory, AssetInventoryService
from app.services.asset_review_service import REFERENCE_CATEGORY, AssetReviewConflict, record_name

ACTOR = "Workbook import"
ACTION = "workbook-import"
PLACEHOLDERS = {"", "-", "--", "?", "NA", "N/A", "NONE", "NULL", "NOT ASSIGNED", "NOT AVAILABLE", "NEED TO CHECK"}
KEY_PLACEHOLDERS = {re.sub(r"\s+", "", value) for value in PLACEHOLDERS | {"VIRTUAL MACHINE", "NOT IN USE"}}
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T|$)")


def clean(value):
    if isinstance(value, str):
        value = value.strip()
        if value.upper() in PLACEHOLDERS:
            return None
    return value


def blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def identity(value):
    if value is None:
        return ""
    text = re.sub(r"\s+", "", str(value)).upper()
    return "" if text in KEY_PLACEHOLDERS else text


def date_only(value):
    return value if isinstance(value, str) and ISO_DATE.match(value) else None


def comparable(value):
    text = str(value).strip().casefold()
    return text[:10] if ISO_DATE.match(text) else text


@dataclass(frozen=True)
class Mapping:
    source: str
    target: str
    transform: object = None


@dataclass(frozen=True)
class Profile:
    category: AssetInventoryCategory
    mappings: tuple
    new_columns: tuple
    identity_columns: tuple


NETWORK = Profile(AssetInventoryCategory.NETWORK, (
    Mapping("Location", "SITE"), Mapping("Device", "TYPE"), Mapping("Hostname", "HOST NAME"),
    Mapping("Host IP", "IP ADDRESS"), Mapping("Make", "PROVIDER"), Mapping("Make", "MAKE"), Mapping("Model", "MODEL"),
    Mapping("Serial Number", "SERIAL NUMBER"), Mapping("AMC Status", "AMC"),
    Mapping("AMC Expiry Date", "AMC END DATE"), Mapping("EOL Date", "EOL"), Mapping("Country", "COUNTRY"),
    Mapping("Firmware/IOS Version", "FIRMWARE/IOS VERSION"), Mapping("Login Status", "LOGIN STATUS"),
), ("COUNTRY", "MAKE", "FIRMWARE/IOS VERSION", "LOGIN STATUS"), ("SERIAL NUMBER", "HOST NAME"))

TELECOM = Profile(AssetInventoryCategory.TELECOM, (
    Mapping("Region", "Region"), Mapping("Site Location", "Location"), Mapping("Entity", "Entity"),
    Mapping("Provider", "Provider"), Mapping("Circuit ID", "Provider Circuit ID"), Mapping("Roles", "Type"),
    Mapping("AMC Status", "Renewal Start Date", date_only), Mapping("AMC End Date", "Renewal End Date", date_only),
), (), ("Provider Circuit ID",))

SERVER_EXTRA = (Mapping("Validation", "WORKBOOK VALIDATION"), Mapping("Validated by", "WORKBOOK VALIDATED BY"))


def server_profile(columns):
    shared = tuple(Mapping(column, column) for column in columns if column != "S.N")
    return Profile(AssetInventoryCategory.SERVER, shared + SERVER_EXTRA,
                   tuple(mapping.target for mapping in SERVER_EXTRA), ("HOST NAME",))


@dataclass
class CategoryPlan:
    category: str
    source_file: str
    source_sheet: str
    sha256: str
    base_columns: list
    columns: list
    added_columns: list
    source_rows: int = 0
    updates: list = field(default_factory=list)
    creates: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    ambiguous: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    unchanged_matches: int = 0
    unused_source_columns: list = field(default_factory=list)

    def summary(self):
        fills = Counter(header for update_ in self.updates for header in update_["fills_by_header"])
        conflicts = Counter(conflict["header"] for conflict in self.conflicts)
        return {
            "category": self.category, "source_file": self.source_file, "source_sheet": self.source_sheet,
            "source_rows": self.source_rows, "added_columns": self.added_columns,
            "matched_records": len(self.updates) + self.unchanged_matches,
            "records_updated": len(self.updates), "matched_without_changes": self.unchanged_matches,
            "cells_filled": sum(fills.values()), "cells_filled_by_column": dict(fills),
            "conflicts_kept": len(self.conflicts), "conflicts_by_column": dict(conflicts),
            "reviews_imported": sum(len(item.get("reviews") or {}) for item in self.updates + self.creates),
            "new_records": len(self.creates), "ambiguous_rows": len(self.ambiguous),
            "skipped_rows": len(self.skipped), "unused_source_columns": self.unused_source_columns,
        }


def _cells(record):
    return {cell["header"]: cell["value"] for cell in record["data"]}


def _index(items, key):
    result = defaultdict(list)
    for item in items:
        value = key(item)
        if value:
            result[value].append(item)
    return result


def _same_model(left, right):
    a, b = (re.sub(r"[^a-z0-9]", "", str(value or "").casefold()) for value in (left, right))
    return bool(a and b and (a == b or a in b or b in a))


def _match_by_host(rows, records):
    portal = _index(records, lambda record: identity(_cells(record).get("HOST NAME")))
    repeated = Counter(identity(row["mapped"].get("HOST NAME")) for row in rows)
    for row in rows:
        host = identity(row["mapped"].get("HOST NAME"))
        found = portal.get(host, [])
        if not host:
            yield row, "skip", "Workbook row has no usable host name."
        elif repeated[host] > 1:
            yield row, "ambiguous", "Host name repeats in the workbook."
        elif len(found) > 1:
            yield row, "ambiguous", "Host name matches several portal records."
        elif found:
            yield row, "match", found[0]
        else:
            yield row, "new", None


def _match_network(rows, records):
    def keys(values):
        return (identity(values.get("SERIAL NUMBER")), identity(values.get("HOST NAME")),
                identity(values.get("IP ADDRESS")))

    record_keys = {record["id"]: keys(_cells(record)) for record in records}
    by_serial, by_host, by_ip = (_index(records, lambda record, n=n: record_keys[record["id"]][n]) for n in range(3))
    row_keys = [keys(row["mapped"]) for row in rows]
    repeated = [Counter(key[n] for key in row_keys) for n in range(3)]

    def unique(index, n, key):
        found = index.get(key, [])
        return found[0] if key and len(found) == 1 and repeated[n][key] == 1 else None

    for row, (serial, host, ip) in zip(rows, row_keys):
        candidates = by_serial.get(serial, []) + by_host.get(host, []) + by_ip.get(ip, [])
        host_record, ip_records = unique(by_host, 1, host), by_ip.get(ip, [])
        record = unique(by_serial, 0, serial)
        if record:
            confirmed = host and record_keys[record["id"]][1] == host
            if host_record and host_record is not record:
                yield row, "ambiguous", "Serial number and host name identify different portal records."
            elif ip_records and record not in ip_records and not confirmed:
                yield row, "ambiguous", "Serial number and IP address identify different portal records."
            else:
                yield row, "match", record
            continue
        if host_record:
            portal_serial, portal_ip = record_keys[host_record["id"]][0], record_keys[host_record["id"]][2]
            if serial and portal_serial and serial != portal_serial:
                yield row, "ambiguous", "Host name matches, but the serial number differs."
            elif ip and portal_ip and ip != portal_ip:
                yield row, "ambiguous", "Host name matches, but the IP address differs."
            else:
                yield row, "match", host_record
            continue
        ip_record = unique(by_ip, 2, ip)
        if ip_record and not by_host.get(host):
            portal_serial = record_keys[ip_record["id"]][0]
            if serial and portal_serial and serial != portal_serial:
                yield row, "ambiguous", "IP address matches, but the serial number differs."
            elif not _same_model(_cells(ip_record).get("MODEL"), row["mapped"].get("MODEL")):
                yield row, "ambiguous", "IP address matches a record with a different model."
            else:
                yield row, "match", ip_record
            continue
        if candidates:
            yield row, "ambiguous", "Identifiers repeat or point to different portal records."
        elif not (serial or host or ip):
            yield row, "skip", "Workbook row has no serial number, host name or IP address."
        else:
            yield row, "new", None


def _match_telecom(rows, records):
    def fallback(values):
        return tuple(identity(values.get(column)) for column in ("S.N", "Region", "Location", "Provider"))

    by_circuit = _index(records, lambda record: identity(_cells(record).get("Provider Circuit ID")))
    by_fallback = _index(records, lambda record: "|".join(fallback(_cells(record))))
    repeated = Counter(identity(row["mapped"].get("Provider Circuit ID")) for row in rows)
    for row in rows:
        circuit = identity(row["mapped"].get("Provider Circuit ID"))
        values = {**row["mapped"], "S.N": row["values"].get("S.N")}
        found = by_circuit.get(circuit, []) if circuit and repeated[circuit] == 1 else []
        if not found and all(fallback(values)):
            found = by_fallback.get("|".join(fallback(values)), [])
        if len(found) == 1:
            portal = _cells(found[0])
            if all(identity(portal.get(column)) == identity(values.get(column)) for column in ("Location", "Provider")):
                yield row, "match", found[0]
            else:
                yield row, "ambiguous", "Circuit ID matches, but the location or provider differs."
        elif found or (circuit and by_circuit.get(circuit)):
            yield row, "ambiguous", "Circuit identifiers repeat in the workbook or portal."
        else:
            yield row, "new", None


MATCHERS = {
    AssetInventoryCategory.SERVER: _match_by_host,
    AssetInventoryCategory.NETWORK: _match_network,
    AssetInventoryCategory.TELECOM: _match_telecom,
}

# Data columns in the portal export that would collide with the UI's own review columns.
EXPORT_RENAMES = {"Validation": "WORKBOOK VALIDATION", "Validated by": "WORKBOOK VALIDATED BY",
                  "Validated on": "WORKBOOK VALIDATED ON"}
IDENTITY_COLUMNS = {
    AssetInventoryCategory.SERVER: ("HOST NAME",),
    AssetInventoryCategory.NETWORK: NETWORK.identity_columns,
    AssetInventoryCategory.TELECOM: TELECOM.identity_columns,
}


def export_profile(category, export_columns, batch_columns):
    category = AssetInventoryCategory(category)
    mappings = tuple(Mapping(column, EXPORT_RENAMES.get(column, column)) for column in export_columns if column != "S.N")
    new_columns = tuple(m.target for m in mappings if m.target not in batch_columns)
    return Profile(category, mappings, new_columns, IDENTITY_COLUMNS[category])


def _match_network_export(rows, records):
    """Portal exports keep the inventory row number; confirm it with the device identifiers."""
    by_row = _index(records, lambda record: identity(_cells(record).get("S.N")))
    repeated = Counter(identity(row["values"].get("S.N")) for row in rows)
    unresolved = []
    for row in rows:
        number = identity(row["values"].get("S.N"))
        found = by_row.get(number, []) if number and repeated[number] == 1 else []
        if len(found) != 1:
            unresolved.append(row)
            continue
        portal, source = _cells(found[0]), row["values"]
        same = all(identity(portal.get(column)) == identity(source.get(column))
                   for column in ("HOST NAME", "IP ADDRESS", "MODEL", "SITE"))
        portal_serial, source_serial = identity(portal.get("SERIAL NUMBER")), identity(source.get("SERIAL NUMBER"))
        if same and (not portal_serial or not source_serial or portal_serial == source_serial):
            yield row, "match", found[0]
        elif same:
            yield row, "ambiguous", "Row number, host name, IP, model and site match, but the serial number differs."
        else:
            unresolved.append(row)
    yield from _match_network(unresolved, records)


def _same_value(left, right):
    return (blank(left) and blank(right)) or (not blank(left) and not blank(right) and comparable(left) == comparable(right))


def _review_imports(row, data_values, position, existing_reviews, renames):
    imported = {}
    for header, review in (row.get("reviews") or {}).items():
        target = renames.get(header, header)
        index = position.get(target)
        if index is None or str(index) in existing_reviews:
            continue
        if _same_value(data_values.get(target), review.get("value")):
            imported[index] = {"header": target, "value": data_values.get(target),
                               "validated_at": review["validated_at"], "validated_by": review["validated_by"]}
    return imported


def build_plan(category, workbook, batch_columns, records, deleted_identities=frozenset(), add_new=True,
               profile=None, matcher=None):
    """Plan a fill-only reconciliation without touching storage.

    ``records`` are active portal records as dicts with ``id``, ``name``,
    ``revision``, ``data`` and optionally ``field_reviews``. ``deleted_identities``
    holds identity keys of records an operator deleted; those are never re-created.
    Source rows may carry ``reviews`` (header -> review) and ``validation``; a
    review is imported only where the resulting cell equals the reviewed value.
    """
    category = AssetInventoryCategory(category)
    profile = profile or (server_profile(batch_columns) if category is AssetInventoryCategory.SERVER else (
        NETWORK if category is AssetInventoryCategory.NETWORK else TELECOM))
    matcher = matcher or MATCHERS[category]
    renames = {m.source: m.target for m in profile.mappings}
    added = [column for column in profile.new_columns if column not in batch_columns]
    columns = list(batch_columns) + added
    missing = [m.target for m in profile.mappings if m.target not in columns]
    if missing:
        raise ValueError(f"{category.value} inventory has no column for: {', '.join(missing)}")
    mappings = [m for m in profile.mappings if m.source in workbook["columns"]]
    plan = CategoryPlan(category.value, workbook["source_file"], workbook["source_sheet"], workbook.get("sha256", ""),
                        list(batch_columns), columns, added, source_rows=len(workbook["rows"]))
    rows = []
    for row in workbook["rows"]:
        mapped = {}
        for mapping in mappings:
            value = clean(row["values"].get(mapping.source))
            value = mapping.transform(value) if mapping.transform and value is not None else value
            if value is not None:
                mapped[mapping.target] = value
        rows.append({**row, "mapped": mapped})
    used = {m.source for m in mappings}
    plan.unused_source_columns = [column for column in workbook["columns"] if column not in used and column != "S.N"]

    position = {header: index for index, header in enumerate(columns)}
    matched = defaultdict(list)
    for row, outcome, detail in matcher(rows, records):
        if outcome == "match":
            matched[detail["id"]].append((row, detail))
        elif outcome == "new":
            keys = {identity(row["mapped"].get(column)) for column in profile.identity_columns} - {""}
            if not add_new:
                plan.skipped.append({"source_row": row["source_row"], "identity": _label(row, profile),
                                     "reason": "No matching portal record; new assets are disabled for this import."})
                continue
            if keys & deleted_identities:
                plan.skipped.append({"source_row": row["source_row"], "identity": _label(row, profile),
                                     "reason": "An operator deleted this asset in the portal."})
                continue
            data = [{"index": index, "header": header, "value": row["mapped"].get(header)}
                    for index, header in enumerate(columns)]
            reviews = _review_imports(row, row["mapped"], position, {}, renames)
            plan.creates.append({"source_row": row["source_row"], "name": record_name(data, row["source_row"]),
                                 "data": data, "reviews": reviews, "validation": row.get("validation"),
                                 "origin": row.get("origin")})
        else:
            target = plan.skipped if outcome == "skip" else plan.ambiguous
            target.append({"source_row": row["source_row"], "identity": _label(row, profile), "reason": detail})

    for pairs in matched.values():
        if len(pairs) > 1:
            for row, record in pairs:
                plan.ambiguous.append({"source_row": row["source_row"], "identity": _label(row, profile),
                                       "reason": f"Several workbook rows match portal record {record['name']}."})
            continue
        row, record = pairs[0]
        current = _cells(record)
        fills = {}
        for header, value in row["mapped"].items():
            existing = current.get(header)
            if blank(existing):
                fills[position[header]] = value
            elif comparable(existing) != comparable(value):
                plan.conflicts.append({"record": record["name"], "header": header, "portal_value": existing,
                                       "workbook_value": value, "source_row": row["source_row"]})
        final = {**current, **{columns[index]: value for index, value in fills.items()}}
        existing_reviews = {key: review for key, review in (record.get("field_reviews") or {}).items()
                            if int(key) not in fills}
        reviews = _review_imports(row, final, position, existing_reviews, renames)
        if fills or reviews:
            plan.updates.append({"record_id": record["id"], "revision": record["revision"], "name": record["name"],
                                 "source_row": row["source_row"], "fills": fills, "reviews": reviews,
                                 "validation": row.get("validation"), "origin": row.get("origin"),
                                 "fills_by_header": {columns[index]: value for index, value in fills.items()}})
        else:
            plan.unchanged_matches += 1
    return plan


def _label(row, profile):
    values = row["mapped"]
    parts = [str(values[column]) for column in profile.identity_columns + ("IP ADDRESS",) if values.get(column)]
    return " / ".join(parts) or f"row {row['source_row']}"


def read_workbook(path, sheet):
    snapshot = AssetInventoryService.read_sheet(path, sheet)
    snapshot["sha256"] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return snapshot


def read_portal_export(path):
    """Read an Assets Analytics JSON export into per-category import sources."""
    path = Path(path)
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    digest = hashlib.sha256(raw).hexdigest()
    sources = {}
    for category, block in (payload.get("categories") or {}).items():
        AssetInventoryCategory(category)
        columns = [str(column) for column in block["columns"]]
        rows = []
        for record in block["records"]:
            values = {cell["header"]: cell["value"] for cell in record["data"]}
            if set(values) - set(columns):
                raise ValueError(f"{category} export record {record.get('id')} has cells outside its columns.")
            rows.append({
                "source_row": record.get("source_row") or 0, "values": values,
                "reviews": {review["header"]: review for review in (record.get("field_reviews") or {}).values()},
                "validation": {key: record.get(key) for key in ("is_validated", "validated_at", "validated_by")},
                "origin": {key: record.get(key) for key in ("id", "source_file", "source_sheet", "source_row")},
            })
        sources[category] = {"columns": columns, "rows": rows, "source_file": path.name,
                             "source_sheet": block.get("source_sheet") or category, "sha256": digest}
    return sources, payload.get("admin_cost_center_reference"), digest


def _reference_value(value):
    if isinstance(value, str):
        value = value.strip()
    return None if value == "" else value


async def apply_cost_center_reference(session, reference, source_file, digest):
    """Store the admin cost-center reference as standalone rows; never link it to devices."""
    columns = [str(column) for column in reference["columns"]]
    now = datetime.now(timezone.utc)
    batch = (await session.execute(select(AssetInventoryBatch).where(
        AssetInventoryBatch.category == REFERENCE_CATEGORY).with_for_update())).scalar_one_or_none()
    if batch is None:
        batch = AssetInventoryBatch(category=REFERENCE_CATEGORY, source_file=source_file[:255],
                                    source_sheet="admin_cost_center_reference", columns=columns,
                                    created_at=now, updated_at=now)
        session.add(batch)
    elif batch.columns != columns:
        raise ValueError("The stored cost-center reference uses different columns; review it before re-importing.")
    existing = {row.source_key: row for row in (await session.execute(select(AssetInventoryRecord).where(
        AssetInventoryRecord.category == REFERENCE_CATEGORY))).scalars()}
    order = max((row.source_order for row in existing.values()), default=-1)
    result = {"rows": len(reference["records"]), "added": 0, "unchanged": 0, "conflicts": []}
    for item in reference["records"]:
        data = [{"index": index, "header": header, "value": _reference_value(item.get(header))}
                for index, header in enumerate(columns)]
        key = f"reference:{item['source_row']}"
        if key in existing:
            if existing[key].data == data:
                result["unchanged"] += 1
            else:
                result["conflicts"].append({"source_row": item["source_row"], "reason": "Stored row differs; kept."})
            continue
        values = {cell["header"]: cell["value"] for cell in data}
        name = " · ".join(str(values[h]) for h in ("CC Code", "Cost Center Name") if values.get(h)) or \
            f"Reference row {item['source_row']}"
        order += 1
        identifier = uuid.uuid4()
        session.add(AssetInventoryRecord(
            id=identifier, category=REFERENCE_CATEGORY, source_key=key, name=name[:512],
            source_file=source_file[:255], source_sheet="admin_cost_center_reference",
            source_row=item["source_row"], source_order=order, data=data, field_reviews={}, is_validated=False,
            revision=1, is_deleted=False, created_at=now, updated_at=now))
        session.add(AssetInventoryAudit(category=REFERENCE_CATEGORY, record_id=str(identifier), action=ACTION,
                                        actor=ACTOR, details={"source_file": source_file, "after": data}))
        result["added"] += 1
    session.add(AssetInventoryAudit(category=REFERENCE_CATEGORY, record_id=f"batch:{REFERENCE_CATEGORY}",
                                    action=ACTION, actor=ACTOR, details={**result, "sha256": digest}))
    await session.flush()
    return result


def _validation_state(data, reviews, source_validation=None):
    """Keep a source's verified status while every populated cell carries a review."""
    populated = [cell for cell in data if not blank(cell["value"])]
    if (source_validation and source_validation.get("is_validated") and source_validation.get("validated_at")
            and populated and all(str(cell["index"]) in reviews for cell in populated)):
        return True, datetime.fromisoformat(source_validation["validated_at"]), source_validation.get("validated_by")
    complete = len(reviews) == len(data)
    latest = max(reviews.values(), key=lambda review: review["validated_at"]) if reviews else None
    if complete and latest:
        return True, datetime.fromisoformat(latest["validated_at"]), latest["validated_by"]
    return False, None, None


async def load_plan(session, category, workbook, lock=False, add_new=True, export=False):
    category = AssetInventoryCategory(category)
    query = select(AssetInventoryBatch).where(AssetInventoryBatch.category == category.value)
    batch = (await session.execute(query.with_for_update() if lock else query)).scalar_one_or_none()
    if batch is None:
        raise LookupError(f"{category.value} inventory has not been initialised in the portal.")
    rows = (await session.execute(select(AssetInventoryRecord).where(
        AssetInventoryRecord.category == category.value))).scalars().all()
    deleted_ids = set((await session.execute(select(AssetInventoryAudit.record_id).where(
        AssetInventoryAudit.category == category.value, AssetInventoryAudit.action == "delete"))).scalars())
    deleted = {identity(_cells({"data": row.data}).get(column)) for row in rows
               if row.is_deleted and str(row.id) in deleted_ids for column in IDENTITY_COLUMNS[category]} - {""}
    active = [{"id": str(row.id), "name": row.name, "revision": row.revision, "data": row.data,
               "field_reviews": row.field_reviews or {}} for row in rows if not row.is_deleted]
    profile = export_profile(category, workbook["columns"], batch.columns) if export else None
    matcher = _match_network_export if export and category is AssetInventoryCategory.NETWORK else None
    plan = build_plan(category, workbook, batch.columns, active, frozenset(deleted), add_new, profile, matcher)
    return plan, batch, rows


async def apply_plan(session, category, workbook, add_new=True, export=False):
    """Apply a freshly computed plan in the caller's transaction."""
    plan, batch, rows = await load_plan(session, category, workbook, lock=True, add_new=add_new, export=export)
    now = datetime.now(timezone.utc)
    updates = {update_["record_id"]: update_ for update_ in plan.updates}
    for row in rows:
        if len(row.data) != len(plan.base_columns):
            raise AssetReviewConflict(f"Record {row.id} does not match the {category} column layout.")
        update_ = updates.get(str(row.id))
        if not plan.added_columns and not update_:
            continue
        data = [dict(cell) for cell in row.data] + [
            {"index": len(plan.base_columns) + offset, "header": header, "value": None}
            for offset, header in enumerate(plan.added_columns)]
        reviews = dict(row.field_reviews or {})
        for index, value in (update_["fills"] if update_ else {}).items():
            data[index]["value"] = value
            reviews.pop(str(index), None)
        for index, review in (update_.get("reviews") or {} if update_ else {}).items():
            reviews[str(index)] = review
        validated, validated_at, validated_by = _validation_state(
            data, reviews, update_.get("validation") if update_ and not row.is_deleted else None)
        result = await session.execute(update(AssetInventoryRecord).where(
            AssetInventoryRecord.id == row.id, AssetInventoryRecord.revision == row.revision).values(
            data=data, field_reviews=reviews, is_validated=validated, revision=row.revision + 1, updated_at=now,
            validated_at=validated_at, validated_by=validated_by,
        ).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise AssetReviewConflict("Inventory changed during the import. No changes were saved; rerun it.")
        if update_:
            session.add(AssetInventoryAudit(category=plan.category, record_id=str(row.id), action=ACTION, actor=ACTOR,
                                            details={"source_file": plan.source_file, "source_sheet": plan.source_sheet,
                                                     "source_row": update_["source_row"], "origin": update_.get("origin"),
                                                     "filled": update_["fills_by_header"],
                                                     "reviews_imported": sorted(
                                                         review["header"] for review in update_["reviews"].values())}))
    order = (await session.execute(select(func.max(AssetInventoryRecord.source_order)).where(
        AssetInventoryRecord.category == plan.category))).scalar_one()
    order = -1 if order is None else order
    for offset, create in enumerate(plan.creates, start=1):
        identifier = uuid.uuid4()
        origin = create.get("origin") or {}
        sheet = (f"{origin['source_file']} / {origin['source_sheet']}" if origin.get("source_file")
                 else plan.source_sheet)
        key = (f"export:{origin['id']}" if origin.get("id")
               else f"workbook:{plan.source_file}:{plan.source_sheet}:{create['source_row']}")
        reviews = {str(index): review for index, review in (create.get("reviews") or {}).items()}
        validated, validated_at, validated_by = _validation_state(create["data"], reviews, create.get("validation"))
        session.add(AssetInventoryRecord(
            id=identifier, category=plan.category, name=create["name"][:512],
            source_key=key[:512],
            source_file=plan.source_file[:255], source_sheet=sheet[:255], source_row=create["source_row"],
            source_order=order + offset, data=create["data"], field_reviews=reviews, is_validated=validated,
            validated_at=validated_at, validated_by=validated_by, revision=1,
            is_deleted=False, created_at=now, updated_at=now))
        session.add(AssetInventoryAudit(category=plan.category, record_id=str(identifier), action=ACTION, actor=ACTOR,
                                        details={"source_file": plan.source_file, "source_sheet": plan.source_sheet,
                                                 "source_row": create["source_row"], "origin": origin,
                                                 "after": create["data"]}))
    if plan.added_columns:
        batch.columns = plan.columns
        batch.updated_at = now
    session.add(AssetInventoryAudit(category=plan.category, record_id=f"batch:{plan.category}", action=ACTION,
                                    actor=ACTOR, details={**plan.summary(), "sha256": plan.sha256}))
    await session.flush()
    return plan


def read_sheet_export(path):
    """Read a single-sheet JSON export (``columns`` and ``records`` with ``data`` cells)."""
    path = Path(path)
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    columns = [str(column) for column in payload["columns"]]
    rows = []
    for record in payload["records"]:
        values = {cell["header"]: cell["value"] for cell in record["data"]}
        if set(values) - set(columns):
            raise ValueError(f"Export row {record.get('source_row')} has cells outside its columns.")
        rows.append({"source_row": int(record.get("source_row") or 0), "values": values})
    return {"columns": columns, "rows": rows, "source_file": payload.get("source_file") or path.name,
            "source_sheet": payload.get("source_sheet") or "", "sha256": payload.get("source_sha256") or
            hashlib.sha256(raw).hexdigest(), "export_file": path.name}


def _source_value(value):
    if isinstance(value, str):
        value = value.strip()
    return None if value == "" else value


@dataclass
class ReplacePlan:
    category: str
    source_file: str
    source_sheet: str
    columns: list
    matched: list = field(default_factory=list)
    creates: list = field(default_factory=list)
    retired: list = field(default_factory=list)
    review: list = field(default_factory=list)
    cells_changed: Counter = field(default_factory=Counter)
    cells_cleared: Counter = field(default_factory=Counter)
    dropped_columns: list = field(default_factory=list)

    def summary(self):
        return {"category": self.category, "source_file": self.source_file, "source_sheet": self.source_sheet,
                "columns": self.columns, "matched_records": len(self.matched),
                "records_updated": sum(1 for item in self.matched if item["changes"]),
                "cells_changed": sum(self.cells_changed.values()), "cells_changed_by_column": dict(self.cells_changed),
                "cells_cleared": sum(self.cells_cleared.values()), "new_records": len(self.creates),
                "retired_records": len(self.retired), "needs_review": len(self.review),
                "dropped_columns": self.dropped_columns}


def plan_replace(source, live_columns, records, renames=EXPORT_RENAMES, identity_column="HOST NAME", confirm=None):
    """Plan making a category hold exactly the source rows (values verbatim, matched by identity)."""
    columns = [renames.get(column, column) for column in source["columns"]]
    if len(set(columns)) != len(columns):
        raise ValueError("Source columns are not unique after renaming.")
    plan = ReplacePlan(None, source["source_file"], source["source_sheet"], columns)
    by_identity = _index(records, lambda record: identity(_cells(record).get(identity_column)))
    repeated = Counter(identity(row["values"].get(identity_column)) for row in source["rows"])
    serials = Counter(identity(row["values"].get("SERIAL NUMBER")) for row in source["rows"])
    portal_serials = {identity(_cells(record).get("SERIAL NUMBER")) for record in records} - {""}
    hostless = _index([record for record in records if not identity(_cells(record).get(identity_column))],
                      lambda record: identity(_cells(record).get("SERIAL NUMBER")))
    matched_ids = set()
    for row in source["rows"]:
        values = {renames.get(header, header): _source_value(value) for header, value in row["values"].items()}
        data = [{"index": index, "header": header, "value": values.get(header)} for index, header in enumerate(columns)]
        key = identity(values.get(identity_column))
        found = by_identity.get(key, []) if key else []
        serial = identity(values.get("SERIAL NUMBER"))
        if not key and serial and serials[serial] == 1 and len(hostless.get(serial, [])) == 1:
            key, found, repeated[key] = serial, hostless[serial], 1
        if key and repeated[key] == 1 and len(found) == 1 and confirm and not confirm(_cells(found[0]), values):
            plan.review.append({"source_row": row["source_row"], "identity": values.get(identity_column),
                                "outcome": "added",
                                "reason": "Row number matches a record with different device identifiers; "
                                          "added as a new record and the old one retired."})
            found = []
        if key and repeated[key] == 1 and len(found) == 1:
            record = found[0]
            current = _cells(record)
            changes = {header: (current.get(header), values.get(header)) for header in columns
                       if not _same_value(current.get(header), values.get(header))}
            for header, (before, after) in changes.items():
                (plan.cells_cleared if blank(after) else plan.cells_changed)[header] += 1
            plan.matched.append({"record": record, "source_row": row["source_row"], "data": data, "changes": changes,
                                 "name": _replace_name(data, values, row["source_row"])})
            matched_ids.add(record["id"])
        elif key and (repeated[key] > 1 or len(found) > 1):
            plan.review.append({"source_row": row["source_row"], "identity": values.get(identity_column),
                                "outcome": "not_added",
                                "reason": f"{identity_column} repeats; not added."})
        else:
            serial = identity(values.get("SERIAL NUMBER"))
            if not key and (not serial or serials[serial] > 1 or serial in portal_serials):
                plan.review.append({"source_row": row["source_row"], "identity": values.get("SERIAL NUMBER"),
                                    "outcome": "not_added",
                                    "reason": f"No usable {identity_column} and no unique serial number; not added."})
                continue
            plan.creates.append({"source_row": row["source_row"], "data": data,
                                 "name": _replace_name(data, values, row["source_row"])})
            if not key:
                plan.review.append({"source_row": row["source_row"], "identity": values.get("SERIAL NUMBER"),
                                    "outcome": "added", "reason": f"Added from the source, but its {identity_column} is "
                                              f"{values.get(identity_column)!r}."})
    plan.retired = [record for record in records if record["id"] not in matched_ids]
    return plan


def _replace_name(data, values, source_row):
    if not identity(values.get("HOST NAME")) and identity(values.get("SERIAL NUMBER")):
        return f"{values.get('SERIAL NUMBER')} (no host name)"
    return record_name(data, source_row)


def network_identifiers_agree(portal, source):
    """Confirm an S.N match: host, IP, model and site agree and serials are compatible."""
    same = all(identity(portal.get(column)) == identity(source.get(column))
               for column in ("HOST NAME", "IP ADDRESS", "MODEL", "SITE"))
    left, right = identity(portal.get("SERIAL NUMBER")), identity(source.get("SERIAL NUMBER"))
    return same and (not left or not right or left == right)


def telecom_identifiers_agree(portal, source):
    """Confirm an S.N match for circuits across the old and new telecom header names."""
    def value(record, *names):
        return next((identity(record.get(name)) for name in names if name in record), "")
    circuit = (value(portal, "Circuit ID", "Provider Circuit ID"), value(source, "Circuit ID", "Provider Circuit ID"))
    location = (value(portal, "Site Location", "Location"), value(source, "Site Location", "Location"))
    return (circuit[0] == circuit[1] and location[0] == location[1]
            and value(portal, "Provider") == value(source, "Provider"))


async def apply_replace(session, category, source, identity_column="HOST NAME", confirm=None, allow_drop=False):
    """Make one category hold exactly the source rows; other categories are untouched."""
    category = AssetInventoryCategory(category)
    batch = (await session.execute(select(AssetInventoryBatch).where(
        AssetInventoryBatch.category == category.value).with_for_update())).scalar_one_or_none()
    if batch is None:
        raise LookupError(f"{category.value} inventory has not been initialised in the portal.")
    rows = (await session.execute(select(AssetInventoryRecord).where(
        AssetInventoryRecord.category == category.value))).scalars().all()
    active = [{"id": str(row.id), "name": row.name, "revision": row.revision, "data": row.data,
               "field_reviews": row.field_reviews or {}} for row in rows if not row.is_deleted]
    plan = plan_replace(source, batch.columns, active, identity_column=identity_column, confirm=confirm)
    plan.category = category.value
    dropped = [column for column in batch.columns if column not in plan.columns]
    if dropped and not allow_drop:
        raise ValueError(f"Replacement source lacks existing columns {dropped}; refusing to discard them.")
    plan.dropped_columns = dropped
    now = datetime.now(timezone.utc)
    by_id = {str(row.id): row for row in rows}
    provenance = {"source_file": plan.source_file[:255], "source_sheet": plan.source_sheet[:255]}

    def reshaped(row):
        values = {cell["header"]: cell["value"] for cell in row.data}
        return [{"index": index, "header": header, "value": values.get(header)}
                for index, header in enumerate(plan.columns)]

    async def write(row, values, action, details):
        result = await session.execute(update(AssetInventoryRecord).where(
            AssetInventoryRecord.id == row.id, AssetInventoryRecord.revision == row.revision).values(
            revision=row.revision + 1, updated_at=now, **values).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise AssetReviewConflict("Inventory changed during the import. No changes were saved; rerun it.")
        session.add(AssetInventoryAudit(category=plan.category, record_id=str(row.id), action=action, actor=ACTOR,
                                        details=details))

    for item in plan.matched:
        row = by_id[item["record"]["id"]]
        old = {cell["header"]: (str(cell["index"]), cell["value"]) for cell in row.data}
        reviews = {}
        for cell in item["data"]:
            previous = old.get(cell["header"])
            review = (row.field_reviews or {}).get(previous[0]) if previous else None
            if review and _same_value(previous[1], cell["value"]):
                reviews[str(cell["index"])] = {**review, "header": cell["header"]}
        validated, validated_at, validated_by = _validation_state(item["data"], reviews)
        if not item["changes"] and row.data == item["data"] and row.source_row == item["source_row"] \
                and row.source_file == provenance["source_file"] and row.name == item["name"]:
            continue
        await write(row, {"data": item["data"], "field_reviews": reviews, "is_validated": validated,
                          "validated_at": validated_at, "validated_by": validated_by, "name": item["name"][:512],
                          "source_row": item["source_row"], **provenance}, "workbook-replace",
                    {**provenance, "source_row": item["source_row"],
                     "changes": {header: {"before": before, "after": after}
                                 for header, (before, after) in item["changes"].items()}})
    for record in plan.retired:
        row = by_id[record["id"]]
        await write(row, {"is_deleted": True, "data": reshaped(row)}, "workbook-retire",
                    {**provenance, "reason": "Not present in the replacement source.", "before": row.data})
    for row in rows:
        if row.is_deleted and [cell["header"] for cell in row.data] != plan.columns:
            result = await session.execute(update(AssetInventoryRecord).where(
                AssetInventoryRecord.id == row.id, AssetInventoryRecord.revision == row.revision).values(
                data=reshaped(row), revision=row.revision + 1).execution_options(synchronize_session=False))
            if result.rowcount != 1:
                raise AssetReviewConflict("Inventory changed during the import. No changes were saved; rerun it.")
    order = max((row.source_order for row in rows), default=-1)
    for item in plan.creates:
        order += 1
        identifier = uuid.uuid4()
        session.add(AssetInventoryRecord(
            id=identifier, category=plan.category, name=item["name"][:512],
            source_key=f"source:{plan.source_file}:{plan.source_sheet}:{item['source_row']}:{identifier.hex[:8]}"[-512:],
            source_row=item["source_row"], source_order=order, data=item["data"], field_reviews={},
            is_validated=False, revision=1, is_deleted=False, created_at=now, updated_at=now, **provenance))
        session.add(AssetInventoryAudit(category=plan.category, record_id=str(identifier), action=ACTION,
                                        actor=ACTOR, details={**provenance, "source_row": item["source_row"],
                                                              "after": item["data"]}))
    batch.columns = plan.columns
    batch.source_file, batch.source_sheet = provenance["source_file"], provenance["source_sheet"]
    batch.updated_at = now
    session.add(AssetInventoryAudit(category=plan.category, record_id=f"batch:{plan.category}",
                                    action="workbook-replace", actor=ACTOR,
                                    details={**plan.summary(), "sha256": source.get("sha256"),
                                             "export_file": source.get("export_file"),
                                             "dropped_columns": plan.dropped_columns,
                                             "removed_source_columns": source.get("removed_columns", []),
                                             "retired": [record["name"] for record in plan.retired],
                                             "needs_review": plan.review}))
    await session.flush()
    return plan


def read_csv_source(path):
    """Read a CSV inventory export; blank lines are skipped, values are kept as text."""
    import csv
    import io
    path = Path(path)
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    lines = list(csv.reader(io.StringIO(text)))
    header = [column.strip() for column in lines[0]]
    columns = AssetInventoryService._unique_headers(header)
    rows = []
    for number, line in enumerate(lines[1:], start=2):
        if not any(cell.strip() for cell in line):
            continue
        if len(line) > len(columns) and any(cell.strip() for cell in line[len(columns):]):
            raise ValueError(f"CSV line {number} has values beyond the header columns.")
        rows.append({"source_row": number,
                     "values": {column: (line[index] if index < len(line) else None) for index, column in enumerate(columns)}})
    return {"columns": columns, "rows": rows, "source_file": path.name, "source_sheet": "CSV",
            "sha256": hashlib.sha256(raw).hexdigest(), "export_file": path.name}


def read_sheet_source(path, sheet):
    snapshot = AssetInventoryService.read_sheet(path, sheet)
    snapshot["sha256"] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return snapshot


def prune_source_columns(source, drop=(), drop_empty=True):
    """Remove completely empty columns and explicitly named redundant ones, recording why."""
    removed = [{"column": column, "reason": reason} for column, reason in drop]
    names = {item["column"] for item in removed}
    unknown = names - set(source["columns"])
    if unknown:
        raise ValueError(f"Cannot drop unknown columns: {sorted(unknown)}")
    if drop_empty:
        for column in source["columns"]:
            if column not in names and all(blank(_source_value(row["values"].get(column))) for row in source["rows"]):
                removed.append({"column": column, "reason": "Empty in every row."})
                names.add(column)
    columns = [column for column in source["columns"] if column not in names]
    rows = [{**row, "values": {column: row["values"].get(column) for column in columns}} for row in source["rows"]]
    return {**source, "columns": columns, "rows": rows, "removed_columns": removed}


async def verify_by_column(session, category, column, when, note, reviewer_name=None):
    """Mark every active record verified, attributing each to the value in ``column`` (operator instruction).

    With ``reviewer_name`` every record is attributed to that named reviewer instead.
    """
    category = AssetInventoryCategory(category)
    rows = (await session.execute(select(AssetInventoryRecord).where(
        AssetInventoryRecord.category == category.value, AssetInventoryRecord.is_deleted.is_(False))
        .execution_options(populate_existing=True))).scalars().all()
    stamp = when.isoformat()
    verified, skipped = 0, []
    for row in rows:
        reviewer = reviewer_name or next((cell["value"] for cell in row.data if cell["header"] == column), None)
        reviewer = str(reviewer).strip() if not blank(reviewer) else None
        if not reviewer:
            skipped.append(row.name)
            continue
        reviews = {str(cell["index"]): {"header": cell["header"], "value": cell["value"], "validated_at": stamp,
                                        "validated_by": reviewer[:128]} for cell in row.data}
        result = await session.execute(update(AssetInventoryRecord).where(
            AssetInventoryRecord.id == row.id, AssetInventoryRecord.revision == row.revision).values(
            field_reviews=reviews, is_validated=True, validated_at=when, validated_by=reviewer[:128],
            revision=row.revision + 1, updated_at=when).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise AssetReviewConflict("Inventory changed during the import. No changes were saved; rerun it.")
        session.add(AssetInventoryAudit(category=category.value, record_id=str(row.id), action="validate",
                                        actor=reviewer[:128], details={"note": note, "validated_by_column": column,
                                                                       "validated_at": stamp}))
        verified += 1
    await session.flush()
    return {"verified": verified, "skipped_without_reviewer": skipped}
