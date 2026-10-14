"""Run from project root: python -B frontend/vendor_management_test.py"""
import base64
import concurrent.futures
from contextlib import closing
import io
import re
import shutil
import subprocess
import zipfile
import http.client
from html.parser import HTMLParser
import json
from pathlib import Path
import socket
import sqlite3
import threading
import unittest
from unittest.mock import patch
import uuid

import vendor_management_server as vm


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.inputs = []
        self.external = []
        self.events = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "input":
            self.inputs.append(attrs)
        for key, value in attrs.items():
            if key.startswith("on"):
                self.events.append(key)
            if key in ("src", "href") and value and not value.startswith("#"):
                self.external.append(value)


def payload(vendor="Dell", methods=None, steps=None, **extra):
    methods = methods or ["Phone"]
    value = {"vendor": vendor, "methods": methods,
             "steps": steps if steps is not None else {m: ["Open support", "Provide ticket details"] for m in methods if m == "Other"},
             "request_id": uuid.uuid4().hex}
    if "Other" in methods:
        value["custom_method"] = "Partner help desk"
    if "Email" in methods:
        value["email_details"] = {"address": "support@vendor.example", "subject": "Support request: [ticket]",
                                  "opening": "Hello support,\n", "body": "Issue:\n\tDescribe the problem"}
    if "Phone" in methods:
        value["phone_details"] = {"number": "+44 (0)20 1234-5678", "contact_name": "Support team", "account_id": "000123", "extension": "007", "notes": "Available weekdays\nAsk for support"}
    if "Portal" in methods:
        value["portal_details"] = {"what_to_do": "Open a support case", "how_to_do": "Sign in\n\tSelect New case"}
        value["sop"] = attachment("portal.txt", b"Open portal and follow procedure.")
    value.update(extra)
    return value


def attachment(name="procedure.txt", data=b"Step 1: contact support."):
    return {"name": name, "data": base64.b64encode(data).decode()}


def docx(extra=None, document=None):
    files = {
        "[Content_Types].xml": b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": document or b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Contact support.</w:t></w:r></w:p></w:body></w:document>'}
    files.update(extra or {})
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out.getvalue()


def pdf():
    result = b"%PDF-1.4\n"
    bodies = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [] /Count 0 >>"]
    offsets = []
    for index, body in enumerate(bodies, 1):
        offsets.append(len(result))
        result += str(index).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref = len(result)
    result += b"xref\n0 3\n0000000000 65535 f \n"
    for offset in offsets:
        result += f"{offset:010} 00000 n \n".encode()
    result += b"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF\n"
    return result


class VendorManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = Path(__file__).resolve().with_name(".vendor_management_test_" + uuid.uuid4().hex + ".db")
        cls.start_server()

    @classmethod
    def start_server(cls):
        cls.server = vm.VendorServer(cls.database, port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port
        cls.origin = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def stop_server(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    @classmethod
    def tearDownClass(cls):
        cls.stop_server()
        for suffix in ("", "-journal", "-wal", "-shm"):
            cls.database.with_name(cls.database.name + suffix).unlink(missing_ok=True)

    def setUp(self):
        connection = vm.connect(self.database)
        try:
            with connection:
                connection.execute("DROP TRIGGER IF EXISTS vm_test_fail")
                for table in ("vm_submissions", "vm_portal_sops", "vm_portal_details", "vm_phone_details", "vm_sops", "vm_email_details", "vm_method_steps", "vm_vendor_methods", "vm_vendors"):
                    connection.execute("DELETE FROM " + table)
        finally:
            connection.close()

    def request(self, method="GET", path="/api/vendors", payload=None, body=None, headers=None):
        headers = dict(headers or {})
        if method == "POST":
            headers.setdefault("Origin", self.origin)
            headers.setdefault("Content-Type", "application/json")
            if body is None:
                body = json.dumps(payload).encode()
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def assert_bad(self, value):
        result = self.request("POST", payload=value)
        self.assertEqual(result[0], 400, result[2])
        self.assertEqual(vm.load(self.database), [])

    def test_page_and_csp(self):
        for path in ("/", "/vendor_management.html"):
            status, headers, body = self.request(path=path)
            self.assertEqual(status, 200)
            self.assertEqual(body, self.server.page)
            self.assertIn("sha256-", headers["Content-Security-Policy"])
            self.assertNotIn("unsafe-inline", headers["Content-Security-Policy"])
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(headers["Cache-Control"], "no-store")
            for tag in ("style", "script"):
                for block in re.findall(r"<" + tag + r">(.*?)</" + tag + r">", body.decode(), re.S):
                    digest = base64.b64encode(vm.hashlib.sha256(block.encode()).digest()).decode()
                    self.assertIn("sha256-" + digest, headers["Content-Security-Policy"])

    def assert_page_line_endings(self, line_ending):
        original = (vm.HERE / "vendor_management.html").read_bytes()
        normalized = original.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        source = normalized.replace("\n", line_ending).encode("utf-8")
        with patch.object(Path, "read_bytes", return_value=source):
            server = vm.VendorServer(self.database, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for path in ("/", "/vendor_management.html"):
                with self.subTest(path=path):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=30)
                    try:
                        connection.request("GET", path)
                        response = connection.getresponse()
                        body = response.read()
                        csp = response.getheader("Content-Security-Policy")
                        self.assertEqual(response.status, 200)
                        self.assertEqual(body, normalized.encode("utf-8"))
                        self.assertEqual(int(response.getheader("Content-Length")), len(body))
                        self.assertNotIn("unsafe-inline", csp)
                        directives = dict(part.strip().split(" ", 1) for part in csp.split(";"))
                        for tag in ("style", "script"):
                            blocks = re.findall(r"<" + tag + r">(.*?)</" + tag + r">", normalized, re.S)
                            self.assertTrue(blocks)
                            expected = {"'sha256-" + base64.b64encode(vm.hashlib.sha256(block.encode("utf-8")).digest()).decode() + "'" for block in blocks}
                            self.assertEqual(set(directives[tag + "-src"].split()), expected)
                    finally:
                        connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual((vm.HERE / "vendor_management.html").read_bytes(), original)

    def test_page_csp_lf(self):
        self.assert_page_line_endings("\n")

    def test_page_csp_crlf(self):
        self.assert_page_line_endings("\r\n")

    def test_page_csp_lone_cr(self):
        self.assert_page_line_endings("\r")

    def test_no_arbitrary_files(self):
        for path in ("/vendor_management_server.py", "/../data/itom.db", "/data/vendor_management.db", "/%2e%2e/index.html", "/index.html", "/.env", "/api/sops/../../.env", "/api/sops/%2e%2e", "/api/sops/" + "f" * 32):
            self.assertEqual(self.request(path=path)[0], 404)

    def test_free_name_all_methods_ordered_steps(self):
        value = payload("  New   Vendor  ", list(vm.METHODS))
        value["steps"]["Other"] = ["Step three first", "Step one next", "Step two last"]
        self.assertEqual(self.request("POST", payload=value)[0], 200)
        saved = vm.load(self.database)[0]
        self.assertEqual(saved["name"], "New Vendor")
        self.assertEqual(saved["methods"], ["Email", "Partner help desk", "Phone", "Portal"])
        self.assertEqual(saved["steps"]["Partner help desk"], value["steps"]["Other"])
        self.assertIsNone(saved["sop"])
        self.assertEqual(saved["portal_sop"]["name"], "portal.txt")
        self.assertEqual(saved["phone_details"], value["phone_details"])

    def test_normalized_additive_update_and_stale_retry(self):
        first = payload("Microsoft", ["Phone", "Email"])
        vm.save(self.database, first)
        newer = payload("  MICROSOFT ", ["Phone"], phone_details={"number": "+1 234 567 8900", "contact_name": "New contact", "account_id": "000987"})
        vm.save(self.database, newer)
        vm.save(self.database, first)
        saved = vm.load(self.database)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["name"], "Microsoft")
        self.assertEqual(saved[0]["methods"], ["Email", "Phone"])
        self.assertEqual(saved[0]["phone_details"], {**first["phone_details"], **newer["phone_details"]})
        self.assertEqual(saved[0]["steps"]["Email"], [])

    def test_custom_casefold(self):
        for name in ("Straße", " STRASSE "):
            vm.save(self.database, payload(name))
        self.assertEqual(len(vm.load(self.database)), 1)

    def test_alias_collision_rejected(self):
        self.assert_bad(payload(methods=["Phone", "Other"], custom_method="Ｐｈｏｎｅ"))

    def test_validation_no_partial_records(self):
        invalid = [None, [], {}, payload(vendor=None), payload(methods=[None]), payload(methods=["Phone", "Phone"]), payload(unexpected=True), payload(custom_vendor="obsolete"), payload(custom_method="unused"), payload(request_id="wrong")]
        value = payload(); value["methods"] = []; invalid.append(value)
        for value in invalid:
            with self.subTest(value=value):
                self.assert_bad(value)

    def test_step_validation(self):
        for steps in ({}, {"Other": []}, {"Other": [""]}, {"Other": ["  "]}, {"Other": [None]}, {"Other": ["a"] * 31}, {"Other": ["a" * 2001]}, {"Other": ["x\u202e"]}, {"Other": ["a"], "Email": ["unselected"]}):
            with self.subTest(steps=steps):
                value = payload(methods=["Other"]); value["steps"] = steps
                self.assert_bad(value)
        self.assertEqual(self.request("POST", payload=payload(methods=["Other"], steps={"Other": ["a" * 2000] * 30}))[0], 200)

    def test_other_requires_custom_name_and_steps(self):
        for custom in ("", "  ", "a" * 81):
            self.assert_bad(payload(methods=["Other"], custom_method=custom))
        value = payload(methods=["Other"]); value["steps"] = {"Other": []}
        self.assert_bad(value)

    def test_custom_text_limits_controls(self):
        for text in (" ", "a" * 101, "a\n", "x\x00", "x\u202e", "x\ud800"):
            self.assert_bad(payload(vendor=text))
        for text in (" ", "a" * 81, "x\t", "x\u200b"):
            self.assert_bad(payload(methods=["Other"], custom_method=text))
        self.assertEqual(self.request("POST", payload=payload("a" * 100, ["Other"], custom_method="b" * 80))[0], 200)

    def test_atomic_rollback_steps_sop_submission(self):
        before = payload(methods=["Phone", "Email"], sop=attachment()); vm.save(self.database, before)
        snapshot = vm.load(self.database)
        connection = vm.connect(self.database)
        try:
            connection.execute("CREATE TRIGGER vm_test_fail BEFORE INSERT ON vm_submissions BEGIN SELECT RAISE(ABORT, 'test failure'); END")
            connection.commit()
        finally:
            connection.close()
        new = payload(methods=["Phone", "Portal", "Email"], steps={}, email_details={"address": "new@vendor.example", "subject": "Changed"}, sop=attachment("new.txt"))
        self.assertEqual(self.request("POST", payload=new)[0], 503)
        self.assertEqual(vm.load(self.database), snapshot)
        connection = vm.connect(self.database)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM vm_sops").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM vm_submissions").fetchone()[0], 1)
        finally:
            connection.close()

    def test_parameterized_untrusted_text(self):
        name = "<img src=x>'); DROP TABLE vm_vendors;--"
        text = "<script>alert('x')</script>"
        vm.save(self.database, payload(name, methods=["Other"], steps={"Other": [text]}))
        self.assertEqual(vm.load(self.database)[0]["name"], name)
        self.assertEqual(vm.load(self.database)[0]["steps"]["Partner help desk"], [text])

    def test_host_and_origin(self):
        for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}, {"Origin": self.origin, "Host": f"localhost:{self.port}"}):
            self.assertEqual(self.request("POST", payload=payload(), headers=headers)[0], 403)
        self.assertEqual(self.request(headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request(headers={"Host": f"localhost:{self.port}"})[0], 200)
        self.assertEqual(vm.load(self.database), [])

    def test_missing_origin(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("POST", "/api/vendors", body=b"{}", headers={"Content-Type": "application/json"})
            self.assertEqual(connection.getresponse().status, 403)
        finally:
            connection.close()

    def test_json_size_and_type(self):
        for body in (b"not json", b"{", b"\xff", b'{"vendor":"HP","vendor":"Dell"}', b'{"vendor":NaN}', b"[" * 2000):
            self.assertEqual(self.request("POST", body=body)[0], 400)
        self.assertEqual(self.request("POST", body=b"", headers={"Content-Length": str(vm.MAX_BODY + 1)})[0], 413)
        self.assertEqual(self.request("POST", body=b"")[0], 413)
        self.assertEqual(self.request("POST", body=b"{}", headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", body=b"{}", headers={"Transfer-Encoding": "chunked"})[0], 400)

    def test_duplicate_security_headers(self):
        for header in ("Host", "Origin", "Content-Length", "Content-Type"):
            values = {"Host": f"127.0.0.1:{self.port}", "Origin": self.origin, "Content-Length": "2", "Content-Type": "application/json"}
            lines = ["POST /api/vendors HTTP/1.1"] + [k + ": " + v for k, v in values.items()] + [header + ": " + values[header], "Connection: close", "", "{}"]
            with socket.create_connection(("127.0.0.1", self.port), timeout=5) as connection:
                connection.sendall("\r\n".join(lines).encode())
                code = connection.recv(4096).split(b"\r\n")[0]
                self.assertNotIn(b"200", code)

    def test_concurrent_repeats_one_blob(self):
        value = payload("Cisco", ["Phone", "Email"], sop=attachment())
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            self.assertEqual(list(pool.map(lambda _: self.request("POST", payload=value)[0], range(10))), [200] * 10)
        connection = vm.connect(self.database)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM vm_sops").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM vm_submissions").fetchone()[0], 1)
        finally:
            connection.close()

    def test_id_reuse_different_content_rejected(self):
        value = payload(); vm.save(self.database, value)
        value["phone_details"]["account_id"] = "Different"
        self.assertEqual(self.request("POST", payload=value)[0], 400)
        self.assertNotEqual(vm.load(self.database)[0]["phone_details"]["account_id"], "Different")

    def test_persists_server_restart(self):
        value = payload("Restart Vendor", list(vm.METHODS), sop=attachment("restart.txt"))
        vm.save(self.database, value)
        snapshot = vm.load(self.database)
        self.stop_server(); self.start_server()
        self.assertEqual(json.loads(self.request()[2])["vendors"], snapshot)
        identifier = snapshot[0]["portal_sop"]["id"]
        self.assertEqual(self.request(path="/api/sops/" + identifier)[2], base64.b64decode(value["sop"]["data"]))

    def test_legacy_migration_preserves_rows_and_file(self):
        database = self.database.with_name(".legacy_" + uuid.uuid4().hex + ".db")
        try:
            connection = sqlite3.connect(database)
            connection.executescript("CREATE TABLE vm_vendors (vendor_key TEXT PRIMARY KEY, name TEXT NOT NULL); CREATE TABLE vm_vendor_methods (vendor_key TEXT NOT NULL REFERENCES vm_vendors(vendor_key), method_key TEXT NOT NULL, label TEXT NOT NULL, PRIMARY KEY(vendor_key, method_key)); INSERT INTO vm_vendors VALUES ('dell','Dell'); INSERT INTO vm_vendor_methods VALUES ('dell','email','Email'); CREATE TABLE unrelated (value TEXT); INSERT INTO unrelated VALUES ('untouched');")
            connection.commit(); connection.close()
            vm.initialize(database); vm.initialize(database)
            self.assertEqual(vm.load(database)[0]["steps"], {"Email": []})
            self.assertIsNone(vm.load(database)[0]["email_details"])
            vm.save(database, payload("DELL", ["Phone"], sop=attachment()))
            saved = vm.load(database)[0]
            self.assertEqual(saved["methods"], ["Email", "Phone"])
            self.assertEqual(saved["name"], "Dell")
            self.assertIsNone(saved["email_details"])
            connection = sqlite3.connect(database)
            self.assertEqual(connection.execute("SELECT value FROM unrelated").fetchone()[0], "untouched")
            connection.close()
        finally:
            database.unlink(missing_ok=True)

    def test_attachment_download_metadata(self):
        data = b"First step\nSecond step"
        self.assertEqual(self.request("POST", payload=payload(sop=attachment("procédure.txt", data)))[0], 200)
        sop = vm.load(self.database)[0]["sop"]
        self.assertNotIn("data", sop)
        self.assertEqual(sop["size"], len(data))
        self.assertEqual(sop["sha256"], vm.hashlib.sha256(data).hexdigest())
        code, headers, body = self.request(path="/api/sops/" + sop["id"])
        self.assertEqual((code, body), (200, data))
        self.assertTrue(headers["Content-Disposition"].startswith("attachment;"))
        self.assertIn("filename*=UTF-8''proc%C3%A9dure.txt", headers["Content-Disposition"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.request(path="/api/sops/" + sop["id"], headers={"Origin": "https://evil.example"})[0], 403)

    def test_no_attachment_keeps_sop_and_new_sop_retains_old(self):
        vm.save(self.database, payload(sop=attachment("first.txt", b"First")))
        first = vm.load(self.database)[0]["sop"]
        vm.save(self.database, payload(methods=["Email"], sop=None))
        self.assertEqual(vm.load(self.database)[0]["sop"], first)
        vm.save(self.database, payload(sop=attachment("second.txt", b"Second")))
        self.assertEqual(vm.load(self.database)[0]["sop"]["name"], "second.txt")
        self.assertEqual(self.request(path="/api/sops/" + first["id"])[2], b"First")

    def test_three_allowed_formats(self):
        for name, data in (("safe.txt", b"Instructions"), ("safe.pdf", pdf()), ("safe.docx", docx())):
            with self.subTest(name=name):
                self.assertEqual(self.request("POST", payload=payload(vendor=name, sop=attachment(name, data)))[0], 200)

    def test_invalid_extension_or_filename(self):
        for name in ("a.html", "a.js", "a.exe", "a.docm", "a.doc", "../a.txt", "a/b.txt", "a\\b.txt", "C:a.txt", "a.txt\r\nX: yes", ".txt", "a\u202e.txt", "a" * 151 + ".txt"):
            self.assert_bad(payload(sop=attachment(name)))

    def test_invalid_sop_schema_base64_empty(self):
        for sop in ({}, [], "file", {"name": "a.txt", "data": "%%%"}, {"name": "a.txt", "data": "x"}, {"name": "a.txt", "data": "é"}, attachment(data=b""), {**attachment(), "path": "/etc/passwd"}):
            self.assert_bad(payload(sop=sop))

    def test_ten_mib_boundary(self):
        data = b"a" * vm.MAX_FILE
        result = self.request("POST", payload=payload(sop=attachment(data=data)))
        self.assertEqual(result[0], 200, result[2])
        identifier = vm.load(self.database)[0]["sop"]["id"]
        self.assertEqual(len(self.request(path="/api/sops/" + identifier)[2]), vm.MAX_FILE)
        value = payload(sop=attachment(data=data + b"x"))
        self.assertEqual(self.request("POST", payload=value)[0], 400)

    def test_txt_rejects_binary_and_markup(self):
        for data in (b"<html><script>alert(1)</script></html>", b"#!/bin/sh\nexit", b"MZbinary", b"PK\x03\x04zip", b"a\x00b", b"\xff", b"<svg onload='x'>"):
            self.assert_bad(payload(sop=attachment(data=data)))

    def test_pdf_rejects_active_and_spoofed(self):
        invalid = [b"not a pdf", b"%PDF-1.7\n%%EOF", b"<html>fake</html>", pdf().replace(b"%%EOF", b"%%EOF garbage")]
        for action in (b"/JavaScript", b"/J#61vaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/ObjStm", b"/Encrypt", b"/OpenAction"):
            invalid.append(pdf().replace(b"/Catalog", b"/Catalog " + action))
        for data in invalid:
            self.assert_bad(payload(sop=attachment("bad.pdf", data)))

    def test_docx_rejects_macro_embedding_and_path(self):
        for name in ("word/vbaProject.bin", "word/embeddings/object.bin", "word/activeX/a.xml", "../outside.xml", "word/script.js", "word/vector.svg"):
            self.assert_bad(payload(sop=attachment("bad.docx", docx({name: b"bad"}))))

    def test_docx_rejects_fake_and_xml_entities(self):
        for data in (b"PKnotzip", docx(document=b"<notword/>"), docx(document=b'<!DOCTYPE a [<!ENTITY x "boom">]><a>&x;</a>'), docx(document='<document/>'.encode('utf-16')), docx({"[Content_Types].xml": b"<Types/>"})):
            self.assert_bad(payload(sop=attachment("bad.docx", data)))

    def test_docx_rejects_external_relationship_and_fields(self):
        rel = b'<Relationships><Relationship TargetMode="External" Target="https://evil.example/a"/></Relationships>'
        self.assert_bad(payload(sop=attachment("bad.docx", docx({"word/_rels/document.xml.rels": rel}))))
        document = b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:instrText>DDEAUTO</w:instrText></w:document>'
        self.assert_bad(payload(sop=attachment("bad.docx", docx(document=document))))

    def test_docx_rejects_bombs_and_excessive_entries(self):
        self.assert_bad(payload(sop=attachment("bad.docx", docx({"word/bomb.xml": b"a" * (1024 * 1024)}))))
        extras = {f"word/a{i}.xml": b"<a/>" for i in range(254)}
        self.assert_bad(payload(sop=attachment("bad.docx", docx(extras))))
        with self.assertWarns(UserWarning):
            stream = io.BytesIO(docx())
            with zipfile.ZipFile(stream, "a") as archive:
                archive.writestr("word/document.xml", b"<x/>")
        self.assert_bad(payload(sop=attachment("bad.docx", stream.getvalue())))

    def test_email_save_get_normalization_and_multiline(self):
        details = {"address": " Support+tag@VENDOR.Example ", "subject": "  Case   [number] ",
                   "opening": "Hello team,\r\n\tSupport please", "body": "<script>alert(1)</script>\n\nDetails\tgo here"}
        value = payload(methods=["Email"], email_details=details)
        self.assertEqual(self.request("POST", payload=value)[0], 200)
        expected = {**details, "address": "Support+tag@vendor.example", "subject": "Case [number]",
                    "opening": "Hello team,\n\tSupport please"}
        self.assertEqual(json.loads(self.request()[2])["vendors"][0]["email_details"], expected)
        self.assertEqual(vm.load(self.database)[0]["steps"]["Email"], [])

    def test_email_required_details(self):
        value = payload(methods=["Email"]); del value["email_details"]
        self.assert_bad(value)
        for details in (None, [], {}, {"address": "support@vendor.example"}, {"subject": "Help"},
                        {"address": "", "subject": "Help"}, {"address": "a@b.example", "subject": ""}):
            self.assert_bad(payload(methods=["Email"], email_details=details))

    def test_email_invalid_recipient(self):
        invalid = [None, 4, "not-an-email", "a@@b.example", "a@localhost", "Name <a@b.example>",
                   "a@b.example,c@d.example", "a@b.example; c@d.example", "a@b.example\r\nBcc: victim@x.example",
                   "a@b.example\n", "a\tb@b.example", "a..b@vendor.example", ".a@vendor.example",
                   "a@-vendor.example", "a@vendor-.example", "a@vendor..example", "a@vendor.123",
                   "a@" + "b" * 64 + ".example", "a" * 65 + "@b.example", "a@b.example\u202e",
                   "ü@vendor.example", "a@" + ".".join(["b" * 60] * 5)]
        for address in invalid:
            with self.subTest(address=address):
                self.assert_bad(payload(methods=["Email"], email_details={"address": address, "subject": "Help"}))

    def test_email_subject_validation_and_limits(self):
        for subject in (None, [], " ", "a" * 201, "Help\r\nBcc: x@y.example", "Help\n", "Help\t", "Help\x00", "Help\u200b"):
            self.assert_bad(payload(methods=["Email"], email_details={"address": "a@b.example", "subject": subject}))
        self.assertEqual(self.request("POST", payload=payload(methods=["Email"], email_details={"address": "a@b.example", "subject": "a" * 200}))[0], 200)

    def test_email_multiline_validation_and_limits(self):
        for key, limit in (("opening", 2000), ("body", 10000)):
            for text in (None, {}, "x" * (limit + 1), "x\x00", "x\x0b", "x\u202e", "x\ud800"):
                self.assert_bad(payload(methods=["Email"], email_details={"address": "a@b.example", "subject": "Help", key: text}))
        details = {"address": "a@b.example", "subject": "Help", "opening": "x" * 2000, "body": "x" * 10000}
        self.assertEqual(self.request("POST", payload=payload(methods=["Email"], email_details=details))[0], 200)

    def test_email_schema_spoof_and_unselected_rejected(self):
        for key in ("cc", "bcc", "headers", "smtp", "send", "sop", "method_key"):
            self.assert_bad(payload(methods=["Email"], email_details={"address": "a@b.example", "subject": "Help", key: "unexpected"}))
        for details in (None, {}, {"address": "a@b.example", "subject": "Help"}):
            self.assert_bad(payload(email_details=details))

    def test_email_alias_requires_checkbox(self):
        for alias in ("Email", " email ", "EMAIL", "Ｅｍａｉｌ"):
            self.assert_bad(payload(methods=["Other"], custom_method=alias))
            self.assert_bad(payload(methods=["Email", "Other"], custom_method=alias))

    def test_email_replacement_preservation_and_stale_retry(self):
        first = payload(methods=["Phone", "Email"], sop=attachment())
        vm.save(self.database, first)
        before = vm.load(self.database)[0]
        vm.save(self.database, payload(methods=["Portal"]))
        self.assertEqual(vm.load(self.database)[0]["email_details"], before["email_details"])
        replacement = payload(methods=["Email"], email_details={"address": "next@vendor.example", "subject": "New case"})
        vm.save(self.database, replacement); vm.save(self.database, first)
        saved = vm.load(self.database)[0]
        self.assertEqual(saved["email_details"], {**replacement["email_details"], "opening": "", "body": ""})
        self.assertEqual(saved["steps"]["Phone"], before["steps"]["Phone"])
        self.assertEqual(saved["sop"], before["sop"])
        replacement["email_details"]["subject"] = "Changed"
        self.assertEqual(self.request("POST", payload=replacement)[0], 400)
        self.assertEqual(vm.load(self.database)[0], saved)

    def test_email_additive_migration_preserves_existing_steps_and_sop(self):
        database = self.database.with_name(".migration_" + uuid.uuid4().hex + ".db")
        try:
            vm.initialize(database)
            value = payload(methods=["Phone", "Email"], sop=attachment())
            vm.save(database, value)
            with closing(vm.connect(database)) as connection, connection:
                connection.execute("INSERT INTO vm_method_steps VALUES (?, ?, ?, ?)", ("dell", "email", 1, "Prior email instruction"))
            snapshot = vm.load(database)
            with closing(vm.connect(database)) as connection, connection:
                connection.execute("DROP TABLE vm_email_details")
            snapshot[0]["email_details"] = None
            vm.initialize(database); vm.initialize(database)
            self.assertEqual(vm.load(database), snapshot)
            self.assertEqual(vm.load_sop(database, snapshot[0]["sop"]["id"])[2], base64.b64decode(value["sop"]["data"]))
            with closing(vm.connect(database)) as connection, connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM vm_submissions").fetchone()[0], 1)
        finally:
            database.unlink(missing_ok=True)

    def test_email_only_explicit_empty_steps_contract(self):
        value = payload(methods=["Email"], steps={})
        self.assertEqual(self.request("POST", payload=value)[0], 200)
        saved = vm.load(self.database)[0]
        self.assertEqual(saved["methods"], ["Email"])
        self.assertEqual(saved["steps"], {"Email": []})
        self.assertEqual(saved["email_details"], value["email_details"])

    def test_email_steps_missing_or_extraneous_rejected(self):
        value = payload(methods=["Email"]); del value["steps"]
        self.assert_bad(value)
        for steps in (None, [], {"Email": []}, {"Email": ["Old client instruction"]}, {"Phone": ["Unselected"]}):
            self.assert_bad(payload(methods=["Email"], steps=steps) if steps is not None else {**payload(methods=["Email"]), "steps": None})

    def test_mixed_email_phone_requires_details_not_steps(self):
        for steps in ({"Phone": []}, {"Phone": [" "]}, {"Phone": ["Call"], "Email": []}):
            self.assert_bad(payload(methods=["Email", "Phone"], steps=steps))
        for details in (None, {}, {"number": "123"}):
            self.assert_bad(payload(methods=["Email", "Phone"], phone_details=details))
        value = payload(methods=["Email", "Phone"], steps={})
        self.assertEqual(self.request("POST", payload=value)[0], 200)
        self.assertEqual(vm.load(self.database)[0]["steps"], {"Email": [], "Phone": []})

    def test_email_detail_saves_preserve_legacy_notes_sop_and_receipts(self):
        first = payload(methods=["Email", "Phone"], sop=attachment("original.txt", b"Keep this SOP"))
        vm.save(self.database, first)
        with closing(vm.connect(self.database)) as connection, connection:
            connection.executemany("INSERT INTO vm_method_steps VALUES (?, ?, ?, ?)",
                                   [("dell", "email", 1, "Prior first note"), ("dell", "email", 2, "Prior second note")])
            old_payload = {**first, "steps": {**first["steps"], "Email": ["Prior first note", "Prior second note"]}, "request_id": uuid.uuid4().hex}
            old_hash = vm.hashlib.sha256(json.dumps(old_payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
            connection.execute("INSERT INTO vm_submissions VALUES (?, ?)", (old_payload["request_id"], old_hash))
            receipts = connection.execute("SELECT * FROM vm_submissions").fetchall()
        before = vm.load(self.database)[0]
        for methods in (["Email"], ["Email", "Phone"], ["Portal"]):
            value = payload(methods=methods)
            if "Email" in methods:
                value["email_details"] = {"address": "updated@vendor.example", "subject": "Updated"}
            self.assertEqual(self.request("POST", payload=value)[0], 200)
            saved = vm.load(self.database)[0]
            self.assertEqual(saved["steps"]["Email"], before["steps"]["Email"])
            self.assertEqual(saved["sop"], before["sop"])
        snapshot = vm.load(self.database)
        self.stop_server(); self.start_server()
        self.assertEqual(json.loads(self.request()[2])["vendors"], snapshot)
        self.assertEqual(self.request(path="/api/sops/" + before["sop"]["id"])[2], b"Keep this SOP")
        with closing(vm.connect(self.database)) as connection:
            self.assertTrue(set(receipts) <= set(connection.execute("SELECT * FROM vm_submissions").fetchall()))

    def test_email_only_sop_and_exact_retry_persist(self):
        value = payload(methods=["Email"], steps={}, sop=attachment("email.txt", b"Email procedure"))
        self.assertEqual(self.request("POST", payload=value)[0], 200)
        snapshot = vm.load(self.database)
        self.stop_server(); self.start_server()
        self.assertEqual(self.request("POST", payload=value)[0], 200)
        self.assertEqual(vm.load(self.database), snapshot)
        self.assertEqual(self.request(path="/api/sops/" + snapshot[0]["sop"]["id"])[2], b"Email procedure")
        with closing(vm.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM vm_sops").fetchone()[0], 1)

    def test_all_method_combinations_new_contract(self):
        for mask in range(1, 16):
            methods = [m for i, m in enumerate(vm.METHODS) if mask & (1 << i)]
            with self.subTest(methods=methods):
                value = payload("Combination " + str(mask), methods)
                code, _, body = self.request("POST", payload=value)
                self.assertEqual(code, 200, body)
                saved = next(v for v in vm.load(self.database) if v["name"] == value["vendor"])
                self.assertEqual(saved["phone_details"], value.get("phone_details"))
                self.assertEqual(saved["email_details"], value.get("email_details"))
                self.assertEqual(saved["portal_sop"] is not None, "Portal" in methods)
                self.assertEqual(saved["portal_details"], value.get("portal_details"))
                for m in methods:
                    if m != "Other":
                        self.assertEqual(saved["steps"][m], [])

    def test_portal_missing_sop_rejected_all_mixed_states(self):
        for mask in range(1, 16):
            methods = [m for i, m in enumerate(vm.METHODS) if mask & (1 << i)]
            if "Portal" not in methods:
                continue
            for missing in (True, False):
                value = payload(methods=methods, sop=None)
                if missing:
                    del value["sop"]
                self.assert_bad(value)
        for sop in ({}, "existing", {"id": "a" * 32}, attachment(data=b"")):
            self.assert_bad(payload(methods=["Portal"], sop=sop))

    def test_only_other_steps_allowed(self):
        for method in ("Phone", "Portal", "Email"):
            for steps in ({method: []}, {method: ["Old instruction"]}, {"Other": ["Unselected"]}, None, []):
                value = payload(methods=[method]); value["steps"] = steps
                self.assert_bad(value)
            value = payload(methods=[method]); del value["steps"]
            self.assert_bad(value)

    def test_phone_required_fields_and_nested_schema(self):
        value = payload(); del value["phone_details"]
        self.assert_bad(value)
        for details in (None, [], {}, "contact", {"number": "123"}):
            self.assert_bad(payload(phone_details=details))
        for key in ("number", "account_id"):
            details = payload()["phone_details"]; del details[key]
            self.assert_bad(payload(phone_details=details))
        for key in ("steps", "call", "method_key", "sop", "email", "url"):
            details = {**payload()["phone_details"], key: "unexpected"}
            self.assert_bad(payload(phone_details=details))
        for methods in (["Email"], ["Portal"], ["Other"]):
            for details in (None, {}, payload()["phone_details"]):
                self.assert_bad(payload(methods=methods, phone_details=details))

    def test_phone_number_validation(self):
        invalid = (None, 1234567, [], "", " ", "12", "1" * 21, "+1 CALL-NOW", "123#4", "123;456", "123\n", "123\t", "12\u200b3", "++123", "12+34", "123 ext 7", "1" + " " * 39 + "23" + "-" * 40)
        for number in invalid:
            with self.subTest(number=number):
                self.assert_bad(payload(phone_details={**payload()["phone_details"], "number": number}))
        for i, number in enumerate(("123", "+44 (0)20 1234-5678", "(212) 555.0100", "001 234 567 890", "1" * 20)):
            value = payload(str(i), phone_details={**payload()["phone_details"], "number": number})
            self.assertEqual(self.request("POST", payload=value)[0], 200)

    def test_phone_name_account_extension_notes_limits(self):
        for key in ("contact_name", "account_id"):
            invalid = (None, 42, [], {}, True, "---", "x" * 101, "x\n", "\t", "\n", "x\u200b", "x\u202e", "x\x00", "x\ud800")
            if key == "account_id":
                invalid += ("", " ")
            for text in invalid:
                self.assert_bad(payload(phone_details={**payload()["phone_details"], key: text}))
        for extension in (None, 12, " ", "1" * 11, "+12", "12x", "12\n", "1\u200b2"):
            self.assert_bad(payload(phone_details={**payload()["phone_details"], "extension": extension}))
        for notes in (None, [], "x" * 2001, "x\x00", "x\u202e", "x\ud800"):
            self.assert_bad(payload(phone_details={**payload()["phone_details"], "notes": notes}))
        details = {"number": "+1 234 567 8900", "contact_name": "x" * 100, "account_id": "0" * 100, "extension": "0" * 10, "notes": "x" * 2000}
        self.assertEqual(self.request("POST", payload=payload(phone_details=details))[0], 200)

    def test_phone_blank_or_missing_contact_saves_and_reloads(self):
        for index, contact in enumerate(({}, {"contact_name": ""}, {"contact_name": "   "}, {"contact_name": "\u3000"})):
            with self.subTest(contact=contact):
                details = {"number": "123456", "account_id": "0009", **contact}
                value = payload("Optional " + str(index), phone_details=details)
                self.assertEqual(self.request("POST", payload=value)[0], 200)
                self.stop_server(); self.start_server()
                status, _, body = self.request()
                self.assertEqual(status, 200)
                saved = next(v for v in json.loads(body)["vendors"] if v["name"] == value["vendor"])
                self.assertEqual(saved["phone_details"], {"number": "123456", "contact_name": "", "account_id": "0009", "extension": "", "notes": ""})

    def test_phone_empty_contact_clears_only_contact_preserving_legacy_values(self):
        for contact in ({"contact_name": ""}, {}):
            with self.subTest(contact=contact):
                first = payload(methods=list(vm.METHODS))
                vm.save(self.database, first)
                before = vm.load(self.database)[0]
                vm.initialize(self.database)
                self.assertEqual(vm.load(self.database)[0], before)
                details = {k: first["phone_details"][k] for k in ("number", "account_id")}
                value = payload(phone_details={**details, **contact})
                self.assertEqual(self.request("POST", payload=value)[0], 200)
                self.stop_server(); self.start_server()
                expected = {**before, "phone_details": {**before["phone_details"], "contact_name": ""}}
                self.assertEqual(vm.load(self.database)[0], expected)

    def test_phone_normalization_and_optional_replacement(self):
        details = {"number": "  +44   20-1234-5678  ", "contact_name": "  Ｊａｎｅ   Doe ", "account_id": "０００７-ab", "extension": "００７", "notes": "Line one\r\n\tLine two\r<script>text only</script>"}
        vm.save(self.database, payload(phone_details=details))
        expected = {"number": "+44 20-1234-5678", "contact_name": "Jane Doe", "account_id": "0007-ab", "extension": "007", "notes": "Line one\n\tLine two\n<script>text only</script>"}
        self.assertEqual(vm.load(self.database)[0]["phone_details"], expected)
        vm.save(self.database, payload(methods=["Email", "Portal"]))
        self.assertEqual(vm.load(self.database)[0]["phone_details"], expected)
        replacement = {k: expected[k] for k in ("number", "contact_name", "account_id")}
        vm.save(self.database, payload(phone_details=replacement))
        self.assertEqual(vm.load(self.database)[0]["phone_details"], expected)

    def test_builtin_other_aliases_rejected_without_checkbox(self):
        for alias in ("Phone", " PHONE ", "Ｐｈｏｎｅ", "Portal", " PORTAL ", "Ｐｏｒｔａｌ", "Email", "Ｅｍａｉｌ"):
            for methods in (["Other"], list(vm.METHODS)):
                self.assert_bad(payload(methods=methods, custom_method=alias))

    def test_portal_association_is_separate_from_vendor_wide(self):
        vm.save(self.database, payload(sop=attachment("generic.txt", b"Generic instructions")))
        generic = vm.load(self.database)[0]["sop"]
        self.assertIsNone(vm.load(self.database)[0]["portal_sop"])
        self.assertEqual(self.request("POST", payload=payload(methods=["Portal"], sop=None))[0], 400)
        vm.save(self.database, payload(methods=["Portal"], sop=attachment("portal-one.txt", b"Portal one")))
        first = vm.load(self.database)[0]["portal_sop"]
        self.assertEqual(vm.load(self.database)[0]["sop"], generic)
        self.assertEqual(self.request("POST", payload=payload(methods=["Portal"], sop=None))[0], 400)
        vm.save(self.database, payload(methods=["Email"], sop=attachment("generic-two.txt", b"Generic two")))
        self.assertEqual(vm.load(self.database)[0]["portal_sop"], first)
        vm.save(self.database, payload(sop=None))
        self.assertEqual(vm.load(self.database)[0]["portal_sop"], first)
        vm.save(self.database, payload(methods=["Portal", "Other"], sop=attachment("portal-two.txt", b"Portal two")))
        saved = vm.load(self.database)[0]
        self.assertEqual(saved["portal_sop"]["name"], "portal-two.txt")
        self.assertEqual(saved["sop"]["name"], "generic-two.txt")
        self.assertEqual(vm.load_sop(self.database, first["id"])[2], b"Portal one")
        self.assertEqual(vm.load_sop(self.database, generic["id"])[2], b"Generic instructions")
        with closing(vm.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM vm_portal_sops").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM vm_sops").fetchone()[0], 4)

    def test_phone_portal_atomic_failure_at_association_and_receipt(self):
        vm.save(self.database, payload(methods=list(vm.METHODS)))
        snapshot = vm.load(self.database)
        for table in ("vm_portal_details", "vm_portal_sops", "vm_submissions"):
            with closing(vm.connect(self.database)) as connection, connection:
                connection.execute("CREATE TRIGGER vm_test_fail BEFORE INSERT ON " + table + " BEGIN SELECT RAISE(ABORT, 'failure'); END")
            value = payload(methods=list(vm.METHODS), phone_details={"number": "+1 234 567 8900", "contact_name": "Changed", "account_id": "Changed"}, steps={"Other": ["Changed"]}, portal_details={"what_to_do": "Changed task", "how_to_do": "Changed procedure"}, sop=attachment("changed.txt", b"Changed"))
            self.assertEqual(self.request("POST", payload=value)[0], 503)
            self.assertEqual(vm.load(self.database), snapshot)
            with closing(vm.connect(self.database)) as connection, connection:
                for name in ("vm_sops", "vm_portal_sops", "vm_submissions"):
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM " + name).fetchone()[0], 1)
                connection.execute("DROP TRIGGER vm_test_fail")

    def test_phone_portal_restart_retry_and_changed_id_rejection(self):
        first = payload(methods=["Phone", "Portal"])
        vm.save(self.database, first)
        newer = payload(methods=["Phone", "Portal"], sop=attachment("new.txt", b"New portal"), phone_details={"number": "+33 123 456 789", "contact_name": "Later contact", "account_id": "007"})
        vm.save(self.database, newer)
        snapshot = vm.load(self.database)
        self.stop_server(); self.start_server()
        self.assertEqual(self.request("POST", payload=first)[0], 200)
        self.assertEqual(json.loads(self.request()[2])["vendors"], snapshot)
        for changed in ({**first, "phone_details": newer["phone_details"]}, {**first, "sop": attachment("other.txt", b"Other")}, {**first, "sop": attachment("portal.txt", b"Changed bytes")}):
            self.assertEqual(self.request("POST", payload=changed)[0], 400)
            self.assertEqual(vm.load(self.database), snapshot)
        with closing(vm.connect(self.database)) as connection:
            for table in ("vm_sops", "vm_portal_sops", "vm_submissions"):
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 2)

    def test_portal_concurrent_retries_one_association(self):
        value = payload(methods=["Phone", "Portal", "Other"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            self.assertEqual(list(pool.map(lambda _: self.request("POST", payload=value)[0], range(10))), [200] * 10)
        with closing(vm.connect(self.database)) as connection:
            for table in ("vm_sops", "vm_portal_sops", "vm_submissions", "vm_phone_details"):
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 1)

    def test_legacy_phone_portal_notes_and_generic_sop_migration(self):
        database = self.database.with_name(".old_methods_" + uuid.uuid4().hex + ".db")
        try:
            vm.initialize(database)
            vm.save(database, payload(sop=attachment("old.txt", b"Old generic SOP")))
            with closing(vm.connect(database)) as connection, connection:
                connection.execute("INSERT INTO vm_vendor_methods VALUES ('dell','portal','Portal')")
                connection.execute("INSERT INTO vm_vendor_methods VALUES ('dell','email','Email')")
                connection.executemany("INSERT INTO vm_method_steps VALUES ('dell',?,1,?)", [(m, "Prior " + m + " note") for m in ("phone", "portal", "email")])
                connection.execute("DROP TABLE vm_phone_details")
                connection.execute("DROP TABLE vm_portal_sops")
                receipts = connection.execute("SELECT * FROM vm_submissions").fetchall()
            vm.initialize(database); vm.initialize(database)
            before = vm.load(database)[0]
            self.assertIsNone(before["phone_details"])
            self.assertIsNone(before["portal_sop"])
            self.assertIsNone(before["email_details"])
            with self.assertRaises(ValueError):
                vm.save(database, payload(methods=["Portal"], sop=None))
            vm.save(database, payload(methods=list(vm.METHODS)))
            vm.initialize(database)
            saved = vm.load(database)[0]
            for m in ("Phone", "Portal", "Email"):
                self.assertEqual(saved["steps"][m], before["steps"][m])
            self.assertEqual(saved["sop"], before["sop"])
            self.assertEqual(vm.load_sop(database, before["sop"]["id"])[2], b"Old generic SOP")
            with closing(vm.connect(database)) as connection:
                self.assertTrue(set(receipts) <= set(connection.execute("SELECT * FROM vm_submissions").fetchall()))
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            database.unlink(missing_ok=True)

    def test_other_step_replacement_preserves_phone_and_portal(self):
        vm.save(self.database, payload(methods=list(vm.METHODS)))
        before = vm.load(self.database)[0]
        vm.save(self.database, payload(methods=["Other"], steps={"Other": ["Only new instruction"]}))
        saved = vm.load(self.database)[0]
        self.assertEqual(saved["steps"]["Partner help desk"], ["Only new instruction"])
        for key in ("phone_details", "portal_sop", "portal_details", "email_details", "sop"):
            self.assertEqual(saved[key], before[key])

    def test_portal_required_schema_and_unselected_rejected(self):
        value = payload(methods=["Portal"]); del value["portal_details"]
        self.assert_bad(value)
        for details in (None, [], "text", {}, {"what_to_do": "Task"}, {"how_to_do": "Procedure"},
                        {**payload(methods=["Portal"])["portal_details"], "url": "unexpected"}):
            self.assert_bad(payload(methods=["Portal"], portal_details=details))
        for methods in (["Phone"], ["Email"], ["Other"]):
            for details in (None, {}, {"what_to_do": "Task", "how_to_do": "Procedure"}):
                self.assert_bad(payload(methods=methods, portal_details=details))

    def test_portal_each_field_validation_and_multiline_boundary(self):
        for key in ("what_to_do", "how_to_do"):
            for text in (None, 42, True, [], {}, "", " \n\t ", "x" * 2001, "x\x00", "x\x7f", "x\u200b", "x\u202e", "x\ud800"):
                with self.subTest(key=key, text=text):
                    details = {"what_to_do": "Task", "how_to_do": "Procedure", key: text}
                    self.assert_bad(payload(methods=["Portal"], portal_details=details))
        details = {"what_to_do": "x" * 2000, "how_to_do": "y" * 2000}
        self.assertEqual(self.request("POST", payload=payload(methods=["Portal"], portal_details=details))[0], 200)
        self.assertEqual(vm.load(self.database)[0]["portal_details"], details)
        details = {"what_to_do": "  Ｏｐｅｎ case\r\n\tKeep indentation", "how_to_do": "<script>text only</script>\rClick New\n"}
        expected = {"what_to_do": "  Open case\n\tKeep indentation", "how_to_do": "<script>text only</script>\nClick New\n"}
        self.assertEqual(self.request("POST", payload=payload(methods=["Portal"], portal_details=details))[0], 200)
        self.assertEqual(json.loads(self.request()[2])["vendors"][0]["portal_details"], expected)

    def test_portal_details_restart_retry_and_nonportal_preservation(self):
        first = payload(methods=["Portal"])
        self.assertEqual(self.request("POST", payload=first)[0], 200)
        second = payload(methods=["Portal"], portal_details={"what_to_do": "Updated task", "how_to_do": "Updated\nprocedure"}, sop=attachment("new.txt", b"New SOP"))
        self.assertEqual(self.request("POST", payload=second)[0], 200)
        expected = vm.load(self.database)[0]
        self.stop_server(); self.start_server()
        for value in (second, first):
            self.assertEqual(self.request("POST", payload=value)[0], 200)
            self.assertEqual(json.loads(self.request()[2])["vendors"][0], expected)
        for key in ("what_to_do", "how_to_do"):
            changed = {**second, "portal_details": {**second["portal_details"], key: "Changed"}}
            self.assertEqual(self.request("POST", payload=changed)[0], 400)
            self.assertEqual(vm.load(self.database)[0], expected)
        for methods in (["Phone"], ["Email"], ["Other"]):
            self.assertEqual(self.request("POST", payload=payload(methods=methods, sop=attachment("generic.txt")))[0], 200)
            saved = vm.load(self.database)[0]
            self.assertEqual(saved["portal_details"], expected["portal_details"])
            self.assertEqual(saved["portal_sop"], expected["portal_sop"])
        self.assertEqual(self.request(path="/api/sops/" + expected["portal_sop"]["id"])[2], b"New SOP")
        vm.save(self.database, payload(vendor="Other vendor", methods=["Portal"]))
        self.assertEqual(vm.load(self.database)[0]["portal_details"], expected["portal_details"])

    def test_portal_details_additive_migration_without_fabrication(self):
        vm.save(self.database, payload(methods=list(vm.METHODS)))
        with closing(vm.connect(self.database)) as connection, connection:
            connection.execute("INSERT INTO vm_method_steps VALUES ('dell', 'portal', 1, 'Historical portal note')")
            connection.execute("DROP TABLE vm_portal_details")
            tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            before = {t: connection.execute("SELECT * FROM " + t).fetchall() for t in tables}
        vm.initialize(self.database); vm.initialize(self.database)
        saved = vm.load(self.database)[0]
        self.assertIsNone(saved["portal_details"])
        self.assertIsNotNone(saved["portal_sop"])
        self.assertEqual(saved["steps"]["Portal"], ["Historical portal note"])
        with closing(vm.connect(self.database)) as connection:
            self.assertEqual({t: connection.execute("SELECT * FROM " + t).fetchall() for t in tables}, before)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM vm_portal_details").fetchone()[0], 0)

    def test_portal_details_atomic_new_save_and_invalid_sop(self):
        for table in ("vm_portal_details", "vm_sops", "vm_portal_sops", "vm_submissions"):
            with closing(vm.connect(self.database)) as connection, connection:
                connection.execute("CREATE TRIGGER vm_test_fail BEFORE INSERT ON " + table + " BEGIN SELECT RAISE(ABORT, 'failure'); END")
            self.assertEqual(self.request("POST", payload=payload(methods=list(vm.METHODS)))[0], 503)
            self.assertEqual(vm.load(self.database), [])
            with closing(vm.connect(self.database)) as connection, connection:
                for name in ("vm_portal_details", "vm_phone_details", "vm_email_details", "vm_sops", "vm_portal_sops", "vm_submissions", "vm_vendor_methods", "vm_method_steps"):
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM " + name).fetchone()[0], 0)
                connection.execute("DROP TRIGGER vm_test_fail")
        vm.save(self.database, payload(methods=["Portal"]))
        snapshot = vm.load(self.database)
        for sop in (None, attachment("bad.html"), attachment("bad.txt", b"<script>bad</script>")):
            value = payload(methods=["Portal"], portal_details={"what_to_do": "Changed", "how_to_do": "Changed"}, sop=sop)
            self.assertEqual(self.request("POST", payload=value)[0], 400)
            self.assertEqual(vm.load(self.database), snapshot)

    def test_phone_three_fields_preserve_legacy_optional_values(self):
        details = {"number": "123456", "contact_name": "Contact", "account_id": "0009"}
        self.assertEqual(self.request("POST", payload=payload(phone_details=details))[0], 200)
        self.assertEqual(vm.load(self.database)[0]["phone_details"], {**details, "extension": "", "notes": ""})
        legacy = {**details, "extension": "007", "notes": "Legacy\nnotes"}
        vm.save(self.database, payload(phone_details=legacy))
        details["contact_name"] = "New contact"
        vm.save(self.database, payload(phone_details=details))
        self.stop_server(); self.start_server()
        self.assertEqual(vm.load(self.database)[0]["phone_details"], {**legacy, **details})
        vm.save(self.database, payload(phone_details={**details, "extension": "008"}))
        self.assertEqual(vm.load(self.database)[0]["phone_details"], {**legacy, **details, "extension": "008"})
        vm.save(self.database, payload(phone_details={**details, "notes": "Updated legacy notes"}))
        self.assertEqual(vm.load(self.database)[0]["phone_details"], {**details, "extension": "008", "notes": "Updated legacy notes"})

    def test_frontend_interactions(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js unavailable; mocked DOM interactions not run")
        page = Path(__file__).with_name("vendor_management.html")
        result = subprocess.run([node, "-e", FRONTEND_CHECK, str(page)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("assertions (not a real browser)", result.stdout)
        print(result.stdout.strip())

    def test_page_contract(self):
        text = self.server.page.decode()
        parser = PageParser(); parser.feed(text)
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        self.assertFalse(parser.external); self.assertFalse(parser.events)
        self.assertEqual([i["value"] for i in parser.inputs if i.get("type") == "checkbox"], list(vm.METHODS))
        self.assertEqual(next(i for i in parser.inputs if i.get("id") == "vendor")["type"], "text")
        self.assertNotIn("<select", text); self.assertNotIn("custom-vendor", text)
        self.assertNotIn("innerHTML", text); self.assertIn("textContent", text)
        self.assertIn("fetch('/api/vendors'", text); self.assertIn(".normalize('NFKC')", text)
        self.assertIn('aria-labelledby="sop-title"', text)
        self.assertIn("dialog.showModal()", text)
        self.assertIn("dialog.addEventListener('cancel'", text)


FRONTEND_CHECK = 'const assert = require(\'node:assert/strict\');\nconst fs = require(\'node:fs\');\nconst vm = require(\'node:vm\');\nconst crypto = require(\'node:crypto\');\nconst html = fs.readFileSync(process.argv[1], \'utf8\');\nconst ids = new Map();\nconst methods = [];\nlet document;\nlet checks = 0;\nconst check = (actual, expected, message) => { assert.deepEqual(actual, expected, message); checks++; };\nfunction unregister(node) {\n  if (ids.get(node.id) === node) ids.delete(node.id);\n  node.children.forEach(unregister);\n}\nclass Node {\n  constructor(tag) { this.tagName = tag; this.children = []; this.listeners = {}; this.value = \'\'; this.checked = false; this.disabled = false; this.hidden = false; this.files = []; this.attributes = {}; this.textContent = \'\'; }\n  set id(value) { this._id = value; ids.set(value, this); }\n  get id() { return this._id; }\n  append(...nodes) { this.children.push(...nodes); }\n  replaceChildren(...nodes) { this.children.forEach(unregister); this.children = nodes; }\n  setAttribute(key, value) { this.attributes[key] = value; }\n  addEventListener(type, action) { (this.listeners[type] ||= []).push(action); }\n  async emit(type) { const event = {preventDefault() {}}; for (const action of this.listeners[type] || []) await action(event); }\n  querySelectorAll(selector) {\n    const all = this.children.flatMap(n => [n, ...n.querySelectorAll(\'*\')]);\n    return selector === \'*\' ? all : all.filter(n => n.tagName === selector);\n  }\n  focus() { document.activeElement = this; }\n  showModal() { this.open = true; }\n  close() { this.open = false; }\n  reportValidity() {\n    return [...ids.values()].filter(n => [\'input\', \'textarea\'].includes(n.tagName) && n.required && !n.disabled).every(n => n.value.length > 0);\n  }\n}\nfor (const match of html.matchAll(/<(\\w+)\\b([^>]*)>/g)) {\n  const [, tag, raw] = match;\n  const attributes = Object.fromEntries([...raw.matchAll(/([\\w-]+)="([^"]*)"/g)].map(m => [m[1], m[2]]));\n  const node = new Node(tag);\n  if (attributes.id) node.id = attributes.id;\n  Object.assign(node, {type: attributes.type, value: attributes.value || \'\', name: attributes.name, disabled: /\\bdisabled\\b/.test(raw), required: /\\brequired\\b/.test(raw), hidden: /\\bhidden\\b/.test(raw)});\n  if (attributes.name === \'method\') methods.push(node);\n}\ndocument = {activeElement: null, getElementById: id => ids.get(id), createElement: tag => new Node(tag), querySelectorAll: selector => selector.endsWith(\':checked\') ? methods.filter(n => n.checked) : methods};\nconst posts = [];\nlet nextError = false;\nlet heldPost = null;\nlet hold = false;\nconst context = vm.createContext({document, crypto, AbortController, console, setTimeout, clearTimeout, FileReader: class {\n  readAsDataURL(file) { this.result = \'data:application/octet-stream;base64,\' + Buffer.from(file.body).toString(\'base64\'); this.onload(); }\n}, fetch: async (url, options = {}) => {\n  check(url, \'/api/vendors\', \'API is same origin\');\n  if (options.method === \'POST\') {\n    posts.push(JSON.parse(options.body));\n    if (nextError) { nextError = false; throw new TypeError(\'Network failure\'); }\n    if (hold) await new Promise(resolve => { heldPost = resolve; });\n    return {ok: true, json: async () => ({message: \'Saved.\'})};\n  }\n  return {ok: true, json: async () => ({vendors: []})};\n}});\nvm.runInContext(html.match(/<script>([\\s\\S]*?)<\\/script>/)[1], context);\nconst get = id => ids.get(id);\nconst settle = async () => { for (let i = 0; i < 5; i++) await new Promise(r => setImmediate(r)); };\nconst input = async (id, value) => { get(id).value = value; await get(id).emit(\'input\'); };\nconst select = async (method, checked = true) => { const n = methods.find(n => n.value === method); n.checked = checked; await n.emit(\'change\'); };\nasync function submit() { await get(\'vendor-form\').emit(\'submit\'); await settle(); }\nasync function click(id) { await get(id).emit(\'click\'); await settle(); }\n(async () => {\n  await settle();\n  check(methods.map(n => n.value), [\'Phone\',\'Email\',\'Portal\',\'Other\'], \'four checkboxes\');\n  check(get(\'vendor\').type, \'text\', \'free vendor name\');\n  await submit(); check(!!get(\'sop-dialog\').open, false, \'invalid form cannot prompt\');\n  await input(\'vendor\', \'Acme\'); await submit();\n  check(!!get(\'sop-dialog\').open, false, \'at least one method required\');\n  await select(\'Other\'); await input(\'custom-method\', \'Partner desk\');\n  check(get(\'method-section-Other\').hidden, false, \'selected steps shown\');\n  check(get(\'method-section-Email\').hidden, true, \'other steps independent\');\n  await submit(); check(!!get(\'sop-dialog\').open, false, \'blank step blocks prompt\');\n  await input(\'instruction-Other-0\', \'  \'); await submit();\n  check(!!get(\'sop-dialog\').open, false, \'whitespace-only step blocks prompt\');\n  await input(\'instruction-Other-0\', \'Call support\');\n  await click(\'add-step-Other\'); await input(\'instruction-Other-1\', \'Give contract number\');\n  await click(\'add-step-Other\'); await input(\'instruction-Other-2\', \'Record reference\');\n  await get(\'steps-Other\').children[1].children[1].children[1].emit(\'click\');\n  check(get(\'instruction-Other-1\').value, \'Record reference\', \'remove preserves later instruction\');\n  check(get(\'steps-Other\').children[1].children[0].textContent, \'Step 2\', \'renumber after removal\');\n  await select(\'Other\', false); await select(\'Other\');\n  check(get(\'instruction-Other-1\').value, \'Record reference\', \'toggle retains draft\');\n  await select(\'Phone\');\n  await input(\'phone-number\', \'+44 20 1234 5678\');\n  await input(\'phone-contact_name\', \'Support team\');\n  await input(\'phone-account_id\', \'000123\');\n  await select(\'Phone\', false);\n  check(get(\'phone-number\').disabled, true, \'unselected input disabled\');\n  await submit(); check(get(\'sop-dialog\').open, true, \'valid form prompts\');\n  check(document.activeElement.id, \'sop-yes\', \'prompt initial focus\');\n  check(posts.length, 0, \'prompt does not save\');\n  await click(\'sop-cancel\'); check(posts.length, 0, \'Cancel has no write\');\n  check(document.activeElement.id, \'save\', \'Cancel restores submit focus\');\n  await submit(); await get(\'sop-dialog\').emit(\'cancel\');\n  check(!!get(\'sop-dialog\').open, false, \'Escape cancels\'); check(posts.length, 0, \'Escape has no write\');\n  await submit(); await click(\'sop-no\');\n  check(posts.length, 1, \'No really submits\'); check(posts[0].sop, null, \'No has no attachment\');\n  check(posts[0].methods, [\'Other\'], \'only selected methods\');\n  check(posts[0].steps, {Other: [\'Call support\', \'Record reference\']}, \'selected steps ordered\');\n  check(posts[0].custom_method, \'Partner desk\', \'selected custom method retained\');\n  check(!!get(\'sop-dialog\').open, false, \'success closes prompt\');\n  await select(\'Other\', false); await select(\'Other\');\n  check(get(\'custom-method\').value, \'Partner desk\', \'Other name draft retained\');\n  check(get(\'instruction-Other-0\').value, \'Call support\', \'Other steps draft retained\');\n  await input(\'instruction-Other-0\', \'Contact partner\');\n  await submit(); await click(\'sop-yes\');\n  check(get(\'sop-picker\').hidden, false, \'Yes shows picker\');\n  check(posts.length, 1, \'Yes alone does not write\');\n  await click(\'sop-save\'); check(posts.length, 1, \'Yes needs file\');\n  get(\'sop-file\').files = [{name: \'bad.html\', size: 10, body: \'<script/>\'}];\n  await click(\'sop-save\'); check(posts.length, 1, \'invalid extension rejected before write\');\n  get(\'sop-file\').files = [{name: \'huge.txt\', size: 10 * 1024 * 1024 + 1, body: \'x\'}];\n  await click(\'sop-save\'); check(posts.length, 1, \'oversize file rejected before read/write\');\n  get(\'sop-file\').files = [{name: \'guide.txt\', size: 9, body: \'Step one.\'}];\n  nextError = true; await click(\'sop-save\');\n  check(get(\'sop-dialog\').open, true, \'failure retains prompt\');\n  check(posts.length, 2, \'failed request recorded\');\n  await click(\'sop-save\');\n  check(posts.length, 3, \'retry sent\');\n  check(posts[1].request_id, posts[2].request_id, \'retry uses same id\');\n  check(posts[2].steps.Other, [\'Contact partner\', \'Record reference\'], \'Other steps saved\');\n  check(posts[2].sop, {name: \'guide.txt\', data: Buffer.from(\'Step one.\').toString(\'base64\')}, \'file encoded\');\n  await submit(); hold = true; const inFlight = click(\'sop-no\'); await settle();\n  check(get(\'sop-cancel\').disabled, true, \'in-flight cancel disabled\');\n  await get(\'sop-dialog\').emit(\'cancel\'); check(get(\'sop-dialog\').open, true, \'Escape cannot hide in-flight save\');\n  await click(\'sop-no\'); check(posts.length, 4, \'double submit guarded\');\n  heldPost(); hold = false; await inFlight; await settle();\n  await get(\'vendor-form\').emit(\'reset\');\n  for (const n of methods) n.checked = false;\n  get(\'vendor\').value = \'\'; get(\'custom-method\').value = \'\';\n  await new Promise(r => setTimeout(r, 5));\n  check(get(\'instruction-Other-0\').value, \'\', \'reset clears step draft\');\n  check(get(\'method-section-Phone\').hidden, true, \'reset hides sections\');\n  vm.runInContext(`vendors = [{name: \'<img src=x onerror=alert(1)>\', methods: [\'<script>\'], steps: {\'<script>\': [\'<svg onload=x>\']}, sop: null}]; loaded = true; render();`, context);\n  check(get(\'vendor-list\').children[0].children[0].children[1].textContent, \'<img src=x onerror=alert(1)>\', \'untrusted names are text\');\n  check(get(\'vendor-list\').children[0].children[1].children[1].children[0].textContent, \'<svg onload=x>\', \'untrusted steps are text\');\n  await input(\'vendor\', \'Email vendor\'); await select(\'Email\');\n  check(get(\'method-section-Email\').hidden, false, \'Email section visible\');\n  check(get(\'email-address\').required, true, \'Email address required\');\n  check(get(\'email-subject\').required, true, \'Email subject required\');\n  check(get(\'email-body\').tagName, \'textarea\', \'body supports multiline input\');\n  check(get(\'steps-Email\'), undefined, \'no Email step container exists\');\n  check(get(\'instruction-Email-0\'), undefined, \'no Email step input exists\');\n  check(get(\'add-step-Email\'), undefined, \'no Email Add step button exists\');\n  check(get(\'method-section-Email\').querySelectorAll(\'ol\').length, 0, \'Email has no numbered list\');\n  check(get(\'method-section-Email\').children[1].textContent, \'Email uses the details below; no numbered steps are required.\', \'visible local sync marker\');\n  await submit(); check(!!get(\'sop-dialog\').open, false, \'blank email fields block prompt\');\n  await input(\'email-address\', \'bad\'); await input(\'email-subject\', \'Case\');\n  await submit(); check(!!get(\'sop-dialog\').open, false, \'invalid email blocks prompt\');\n  await input(\'email-address\', \'Agent@VENDOR.example\');\n  await input(\'email-subject\', \'Bad\\r\\nBcc: test@x.example\');\n  await submit(); check(!!get(\'sop-dialog\').open, false, \'subject injection blocks prompt\');\n  await input(\'email-subject\', \'Case [number]\');\n  await input(\'email-opening\', \'Hello,\\n\\tTeam\'); await input(\'email-body\', \'<img src=x>\\nDetails\');\n  const addressField = get(\'email-address\');\n  await select(\'Email\', false);\n  check(get(\'email-address\').disabled, true, \'unselected address disabled\');\n  check(get(\'email-address\').required, false, \'unselected email not required\');\n  check(get(\'email-body\').disabled, true, \'unselected multiline disabled\');\n  await select(\'Email\');\n  check(get(\'email-address\') === addressField, true, \'toggle never rebuilds email fields\');\n  check(get(\'email-subject\').disabled, false, \'reselected subject enabled\');\n  check(get(\'email-subject\').required, true, \'reselected subject required\');\n  check(get(\'email-opening\').required, false, \'opening remains optional\');\n  check(get(\'email-body\').required, false, \'body remains optional\');\n  check(get(\'email-opening\').value, \'Hello,\\n\\tTeam\', \'toggle preserves email draft\');\n  await submit(); await click(\'sop-cancel\');\n  check(get(\'email-body\').value, \'<img src=x>\\nDetails\', \'Cancel retains email draft\');\n  const previousCount = posts.length;\n  await submit(); await input(\'email-subject\', \'Edited behind modal\');\n  nextError = true; await click(\'sop-no\'); await click(\'sop-no\');\n  check(posts.length, previousCount + 2, \'email error retry sent\');\n  const emailPost = posts[posts.length - 1];\n  check(emailPost.email_details, {address: \'Agent@vendor.example\', subject: \'Case [number]\', opening: \'Hello,\\n\\tTeam\', body: \'<img src=x>\\nDetails\'}, \'immutable email snapshot and multiline content\');\n  check(emailPost.request_id, posts[posts.length - 2].request_id, \'email retry stable ID\');\n  check(emailPost.steps, {}, \'Email-only payload has explicit empty steps\');\n  await select(\'Phone\');\n  await submit(); check(!!get(\'sop-dialog\').open, false, \'Email plus blank Phone fields blocks modal\');\n  await input(\'phone-number\', \'+1 (212) 555-0100\');\n  await input(\'phone-contact_name\', \'Help desk\'); await input(\'phone-account_id\', \'00042\');\n  await submit(); await click(\'sop-no\');\n  check(posts[posts.length - 1].methods, [\'Phone\', \'Email\'], \'mixed methods retained\');\n  check(posts[posts.length - 1].steps, {}, \'mixed payload has no steps\');\n  check(posts[posts.length - 1].phone_details.account_id, \'00042\', \'account ID preserves leading zeros\');\n  await select(\'Email\', false); await select(\'Phone\');\n  await submit(); await click(\'sop-no\');\n  check(\'email_details\' in posts[posts.length - 1], false, \'non-Email payload omits details\');\n  await select(\'Phone\', false); await select(\'Other\');\n  await input(\'custom-method\', \'Ｅｍａｉｌ\'); await input(\'instruction-Other-0\', \'Send\');\n  await submit(); check(!!get(\'sop-dialog\').open, false, \'Other Email alias rejected\');\n  vm.runInContext(`vendors = [{name: \'Email Vendor\', methods: [\'Email\'], steps: {Email: [\'Send later\']}, email_details: {address: \'a@b.example\', subject: \'<script>alert(1)</script>\', opening: \'Hello,\\\\nTeam\', body: \'<img src=x>\\\\nBody\'}, sop: null}]; loaded = true; render();`, context);\n  const emailValues = get(\'vendor-list\').children[0].children[1].children[1];\n  check(emailValues.tagName, \'dl\', \'email labels rendered with values\');\n  check(emailValues.className, \'email-values\', \'email whitespace preserved by CSS\');\n  check(emailValues.children[0].textContent, \'Vendor support email\', \'directory labels address\');\n  check(emailValues.children[3].textContent, \'<script>alert(1)</script>\', \'subject rendered as text not HTML\');\n  check(emailValues.children[7].textContent, \'<img src=x>\\nBody\', \'body rendered as multiline text\');\n  const emailSection = get(\'vendor-list\').children[0].children[1];\n  check(emailSection.children[2].textContent, \'Prior Email notes (read-only) — retained for reference; no step entry required.\', \'historical notes clearly read-only\');\n  check(emailSection.children[3].tagName, \'ul\', \'historical notes are unnumbered\');\n  check(emailSection.children[3].children[0].textContent, \'Send later\', \'historical note retained\');\n  check(emailSection.querySelectorAll(\'ol\').length, 0, \'directory Email has no numbered UI\');\n  vm.runInContext(`vendors[0].email_details = null; render();`, context);\n  check(get(\'vendor-list\').children[0].children[1].children[1].textContent, \'Legacy Email method — email details not yet recorded.\', \'legacy email fields explicitly missing\');\n  vm.runInContext(`vendors[0].steps.Email = []; render();`, context);\n  check(get(\'vendor-list\').children[0].children[1].children.length, 2, \'legacy Email without notes shows no missing steps message\');\n  vm.runInContext(`vendors[0].methods.push(\'Phone\'); vendors[0].steps.Phone = []; render();`, context);\n  check(get(\'vendor-list\').children[0].children[2].children[1].textContent, \'Legacy Phone method — phone details not yet recorded.\', \'legacy Phone details not invented\');\n  await select(\'Other\', false); await select(\'Email\');\n  await get(\'vendor-form\').emit(\'reset\');\n  for (const n of methods) n.checked = false;\n  await new Promise(r => setTimeout(r, 5));\n  check(get(\'email-address\').disabled, true, \'Clear disables unselected email fields\');\n  check(get(\'email-subject\').required, false, \'Clear unsets email requirement\');\n  check(get(\'steps-Email\'), undefined, \'Clear does not create or query Email steps\');\n  check(get(\'email-address\').value, \'\', \'Clear resets email draft\');\n  check(get(\'email-body\').value, \'\', \'Clear resets body draft\');\n  for (const method of [\'Phone\', \'Portal\', \'Email\']) {\n    check(get(\'steps-\' + method), undefined, method + \' has no step container\');\n    check(get(\'instruction-\' + method + \'-0\'), undefined, method + \' has no step input\');\n    check(get(\'add-step-\' + method), undefined, method + \' has no Add step button\');\n    check(get(\'method-section-\' + method).querySelectorAll(\'ol\').length, 0, method + \' has no numbered UI\');\n  }\n  await input(\'vendor\', \'New requirements\'); await select(\'Phone\');\n  for (const key of [\'number\', \'account_id\']) check(get(\'phone-\' + key).required, true, key + \' required for Phone\');\n  check(get(\'phone-contact_name\').required, false, \'Phone contact optional\');\n  check(get(\'method-section-Phone\').querySelectorAll(\'label\').map(n => n.textContent), [\'Phone number *\', \'Contact person name (optional)\', \'Account ID *\'], \'only contact label has no required marker\');\n  check(get(\'phone-extension\'), undefined, \'no extension field\');\n  check(get(\'phone-notes\'), undefined, \'no Phone notes field\');\n  check(get(\'method-section-Phone\').querySelectorAll(\'input\').length, 3, \'Phone collects only three fields\');\n  check(get(\'method-section-Phone\').querySelectorAll(\'textarea\').length, 0, \'Phone has no extra textarea\');\n  await input(\'phone-number\', \'+44 (0)20 1234-5678\');\n  await input(\'phone-contact_name\', \'  Jane   Doe \'); await input(\'phone-account_id\', \'000123\');\n  const phoneField = get(\'phone-number\');\n  await select(\'Phone\', false);\n  for (const key of [\'number\', \'contact_name\', \'account_id\']) {\n    check(get(\'phone-\' + key).disabled, true, key + \' disabled while hidden\');\n    check(get(\'phone-\' + key).required, false, key + \' not required while hidden\');\n  }\n  await select(\'Phone\');\n  check(phoneField === get(\'phone-number\'), true, \'Phone toggle never rebuilds fields\');\n  check(get(\'phone-account_id\').value, \'000123\', \'Phone toggle retains account ID\');\n  check(get(\'phone-contact_name\').required, false, \'contact remains optional after toggle\');\n  for (const blank of [\'\', \'   \', \'\\u3000\']) {\n    await input(\'phone-contact_name\', blank); await submit();\n    check(get(\'sop-dialog\').open, true, \'blank contact permits Phone save\');\n    await click(\'sop-no\');\n    check(posts[posts.length - 1].phone_details.contact_name, \'\', \'blank contact normalizes to empty\');\n  }\n  for (const key of [\'number\', \'account_id\']) {\n    const previous = get(\'phone-\' + key).value;\n    await input(\'phone-\' + key, \'\'); await submit();\n    check(!!get(\'sop-dialog\').open, false, key + \' remains required with blank contact\');\n    await input(\'phone-\' + key, previous);\n  }\n  for (const bad of [\'---\', \'x\'.repeat(101), \'\\n\', \'\\t\', \'x\\u0000\', \'x\\u200b\', \'x\\u202e\']) {\n    await input(\'phone-contact_name\', bad); await submit();\n    check(!!get(\'sop-dialog\').open, false, \'malformed optional contact blocks prompt\');\n  }\n  await input(\'phone-contact_name\', \'  Ｊａｎｅ   Doe \');\n  const originalPhone = {number: \'+44 (0)20 1234-5678\', contact_name: \'Jane Doe\', account_id: \'000123\'};\n  for (const [key, text] of [[\'number\',\'12\'], [\'number\',\'++1234\'], [\'number\',\'123\\n\'], [\'contact_name\',\'---\'], [\'account_id\',\'   \']]) {\n    const previous = get(\'phone-\' + key).value;\n    await input(\'phone-\' + key, text); await submit();\n    check(!!get(\'sop-dialog\').open, false, \'invalid Phone \' + key + \' blocks modal\');\n    await input(\'phone-\' + key, previous);\n  }\n  await select(\'Portal\');\n  check(get(\'method-section-Portal\').querySelectorAll(\'textarea\').length, 2, \'Portal has two separate cells\');\n  check(get(\'method-section-Portal\').children[3].className, \'portal-fields\', \'Portal responsive two-column container\');\n  check(html.includes(\'.portal-fields{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)\'), true, \'Portal desktop two columns\');\n  check(html.includes(\'@media(max-width:650px){.portal-fields{grid-template-columns:1fr}}\'), true, \'Portal mobile stacked\');\n  check(get(\'method-section-Portal\').children[3].children.map(n => n.children[0].textContent), [\'What to do *\', \'How to do *\'], \'exact Portal labels\');\n  for (const key of [\'what_to_do\', \'how_to_do\']) {\n    check(get(\'portal-\' + key).required, true, key + \' required\');\n    check(get(\'portal-\' + key).maxLength, 2000, key + \' bounded\');\n  }\n  await submit(); check(!!get(\'sop-dialog\').open, false, \'both missing Portal fields block prompt\');\n  await input(\'portal-what_to_do\', \'Open case\');\n  await submit(); check(!!get(\'sop-dialog\').open, false, \'missing How to do blocks prompt\');\n  await input(\'portal-how_to_do\', \'Sign in\'); await input(\'portal-what_to_do\', \'\');\n  await submit(); check(!!get(\'sop-dialog\').open, false, \'missing What to do blocks prompt\');\n  const originalPortal = {what_to_do: \'Open case\\n\\tDescribe issue\', how_to_do: \'<img src=x>\\nClick New\'};\n  for (const key of [\'what_to_do\', \'how_to_do\']) await input(\'portal-\' + key, originalPortal[key]);\n  for (const key of [\'what_to_do\', \'how_to_do\']) {\n    for (const text of [\' \\n\\t \', \'x\'.repeat(2001), \'x\\u0000\', \'x\\u200b\', \'x\\u202e\']) {\n      await input(\'portal-\' + key, text); await submit();\n      check(!!get(\'sop-dialog\').open, false, \'invalid Portal \' + key + \' blocks prompt\');\n    }\n    await input(\'portal-\' + key, \'x\'.repeat(2000)); await submit();\n    check(get(\'sop-dialog\').open, true, key + \' accepts boundary\'); await click(\'sop-cancel\');\n    await input(\'portal-\' + key, originalPortal[key]);\n  }\n  await input(\'portal-how_to_do\', \'<img src=x>\\r\\nClick New\');\n  const portalField = get(\'portal-what_to_do\');\n  await select(\'Portal\', false);\n  check(get(\'method-section-Portal\').hidden, true, \'Portal hidden when unselected\');\n  for (const key of [\'what_to_do\', \'how_to_do\']) {\n    check(get(\'portal-\' + key).disabled, true, key + \' disabled when hidden\');\n    check(get(\'portal-\' + key).required, false, key + \' not required when hidden\');\n  }\n  await select(\'Portal\');\n  check(get(\'portal-what_to_do\') === portalField, true, \'Portal toggle does not rebuild fields\');\n  check(get(\'portal-what_to_do\').value, originalPortal.what_to_do, \'Portal toggle retains multiline draft\');\n  await submit();\n  check(get(\'sop-title\').textContent, \'Portal SOP is mandatory\', \'Portal mandatory heading\');\n  check(get(\'sop-no\').hidden, true, \'Portal has no No bypass\');\n  check(get(\'sop-picker\').hidden, true, \'Portal keeps explicit Yes flow\');\n  const beforePortal = posts.length;\n  await click(\'sop-no\');\n  check(posts.length, beforePortal, \'programmatic No cannot bypass Portal\');\n  await click(\'sop-yes\'); get(\'sop-file\').files = [];\n  await click(\'sop-save\'); check(posts.length, beforePortal, \'Portal requires actual file\');\n  await click(\'sop-cancel\');\n  check(get(\'phone-account_id\').value, \'000123\', \'Cancel keeps Phone draft\');\n  check(get(\'portal-what_to_do\').value, originalPortal.what_to_do, \'Cancel keeps Portal draft\');\n  await submit(); await get(\'sop-dialog\').emit(\'cancel\');\n  check(posts.length, beforePortal, \'Portal Escape has no write\');\n  await submit(); await click(\'sop-yes\');\n  await select(\'Portal\', false);\n  await input(\'phone-contact_name\', \'Changed behind modal\');\n  await input(\'portal-what_to_do\', \'Changed behind modal\');\n  await input(\'portal-how_to_do\', \'Also changed behind modal\');\n  await click(\'sop-no\');\n  check(posts.length, beforePortal, \'pending Portal requirement immutable after background toggle\');\n  get(\'sop-file\').files = [{name: \'portal.txt\', size: 6, body: \'Portal\'}];\n  nextError = true; await click(\'sop-save\');\n  check(get(\'sop-dialog\').open, true, \'Portal error retains modal\');\n  await click(\'sop-save\');\n  const portalPost = posts[posts.length - 1];\n  check(portalPost.phone_details, originalPhone, \'immutable Phone snapshot during Portal retry\');\n  check(Object.keys(portalPost.phone_details), [\'number\', \'contact_name\', \'account_id\'], \'Phone payload has only three fields\');\n  check(portalPost.portal_details, originalPortal, \'immutable normalized Portal snapshot during retry\');\n  check(portalPost.portal_details, posts[posts.length - 2].portal_details, \'retry retains exact Portal details\');\n  check(portalPost.methods, [\'Phone\', \'Portal\'], \'immutable Portal selection\');\n  check(portalPost.steps, {}, \'Phone and Portal never send steps\');\n  check(portalPost.request_id, posts[posts.length - 2].request_id, \'Portal retry uses same ID\');\n  check(portalPost.sop, posts[posts.length - 2].sop, \'Portal retry preserves attachment bytes\');\n  check(get(\'save-status\').textContent.includes(\'New Portal SOP attached.\'), true, \'Portal save labelled separately\');\n  await submit();\n  check(get(\'sop-no\').hidden, false, \'nonportal submission restores optional No\');\n  await click(\'sop-cancel\');\n  await input(\'phone-contact_name\', \'\');\n  await input(\'email-address\', \'support@vendor.example\'); await input(\'email-subject\', \'Help\');\n  await input(\'custom-method\', \'Partner desk\'); await input(\'instruction-Other-0\', \'Open partner help desk\');\n  for (let mask = 1; mask < 16; mask++) {\n    for (let i = 0; i < methods.length; i++) await select(methods[i].value, !!(mask & (1 << i)));\n    await submit();\n    check(get(\'sop-dialog\').open, true, \'combination \' + mask + \' validates without hidden requirements\');\n    const selected = methods.filter(n => n.checked).map(n => n.value);\n    const portal = selected.includes(\'Portal\');\n    check(get(\'sop-no\').hidden, portal, \'combination \' + mask + \' Portal requirement\');\n    if (portal) {\n      await click(\'sop-yes\'); get(\'sop-file\').files = [{name:\'portal.txt\', size:6, body:\'Portal\'}]; await click(\'sop-save\');\n    } else await click(\'sop-no\');\n    const post = posts[posts.length - 1];\n    check(post.methods, selected, \'combination \' + mask + \' selected methods\');\n    check(Object.keys(post.steps), selected.includes(\'Other\') ? [\'Other\'] : [], \'combination \' + mask + \' Other-only steps\');\n    check(\'phone_details\' in post, selected.includes(\'Phone\'), \'combination \' + mask + \' Phone conditional payload\');\n    check(\'email_details\' in post, selected.includes(\'Email\'), \'combination \' + mask + \' Email conditional payload\');\n    check(!!post.sop, portal, \'combination \' + mask + \' attachment\');\n    check(\'portal_details\' in post, portal, \'combination \' + mask + \' Portal conditional payload\');\n  }\n  for (const m of [\'Phone\',\'Email\',\'Portal\']) await select(m, false);\n  for (const alias of [\'Phone\', \'Ｐｈｏｎｅ\', \' portal \', \'Ｐｏｒｔａｌ\']) {\n    await input(\'custom-method\', alias); await submit();\n    check(!!get(\'sop-dialog\').open, false, \'Other built-in alias rejected \' + alias);\n  }\n  vm.runInContext(`vendors = [{name: \'Legacy vendor\', methods: [\'Phone\', \'Portal\'], steps: {Phone: [\'Old phone instruction\'], Portal: [\'Old portal instruction\']}, phone_details: {number:\'+1 212 555-0100\', contact_name:\'<img src=x>\', account_id:\'0007\', extension:\'007\', notes:\'Line one\\\\n<script>plain text</script>\'}, portal_sop: {id:\'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\', name:\'Portal guide.txt\'}, sop:{id:\'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\', name:\'Generic guide.txt\', size:5}}]; loaded = true; render();`, context);\n  const phoneSection = get(\'vendor-list\').children[0].children[1];\n  const portalSection = get(\'vendor-list\').children[0].children[2];\n  check(phoneSection.children[1].tagName, \'dl\', \'Phone labelled directory values\');\n  check(phoneSection.children[1].children[0].textContent, \'Phone number\', \'Phone number label\');\n  check(phoneSection.children[1].children[3].textContent, \'<img src=x>\', \'Phone contact safely rendered as text\');\n  check(phoneSection.children[1].children[5].textContent, \'0007\', \'Phone account ID string display\');\n  check(phoneSection.children[1].children.length, 6, \'Phone directory shows only three labelled values\');\n  check(phoneSection.children[2].textContent.includes(\'Prior Phone notes (read-only)\'), true, \'legacy Phone notes labelled read-only\');\n  check(phoneSection.children[3].tagName, \'ul\', \'Phone notes unnumbered\');\n  check(portalSection.children[2].textContent, \'Download current Portal SOP: Portal guide.txt\', \'Portal download clearly associated\');\n  check(portalSection.children[2].href, \'/api/sops/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\', \'Portal opaque same-origin download\');\n  check(portalSection.children[3].textContent.includes(\'Prior Portal notes (read-only)\'), true, \'legacy Portal notes labelled read-only\');\n  check(portalSection.children[1].textContent, \'Legacy Portal method — What to do and How to do not yet recorded.\', \'legacy Portal details not fabricated\');\n  vm.runInContext(`vendors[0].portal_details = {what_to_do:\'<script>plain text</script>\', how_to_do:\'First\\\\n\\\\tSecond\'}; render();`, context);\n  const portalValues = get(\'vendor-list\').children[0].children[2].children[1];\n  check(portalValues.tagName, \'dl\', \'Portal directory labelled details\');\n  check(portalValues.children[0].textContent, \'What to do\', \'What to do directory label\');\n  check(portalValues.children[1].textContent, \'<script>plain text</script>\', \'Portal text rendered safely\');\n  check(portalValues.children[2].textContent, \'How to do\', \'How to do directory label\');\n  check(portalValues.children[3].textContent, \'First\\n\\tSecond\', \'Portal multiline preserved\');\n  check(portalValues.className, \'email-values\', \'Portal whitespace preserved by CSS\');\n  for (const section of [phoneSection, portalSection]) check(section.querySelectorAll(\'ol\').length, 0, \'no numbered canonical directory lists\');\n  vm.runInContext(`vendors[0].phone_details = null; vendors[0].portal_sop = null; vendors[0].portal_details = null; vendors[0].steps = {Phone:[],Portal:[]}; render();`, context);\n  check(get(\'vendor-list\').children[0].children[1].children[1].textContent, \'Legacy Phone method — phone details not yet recorded.\', \'legacy Phone not fabricated\');\n  check(get(\'vendor-list\').children[0].children[2].children[2].textContent.includes(\'vendor-wide SOP does not count\'), true, \'generic SOP not shown as Portal SOP\');\n  check(get(\'vendor-list\').children[0].children[2].children.length, 3, \'legacy Portal has no missing-steps prompt\');\n  await get(\'vendor-form\').emit(\'reset\');\n  for (const n of methods) n.checked = false;\n  await new Promise(r => setTimeout(r, 5));\n  for (const key of [\'number\',\'contact_name\',\'account_id\']) {\n    check(get(\'phone-\' + key).value, \'\', \'Clear resets Phone \' + key);\n    check(get(\'phone-\' + key).disabled, true, \'Clear disables Phone \' + key);\n    check(get(\'phone-\' + key).required, false, \'Clear removes requirement for Phone \' + key);\n  }\n  for (const key of [\'what_to_do\', \'how_to_do\']) {\n    check(get(\'portal-\' + key).value, \'\', \'Clear resets Portal \' + key);\n    check(get(\'portal-\' + key).disabled, true, \'Clear disables Portal \' + key);\n    check(get(\'portal-\' + key).required, false, \'Clear removes Portal requirement \' + key);\n  }\n  console.log(\'Mocked DOM flow checks passed: \' + checks + \' assertions (not a real browser).\');\n})().catch(error => { console.error(error); process.exitCode = 1; });\n'


if __name__ == "__main__":
    unittest.main(verbosity=2)
