"""Isolated, local-only vendor settings service; no application imports."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import unicodedata
import uuid
import zipfile
import zlib
import xml.etree.ElementTree as ET
from urllib.parse import quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

METHODS = ("Phone", "Email", "Portal", "Other")
MAX_FILE = 10 * 1024 * 1024
MAX_BODY = 14 * 1024 * 1024
MAX_STEPS = 30
MAX_STEP_TEXT = 2000
MAX_ZIP_ENTRIES = 256
MAX_ZIP_TOTAL = 32 * 1024 * 1024
MAX_ZIP_ENTRY = 8 * 1024 * 1024
MIME_TYPES = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".txt": "text/plain; charset=utf-8"}
SAVE_MESSAGE = "Vendor methods and selected details saved. Unselected methods, prior notes and SOP revisions were kept."
HERE = Path(__file__).resolve().parent
DEFAULT_DATABASE = HERE.parent / "data" / "vendor_management.db"


def clean_text(value, label, limit, allow_empty=False):
    if not isinstance(value, str):
        raise ValueError(label + " must be text.")
    if any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError(label + " cannot contain control or invisible format characters.")
    value = " ".join(unicodedata.normalize("NFKC", value).split())
    if (not value and not allow_empty) or len(value) > limit:
        raise ValueError(label + " must contain " + ("0" if allow_empty else "1") + " to " + str(limit) + " characters.")
    return value


def email_address(value):
    if not isinstance(value, str) or any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("Vendor support email must be a single address without controls.")
    value = unicodedata.normalize("NFKC", value).strip()
    if len(value) > 254 or value.count("@") != 1:
        raise ValueError("Enter one vendor support email address, up to 254 characters.")
    local, domain = value.split("@")
    atom = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    labels = domain.split(".")
    if (not 1 <= len(local) <= 64 or not re.fullmatch(atom + r"(?:\." + atom + r")*", local)
            or len(domain) > 253 or len(labels) < 2
            or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels)
            or not re.search(r"[A-Za-z]", labels[-1])):
        raise ValueError("Enter one plain email address (for example support@vendor.com), not a display name or list.")
    return local + "@" + domain.lower()


def email_template(value, label, limit):
    if not isinstance(value, str):
        raise ValueError(label + " must be text.")
    value = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    if any(unicodedata.category(c).startswith("C") and c not in "\n\t" for c in value):
        raise ValueError(label + " cannot contain controls or invisible format characters except newlines/tabs.")
    if len(value) > limit:
        raise ValueError(label + " must be at most " + str(limit) + " characters.")
    return value


def validate_email(value):
    if (not isinstance(value, dict) or not {"address", "subject"} <= set(value)
            or set(value) - {"address", "subject", "opening", "body"}):
        raise ValueError("Email details require address and subject; only optional opening and body are allowed.")
    return {"address": email_address(value["address"]),
            "subject": clean_text(value["subject"], "Subject template", 200),
            "opening": email_template(value.get("opening", ""), "Opening / header text", 2000),
            "body": email_template(value.get("body", ""), "Message body template", 10000)}


def validate_phone(value):
    if (not isinstance(value, dict) or not {"number", "account_id"} <= set(value)
            or set(value) - {"number", "contact_name", "account_id", "extension", "notes"}):
        raise ValueError("Phone details require number and account_id; only optional contact_name, extension and notes are allowed.")
    number = clean_text(value["number"], "Phone number", 40)
    if (not re.fullmatch(r"\+?[0-9(][0-9 () .-]*[0-9)]", number)
            or not 3 <= len(re.findall(r"[0-9]", number)) <= 20):
        raise ValueError("Phone number needs 3–20 digits; use an optional leading +, spaces, parentheses, dots or hyphens (maximum 40 characters).")
    result = {"number": number}
    for key, label in (("contact_name", "Contact person name"), ("account_id", "Account ID")):
        text = clean_text(value.get(key, ""), label, 100, allow_empty=key == "contact_name")
        if text and not any(c.isalnum() for c in text):
            raise ValueError(label + " must contain a letter or digit.")
        result[key] = text
    extension = value.get("extension", "")
    if extension != "":
        extension = clean_text(extension, "Extension", 10)
        if not re.fullmatch(r"[0-9]{1,10}", extension):
            raise ValueError("Extension must contain 1–10 digits or be empty.")
    result["extension"] = extension
    result["notes"] = email_template(value.get("notes", ""), "Phone notes", 2000)
    return result


def validate_portal(value):
    if not isinstance(value, dict) or set(value) != {"what_to_do", "how_to_do"}:
        raise ValueError("Portal details require What to do and How to do only.")
    result = {}
    for key, label in (("what_to_do", "What to do"), ("how_to_do", "How to do")):
        text = email_template(value[key], label, 2000)
        if not text.strip():
            raise ValueError(label + " is required.")
        result[key] = text
    return result


def safe_xml(data):
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)", data, re.I):
        raise ValueError("SOP XML cannot contain document types or entities.")
    # Reject alternate XML encodings that could conceal the declarations above.
    try:
        text = data.decode("utf-8-sig")
        if "\x00" in text or re.search(r'encoding\s*=\s*[\"\'](?!utf-8[\"\'])', text, re.I):
            raise ValueError("SOP XML must be UTF-8.")
        return ET.fromstring(text)
    except (UnicodeError, ET.ParseError) as error:
        raise ValueError("Invalid SOP XML.") from error


def validate_docx(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if not 3 <= len(entries) <= MAX_ZIP_ENTRIES:
                raise ValueError("DOCX must contain 3–256 package entries.")
            names = [entry.filename for entry in entries]
            if len(set(names)) != len(names) or len(set(n.casefold() for n in names)) != len(names):
                raise ValueError("Duplicate DOCX package entries.")
            total = 0
            content_types = None
            document = None
            root_rels = None
            for entry in entries:
                name = entry.filename
                parts = PurePosixPath(name).parts
                if (not parts or name.startswith("/") or "\\" in name or ":" in name or ".." in parts
                        or any(unicodedata.category(c).startswith("C") for c in name)):
                    raise ValueError("Unsafe DOCX package path.")
                if entry.is_dir():
                    continue
                if (entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                        or entry.file_size > MAX_ZIP_ENTRY or entry.file_size > max(1, entry.compress_size) * 200):
                    raise ValueError("Encrypted, oversized or excessively compressed DOCX entry.")
                total += entry.file_size
                if total > MAX_ZIP_TOTAL:
                    raise ValueError("DOCX expands beyond 32 MiB.")
                lower = name.lower()
                if (any(token in lower for token in ("vbaproject", "macros", "activex", "embeddings", "customui"))
                        or not lower.endswith((".xml", ".rels", ".png", ".jpg", ".jpeg", ".gif"))):
                    raise ValueError("DOCX contains unsupported or active content.")
                # Bounded reads check actual expanded bytes and CRC, not only ZIP metadata.
                with archive.open(entry) as stream:
                    body = stream.read(MAX_ZIP_ENTRY + 1)
                    if len(body) > MAX_ZIP_ENTRY or stream.read(1):
                        raise ValueError("DOCX entry exceeds expanded size limit.")
                if len(body) != entry.file_size:
                    raise ValueError("Invalid DOCX expanded size.")
                if lower.endswith((".xml", ".rels")):
                    root = safe_xml(body)
                    if lower.endswith(".rels"):
                        for rel in root:
                            target = rel.get("Target", "")
                            kind = rel.get("Type", "").lower()
                            if (rel.get("TargetMode", "Internal") != "Internal" or target.startswith(("/", "\\"))
                                    or ":" in target or ".." in PurePosixPath(target).parts
                                    or any(t in kind for t in ("oleobject", "package", "attachedtemplate", "vbaproject", "activex"))):
                                raise ValueError("DOCX external or active relationships are not allowed.")
                    if name == "[Content_Types].xml":
                        content_types = root
                    elif name == "word/document.xml":
                        document = root
                    elif name == "_rels/.rels":
                        root_rels = root
                    for node in root.iter():
                        local = node.tag.rsplit("}", 1)[-1]
                        if local in ("altChunk", "object", "control", "fldSimple", "fldChar", "instrText"):
                            raise ValueError("DOCX embedded objects and dynamic fields are not allowed.")
                else:
                    signatures = ((".png", b"\x89PNG\r\n\x1a\n"), (".jpg", b"\xff\xd8\xff"), (".jpeg", b"\xff\xd8\xff"), (".gif", b"GIF8"))
                    if not any(lower.endswith(ext) and body.startswith(magic) for ext, magic in signatures):
                        raise ValueError("Invalid DOCX image content.")
            word_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
            rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            main_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
            if (document is None or document.tag != "{" + word_ns + "}document"
                    or content_types is None or content_types.tag != "{" + ct_ns + "}Types"
                    or root_rels is None or root_rels.tag != "{" + rel_ns + "}Relationships"):
                raise ValueError("Not a standard non-macro Word DOCX package.")
            if not any(c.get("PartName") == "/word/document.xml" and c.get("ContentType") == main_type for c in content_types):
                raise ValueError("Missing standard Word main document content type.")
            if not any(r.get("Target") == "word/document.xml" and r.get("Type", "").endswith("/officeDocument") for r in root_rels):
                raise ValueError("Missing Word document relationship.")
            for c in content_types:
                content_type = c.get("ContentType", "").lower()
                if any(t in content_type for t in ("macro", "vba", "activex", "oleobject", "executable", "html", "javascript")):
                    raise ValueError("Active DOCX content type is not allowed.")
    except (zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError, OSError, EOFError) as error:
        raise ValueError("Invalid or unsupported DOCX archive.") from error


def validate_sop(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"name", "data"}:
        raise ValueError("SOP requires a filename and base64 data.")
    name = clean_text(value["name"], "SOP filename", 150)
    if any(c in name for c in '/\\:<>"|?*') or name.startswith(".") or name.endswith((".", " ")):
        raise ValueError("SOP filename must be a simple filename, not a path.")
    extension = Path(name).suffix.lower()
    if extension not in MIME_TYPES:
        raise ValueError("Attach only PDF, DOCX or TXT.")
    encoded = value["data"]
    if not isinstance(encoded, str) or len(encoded) > ((MAX_FILE + 2) // 3) * 4:
        raise ValueError("SOP must be at most 10 MiB.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, UnicodeError) as error:
        raise ValueError("Invalid SOP base64 data.") from error
    if not 0 < len(data) <= MAX_FILE:
        raise ValueError("SOP must contain 1 byte to 10 MiB.")
    if extension == ".txt":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError as error:
            raise ValueError("TXT SOP must be UTF-8 text.") from error
        if (any(unicodedata.category(c).startswith("C") and c not in "\n\r\t" for c in text)
                or re.search(r"<\s*[!/?a-z]", text, re.I)
                or text.lstrip().startswith(("#!", "MZ", "PK\x03\x04", "%PDF-"))):
            raise ValueError("TXT SOP cannot contain markup, executable signatures or binary data.")
    elif extension == ".pdf":
        if not re.match(br"%PDF-(?:1\.[0-7]|2\.0)\s", data) or not data.rstrip().endswith(b"%%EOF"):
            raise ValueError("Invalid PDF header or trailer.")
        # Decode PDF name escapes before rejecting action/embedded-content markers.
        decoded = re.sub(br"#([0-9a-fA-F]{2})", lambda m: bytes([int(m[1], 16)]), data)
        if re.search(br"/(?:JavaScript|JS|Launch|OpenAction|AA|EmbeddedFile|Filespec|RichMedia|XFA|Encrypt|ObjStm|GoToR|SubmitForm|ImportData)\b", decoded, re.I):
            raise ValueError("PDF active, encrypted, embedded or object-stream content is not supported.")
        if not re.search(br"\b\d+\s+\d+\s+obj\b", data) or b"startxref" not in data:
            raise ValueError("Invalid PDF structure.")
    else:
        validate_docx(data)
    return {"name": name, "mime": MIME_TYPES[extension], "data": data, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def validate(payload):
    fields = {"vendor", "methods", "custom_method", "steps", "sop", "request_id", "email_details", "phone_details", "portal_details"}
    if not isinstance(payload, dict) or set(payload) - fields:
        raise ValueError("Expected vendor name, methods, steps, request_id and optional SOP/custom method.")
    vendor = clean_text(payload.get("vendor"), "Vendor name", 100)
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
        raise ValueError("A 32-character lowercase hexadecimal request_id is required.")
    methods = payload.get("methods")
    if not isinstance(methods, list) or not 1 <= len(methods) <= 4:
        raise ValueError("Select one to four ticket creation methods.")
    if any(not isinstance(m, str) or m not in METHODS for m in methods) or len(set(methods)) != len(methods):
        raise ValueError("Select distinct supported methods.")
    custom = payload.get("custom_method", "")
    if "Other" in methods:
        custom = clean_text(custom, "Custom method", 80)
        if custom.casefold() in {"email", "phone", "portal"}:
            raise ValueError("Select the Email, Phone or Portal checkbox instead of naming Other after a built-in method.")
    elif custom != "":
        raise ValueError("Custom method is only allowed when Other is selected.")
    email = None
    if "Email" in methods:
        email = validate_email(payload.get("email_details"))
    elif "email_details" in payload:
        raise ValueError("Email details are only allowed when Email is selected.")
    phone = None
    if "Phone" in methods:
        phone = validate_phone(payload.get("phone_details"))
    elif "phone_details" in payload:
        raise ValueError("Phone details are only allowed when Phone is selected.")
    portal = None
    if "Portal" in methods:
        portal = validate_portal(payload.get("portal_details"))
    elif "portal_details" in payload:
        raise ValueError("Portal details are only allowed when Portal is selected.")
    sop = validate_sop(payload.get("sop"))
    if "Portal" in methods and sop is None:
        raise ValueError("Portal requires a new SOP upload with every submission, including mixed methods. Existing SOPs do not satisfy this requirement.")
    steps = payload.get("steps")
    if not isinstance(steps, dict) or set(steps) != set(methods) & {"Other"}:
        raise ValueError("Provide steps for Other only; use an empty steps object when Other is not selected.")
    result = {}
    for method in methods:
        label = custom if method == "Other" else method
        key = label.casefold()
        if key in result:
            raise ValueError("Other duplicates a selected method. Use a distinct method name.")
        if method == "Email":
            result[key] = {"label": label, "email_details": email}
            continue
        if method == "Phone":
            result[key] = {"label": label, "phone_details": phone}
            continue
        if method == "Portal":
            result[key] = {"label": label, "portal_details": portal}
            continue
        values = steps[method]
        if not isinstance(values, list) or not 1 <= len(values) <= MAX_STEPS:
            raise ValueError(method + " needs 1–30 ordered steps.")
        result[key] = {"label": label, "steps": [clean_text(s, method + " step", MAX_STEP_TEXT) for s in values]}
    return vendor, result, sop, request_id


def connect(database):
    connection = sqlite3.connect(database, timeout=5)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(database):
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(database)
    try:
        with connection:
            connection.execute("CREATE TABLE IF NOT EXISTS vm_vendors (vendor_key TEXT PRIMARY KEY, name TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS vm_vendor_methods (vendor_key TEXT NOT NULL REFERENCES vm_vendors(vendor_key), method_key TEXT NOT NULL, label TEXT NOT NULL, PRIMARY KEY(vendor_key, method_key))")
            connection.execute("CREATE TABLE IF NOT EXISTS vm_method_steps (vendor_key TEXT NOT NULL, method_key TEXT NOT NULL, position INTEGER NOT NULL CHECK(position >= 1), instruction TEXT NOT NULL, PRIMARY KEY(vendor_key, method_key, position), FOREIGN KEY(vendor_key, method_key) REFERENCES vm_vendor_methods(vendor_key, method_key))")
            connection.execute("CREATE TABLE IF NOT EXISTS vm_sops (id TEXT PRIMARY KEY, vendor_key TEXT NOT NULL REFERENCES vm_vendors(vendor_key), name TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, data BLOB NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            connection.execute("CREATE INDEX IF NOT EXISTS vm_sops_vendor ON vm_sops(vendor_key)")
            connection.execute("CREATE TABLE IF NOT EXISTS vm_submissions (request_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS vm_email_details (vendor_key TEXT NOT NULL, method_key TEXT NOT NULL CHECK(method_key = 'email'), address TEXT NOT NULL, subject TEXT NOT NULL, opening TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(vendor_key, method_key), FOREIGN KEY(vendor_key, method_key) REFERENCES vm_vendor_methods(vendor_key, method_key))")
            connection.execute("CREATE TABLE IF NOT EXISTS vm_phone_details (vendor_key TEXT NOT NULL, method_key TEXT NOT NULL CHECK(method_key = 'phone'), number TEXT NOT NULL, contact_name TEXT NOT NULL, account_id TEXT NOT NULL, extension TEXT NOT NULL, notes TEXT NOT NULL, PRIMARY KEY(vendor_key, method_key), FOREIGN KEY(vendor_key, method_key) REFERENCES vm_vendor_methods(vendor_key, method_key))")
            connection.execute("CREATE TABLE IF NOT EXISTS vm_portal_details (vendor_key TEXT NOT NULL, method_key TEXT NOT NULL CHECK(method_key = 'portal'), what_to_do TEXT NOT NULL, how_to_do TEXT NOT NULL, PRIMARY KEY(vendor_key, method_key), FOREIGN KEY(vendor_key, method_key) REFERENCES vm_vendor_methods(vendor_key, method_key))")
            connection.execute("CREATE TABLE IF NOT EXISTS vm_portal_sops (sop_id TEXT PRIMARY KEY REFERENCES vm_sops(id), vendor_key TEXT NOT NULL, method_key TEXT NOT NULL CHECK(method_key = 'portal'), FOREIGN KEY(vendor_key, method_key) REFERENCES vm_vendor_methods(vendor_key, method_key))")
    finally:
        connection.close()


def save(database, payload):
    vendor, methods, sop, request_id = validate(payload)
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
    connection = connect(database)
    try:
        with connection:
            # Serialize writers so an old retried submission cannot overwrite a newer save.
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT payload_hash FROM vm_submissions WHERE request_id = ?", (request_id,)).fetchone()
            if previous:
                if previous[0] != payload_hash:
                    raise ValueError("Request ID already used for different content; start a new submission.")
                return
            key = vendor.casefold()
            connection.execute("INSERT OR IGNORE INTO vm_vendors(vendor_key, name) VALUES (?, ?)", (key, vendor))
            for method_key, value in methods.items():
                connection.execute("INSERT OR IGNORE INTO vm_vendor_methods(vendor_key, method_key, label) VALUES (?, ?, ?)", (key, method_key, value["label"]))
                # Only Other saves replace steps; canonical methods retain historical notes.
                if "steps" in value:
                    connection.execute("DELETE FROM vm_method_steps WHERE vendor_key = ? AND method_key = ?", (key, method_key))
                    connection.executemany("INSERT INTO vm_method_steps(vendor_key, method_key, position, instruction) VALUES (?, ?, ?, ?)", [(key, method_key, n, text) for n, text in enumerate(value["steps"], 1)])
                if "email_details" in value:
                    email = value["email_details"]
                    connection.execute("INSERT INTO vm_email_details(vendor_key, method_key, address, subject, opening, body) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(vendor_key, method_key) DO UPDATE SET address=excluded.address, subject=excluded.subject, opening=excluded.opening, body=excluded.body", (key, method_key, email["address"], email["subject"], email["opening"], email["body"]))
                if "phone_details" in value:
                    phone = value["phone_details"]
                    # The three-field form must not erase older optional Phone values.
                    previous_phone = connection.execute("SELECT extension, notes FROM vm_phone_details WHERE vendor_key = ? AND method_key = ?", (key, method_key)).fetchone()
                    if previous_phone:
                        for index, field in enumerate(("extension", "notes")):
                            if field not in payload["phone_details"]:
                                phone[field] = previous_phone[index]
                    connection.execute("INSERT INTO vm_phone_details(vendor_key, method_key, number, contact_name, account_id, extension, notes) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(vendor_key, method_key) DO UPDATE SET number=excluded.number, contact_name=excluded.contact_name, account_id=excluded.account_id, extension=excluded.extension, notes=excluded.notes", (key, method_key, phone["number"], phone["contact_name"], phone["account_id"], phone["extension"], phone["notes"]))
                if "portal_details" in value:
                    portal = value["portal_details"]
                    connection.execute("INSERT INTO vm_portal_details(vendor_key, method_key, what_to_do, how_to_do) VALUES (?, ?, ?, ?) ON CONFLICT(vendor_key, method_key) DO UPDATE SET what_to_do=excluded.what_to_do, how_to_do=excluded.how_to_do", (key, method_key, portal["what_to_do"], portal["how_to_do"]))
            if sop:
                sop_id = uuid.uuid4().hex
                connection.execute("INSERT INTO vm_sops(id, vendor_key, name, mime, size, sha256, data) VALUES (?, ?, ?, ?, ?, ?, ?)", (sop_id, key, sop["name"], sop["mime"], sop["size"], sop["sha256"], sop["data"]))
                if "portal" in methods:
                    connection.execute("INSERT INTO vm_portal_sops(sop_id, vendor_key, method_key) VALUES (?, ?, 'portal')", (sop_id, key))
            connection.execute("INSERT INTO vm_submissions(request_id, payload_hash) VALUES (?, ?)", (request_id, payload_hash))
    finally:
        connection.close()


def load(database):
    connection = connect(database)
    try:
        # One read snapshot keeps directory methods, instructions and SOP metadata consistent.
        with connection:
            connection.execute("BEGIN")
            rows = connection.execute("SELECT v.vendor_key, v.name, m.method_key, m.label FROM vm_vendors v LEFT JOIN vm_vendor_methods m ON m.vendor_key = v.vendor_key ORDER BY v.vendor_key, m.method_key").fetchall()
            steps = connection.execute("SELECT vendor_key, method_key, instruction FROM vm_method_steps ORDER BY vendor_key, method_key, position").fetchall()
            sops = connection.execute("SELECT id, vendor_key, name, mime, size, sha256, created_at FROM vm_sops WHERE rowid IN (SELECT MAX(rowid) FROM vm_sops WHERE id NOT IN (SELECT sop_id FROM vm_portal_sops) GROUP BY vendor_key)").fetchall()
            emails = connection.execute("SELECT vendor_key, address, subject, opening, body FROM vm_email_details").fetchall()
            phones = connection.execute("SELECT vendor_key, number, contact_name, account_id, extension, notes FROM vm_phone_details").fetchall()
            portals = connection.execute("SELECT vendor_key, what_to_do, how_to_do FROM vm_portal_details").fetchall()
            portal_sops = connection.execute("SELECT s.id, s.vendor_key, s.name, s.mime, s.size, s.sha256, s.created_at FROM vm_sops s JOIN vm_portal_sops p ON p.sop_id = s.id AND p.vendor_key = s.vendor_key WHERE s.rowid IN (SELECT MAX(s2.rowid) FROM vm_sops s2 JOIN vm_portal_sops p2 ON p2.sop_id = s2.id AND p2.vendor_key = s2.vendor_key GROUP BY s2.vendor_key)").fetchall()
    finally:
        connection.close()
    vendors = {}
    for key, name, method_key, label in rows:
        value = vendors.setdefault(key, {"name": name, "methods": [], "steps": {}, "sop": None, "email_details": None, "phone_details": None, "portal_details": None, "portal_sop": None})
        if method_key is not None:
            value["methods"].append(label)
            value["steps"][label] = []
    labels = {(key, method_key): label for key, _, method_key, label in rows}
    for key, method_key, text in steps:
        vendors[key]["steps"][labels[(key, method_key)]].append(text)
    for identifier, key, name, mime, size, digest, created_at in sops:
        vendors[key]["sop"] = {"id": identifier, "name": name, "mime": mime, "size": size, "sha256": digest, "created_at": created_at}
    for key, address, subject, opening, body in emails:
        vendors[key]["email_details"] = {"address": address, "subject": subject, "opening": opening, "body": body}
    for key, number, contact_name, account_id, extension, notes in phones:
        vendors[key]["phone_details"] = {"number": number, "contact_name": contact_name, "account_id": account_id, "extension": extension, "notes": notes}
    for key, what_to_do, how_to_do in portals:
        vendors[key]["portal_details"] = {"what_to_do": what_to_do, "how_to_do": how_to_do}
    for identifier, key, name, mime, size, digest, created_at in portal_sops:
        vendors[key]["portal_sop"] = {"id": identifier, "name": name, "mime": mime, "size": size, "sha256": digest, "created_at": created_at}
    return list(vendors.values())


def load_sop(database, identifier):
    connection = connect(database)
    try:
        return connection.execute("SELECT name, mime, data FROM vm_sops WHERE id = ?", (identifier,)).fetchone()
    finally:
        connection.close()


def reject_constant(value):
    raise ValueError("Nonstandard JSON number.")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field.")
        result[key] = value
    return result


class VendorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, database, port=8081):
        self.database = Path(database)
        text = (HERE / "vendor_management.html").read_bytes().decode("utf-8")
        # Match browser HTML newline normalization before hashing and serving.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.page = text.encode("utf-8")
        hashes = {}
        for tag in ("script", "style"):
            hashes[tag] = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'" for s in re.findall(r"<" + tag + r">(.*?)</" + tag + r">", text, re.S))
        self.csp = "default-src 'none'; script-src " + hashes["script"] + "; style-src " + hashes["style"] + "; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
        super().__init__(("127.0.0.1", port), Handler)
        try:
            initialize(self.database)
        except Exception:
            self.server_close()
            raise


class Handler(BaseHTTPRequestHandler):
    server_version = "VendorManagement"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        pass

    def respond(self, status, content, content_type="application/json; charset=utf-8", download_name=None):
        if not isinstance(content, bytes):
            content = json.dumps(content, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        if download_name is not None:
            fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", download_name)
            self.send_header("Content-Disposition", 'attachment; filename="' + fallback + '"; filename*=UTF-8\'\'' + quote(download_name, safe=""))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", self.server.csp)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(content)

    def allowed(self, write=False):
        hosts = self.headers.get_all("Host", [])
        port = self.server.server_port
        if len(hosts) != 1 or hosts[0] not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            self.respond(403, {"error": "Invalid Host."})
            return False
        origins = self.headers.get_all("Origin", [])
        expected = "http://" + hosts[0]
        if len(origins) > 1 or (origins and origins[0] != expected) or (write and not origins):
            self.respond(403, {"error": "Same-origin requests only; writes require Origin."})
            return False
        if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            self.respond(403, {"error": "Cross-origin requests are not allowed."})
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        if self.path in ("/", "/vendor_management.html"):
            self.respond(200, self.server.page, "text/html; charset=utf-8")
        elif self.path == "/api/vendors":
            try:
                self.respond(200, {"vendors": load(self.server.database)})
            except sqlite3.Error:
                self.respond(503, {"error": "Storage unavailable. Retry shortly."})
        elif re.fullmatch(r"/api/sops/[0-9a-f]{32}", self.path):
            try:
                sop = load_sop(self.server.database, self.path.rsplit("/", 1)[1])
                if sop is None:
                    self.respond(404, {"error": "SOP not found."})
                else:
                    self.respond(200, sop[2], sop[1], download_name=sop[0])
            except sqlite3.Error:
                self.respond(503, {"error": "Storage unavailable. Retry shortly."})
        else:
            self.respond(404, {"error": "Not found."})

    def do_POST(self):
        if not self.allowed(write=True):
            return
        if self.path != "/api/vendors":
            self.respond(404, {"error": "Not found."})
            return
        types = self.headers.get_all("Content-Type", [])
        if len(types) != 1 or types[0].lower().replace(" ", "") not in ("application/json", "application/json;charset=utf-8"):
            self.respond(415, {"error": "Send application/json in UTF-8."})
            return
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get_all("Transfer-Encoding") or len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
            self.respond(400, {"error": "A single valid Content-Length is required."})
            return
        length = int(lengths[0])
        if not 0 < length <= MAX_BODY:
            self.respond(413, {"error": "Request must be 1 byte to 14 MiB; SOP maximum is 10 MiB."})
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete request body.")
            payload = json.loads(raw.decode("utf-8"), parse_constant=reject_constant, object_pairs_hook=unique_object)
            save(self.server.database, payload)
        except (UnicodeError, RecursionError):
            self.respond(400, {"error": "Invalid UTF-8 or excessively nested JSON."})
            return
        except ValueError as error:
            self.respond(400, {"error": str(error)})
            return
        except TimeoutError:
            self.respond(408, {"error": "Request timed out."})
            return
        except sqlite3.Error:
            self.respond(503, {"error": "Storage unavailable. Retry safely; saves are idempotent."})
            return
        self.respond(200, {"message": SAVE_MESSAGE})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="Optional dedicated database path; default: project data/vendor_management.db")
    args = parser.parse_args()
    with VendorServer(args.database) as server:
        print("Vendor Management: http://127.0.0.1:8081/vendor_management.html", flush=True)
        print("Database: " + str(args.database.resolve()), flush=True)
        print("Local single-user only; Ctrl+C stops the server.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
