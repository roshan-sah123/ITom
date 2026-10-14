#!/usr/bin/env python3
"""Safely add a local Vendor Management launcher to the adjacent frontend/index.html."""
import argparse
import hashlib
from html.parser import HTMLParser
import os
from pathlib import Path
import stat
import sys
from datetime import datetime, timezone
from uuid import uuid4

URL = "http://127.0.0.1:8081/vendor_management.html"
LINK_ID = "vendor-management-nav-link"
CSS = "vendor_management_nav.css"
JS = "vendor_management_nav.js"
VOID = set("area base br col embed hr img input link meta param source track wbr".split())


class Refused(ValueError):
    pass


class Element:
    def __init__(self, tag, attrs, start, parent):
        self.tag, self.attrs, self.start, self.parent = tag, dict(attrs), start, parent
        self.end = None
        self.close = None
        self.text = []
        self.children = []

    def ancestors(self):
        node = self.parent
        while node:
            yield node
            node = node.parent

    def label(self):
        return " ".join("".join(self.text).split()).casefold()


class Source(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.source = text
        self.lines = [0]
        self.lines.extend(i + 1 for i, c in enumerate(text) if c == "\n")
        self.nodes, self.stack = [], []
        self.feed(text)
        self.close()

    def source_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs, self.source_offset(), self.stack[-1] if self.stack else None)
        if len(dict(attrs)) != len(attrs):
            raise Refused("Duplicate HTML attributes: resolve these before installation.")
        if node.parent:
            node.parent.children.append(node)
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)
        else:
            node.end = node.start + len(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop().end = self.source_offset() + len(self.get_starttag_text())

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == tag:
                node = self.stack[index]
                node.close = self.source_offset()
                end = self.source.find(">", node.close)
                if end < 0:
                    raise Refused("Incomplete closing HTML tag.")
                node.end = end + 1
                del self.stack[index:]
                return

    def handle_data(self, data):
        if any(n.tag in {"script", "style", "svg"} or n.attrs.get("aria-hidden") == "true"
               for n in self.stack):
            return
        for node in self.stack:
            node.text.append(data)


def nav_for(node):
    return next((n for n in node.ancestors() if n.tag == "nav"), None)


def plan(original):
    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Refused("index.html must be UTF-8; no encoding conversion was attempted.") from exc
    doc = Source(text)
    candidates = [n for n in doc.nodes if n.tag in {"a", "button"} and nav_for(n)
                  and (n.label() in {"automation", "automations"}
                       or n.attrs.get("data-view", "").casefold() in {"automation", "automations"}
                       or any(c.label() in {"automation", "automations"} for c in n.children))]
    if len(candidates) != 1:
        raise Refused("Expected exactly one static Automations button/link inside <nav>; found %d. Nothing changed." % len(candidates))
    target = candidates[0]
    nav = nav_for(target)
    if target.end is None or nav.end is None or any(n.tag in {"template", "a", "button"} for n in target.ancestors()):
        raise Refused("Automations markup is incomplete, nested, or inside a template.")
    head = [n for n in doc.nodes if n.tag == "head" and n.close is not None]
    body = [n for n in doc.nodes if n.tag == "body" and n.close is not None]
    if len(head) != 1 or len(body) != 1 or body[0] not in list(nav.ancestors()):
        raise Refused("Expected one explicit </head>, one </body>, and navigation inside body.")
    if any(n.tag == "base" and "href" in n.attrs for n in doc.nodes):
        raise Refused("A <base href> changes asset resolution; manual integration is required.")
    refs = [n for n in doc.nodes if n.attrs.get("href", "").split("?")[0].split("#")[0].split("/")[-1] == CSS
            or n.attrs.get("src", "").split("?")[0].split("#")[0].split("/")[-1] == JS]
    existing = [n for n in doc.nodes if n.attrs.get("id") == LINK_ID
                or (nav_for(n) and n.tag in {"a", "button"} and (
                    "vendor management" in n.label() or "vendor_management" in n.attrs.get("href", "")
                    or "vendor-management" in n.attrs.get("data-view", "")
                    or "vendor_management" in n.attrs.get("data-view", "")
                    or any(c.label() == "vendor management" for c in n.children)))]
    if existing:
        link = existing[0]
        css_ok = any(n.tag == "link" and n.attrs.get("href") == CSS and n.attrs.get("rel") == "stylesheet" for n in refs)
        js_ok = any(n.tag == "script" and n.attrs.get("src") == JS and "defer" in n.attrs for n in refs)
        rel = set(link.attrs.get("rel", "").split())
        same_parent = link.parent is target.parent
        immediately_after = same_parent and link.parent.children.index(link) == link.parent.children.index(target) + 1
        if target.parent and target.parent.tag == "li" and link.parent and link.parent.tag == "li":
            tp, lp = target.parent, link.parent
            immediately_after = tp.parent is lp.parent and tp.parent.children.index(lp) == tp.parent.children.index(tp) + 1
        if (len(existing) == 1 and link.tag == "a" and link.attrs.get("id") == LINK_ID
                and link.attrs.get("href") == URL and link.attrs.get("target") == "_blank"
                and "noopener" in rel and link.label() == "vendor management"
                and "vendor-management-nav-link" in link.attrs.get("class", "").split()
                and "nav-tab" not in link.attrs.get("class", "").split() and "data-view" not in link.attrs
                and nav_for(link) is nav and immediately_after and len(refs) == 2 and css_ok and js_ok):
            return original, "already installed"
        raise Refused("Vendor Management already exists or the kit is partially installed. Review it manually; nothing was overwritten or duplicated.")
    if refs:
        raise Refused("Navigation asset references already exist without a verified launcher; nothing changed.")
    newline = "\r\n" if "\r\n" in text else "\n"
    link = ('<a id="%s" class="vendor-management-nav-link" href="%s" target="_blank" '
            'rel="noopener" title="Local Vendor Management companion (opens in a new tab)">'
            '<span>Vendor Management</span></a>') % (LINK_ID, URL)
    after = target.end
    if target.parent.tag == "li":
        if target.parent.end is None or target.parent.parent.tag not in {"ul", "ol"}:
            raise Refused("Unsupported Automations list structure.")
        after = target.parent.end
        link = '<li class="vendor-management-nav-item">' + link + '</li>'
    elif target.parent.tag not in {"nav", "div"}:
        raise Refused("Unsupported Automations container; manual integration is required.")
    inserts = [(after, newline + link),
               (head[0].close, '<link rel="stylesheet" href="%s">' % CSS + newline),
               (body[0].close, '<script src="%s" defer></script>' % JS + newline)]
    changed = text
    for offset, addition in sorted(inserts, reverse=True):
        changed = changed[:offset] + addition + changed[offset:]
    # Slicing the original source is intentional: existing bytes are never reserialized.
    parts, previous = [], 0
    for offset, addition in sorted(inserts):
        parts.extend([text[previous:offset], addition])
        previous = offset
    parts.append(text[previous:])
    if changed != "".join(parts):
        raise Refused("Insertion verification failed.")
    result = changed.encode("utf-8")
    verified, status = plan(result)
    if verified != result or status != "already installed":
        raise Refused("Generated navigation failed verification.")
    return result, "ready"


def install(frontend, dry_run=False):
    frontend = Path(frontend).absolute()
    if frontend.name.casefold() != "frontend" or frontend.is_symlink():
        raise Refused("Keep this installer in the project's real frontend folder, not its root.")
    index = frontend / "index.html"
    required = [index, frontend / CSS, frontend / JS,
                frontend / "vendor_management.html", frontend / "vendor_management_server.py"]
    for path in required:
        if path.is_symlink() or not path.is_file():
            raise Refused("Required adjacent regular file is missing or is a symlink: " + str(path))
    info = index.stat()
    def signature(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mode, value.st_nlink)
    def unchanged():
        return (not index.is_symlink() and signature(index.stat()) == signature(info)
                and index.read_bytes() == original)
    if info.st_nlink != 1 or info.st_size > 16 * 1024 * 1024:
        raise Refused("Refusing a hard-linked or unexpectedly large index.html.")
    original = index.read_bytes()
    changed, status = plan(original)
    if status == "already installed":
        print("Already installed and verified. No files changed.")
        return None
    if dry_run:
        print("Dry run passed: one link after Automations, one stylesheet, one deferred script. No files changed.")
        return None
    backup_dir = frontend.parent / ".vendor-management-backups"
    if backup_dir.is_symlink():
        raise Refused("Backup directory must not be a symlink.")
    backup_dir.mkdir(mode=0o700, exist_ok=True)
    lock = backup_dir / "install.lock"
    try:
        descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise Refused("Another install may be running. Review " + str(lock) + " before retrying.") from exc
    os.close(descriptor)
    token = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid4().hex
    backup = backup_dir / ("index-" + token + ".html.bak")
    staged = frontend / (".index-vendor-" + token + ".stage")
    try:
        if not unchanged():
            raise Refused("index.html changed during inspection; retry after closing editors.")
        with backup.open("xb") as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
        if backup.read_bytes() != original:
            raise Refused("Backup verification failed; index.html was not changed.")
        with staged.open("xb") as stream:
            stream.write(changed)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(staged, stat.S_IMODE(info.st_mode))
        if not unchanged():
            raise Refused("index.html changed before replacement; backup retained, index left untouched.")
        os.replace(staged, index)
    finally:
        if staged.exists():
            staged.unlink()
        lock.unlink()
    print("Installed Vendor Management immediately after Automations.")
    print("Backup: " + str(backup))
    print("Original SHA-256: " + hashlib.sha256(original).hexdigest())
    print("Opens " + URL + " in a new tab; existing companion/database files were not changed.")
    print("Rollback (only if no later index edits should be kept):")
    print('python -c "import shutil; shutil.copyfile(' + repr(str(backup)) + ', ' + repr(str(index)) + ')"')
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing any files")
    args = parser.parse_args()
    try:
        install(Path(__file__).absolute().parent, args.dry_run)
    except (OSError, ValueError, RecursionError) as exc:
        print("REFUSED: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
