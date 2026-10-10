"""Validate deployed HTML assets and the zero-build ES-module graph."""
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "img"} and attrs.get("src"):
            self.assets.append(attrs["src"])
        elif tag == "link" and attrs.get("rel") in {"stylesheet", "icon"}:
            self.assets.append(attrs["href"])


def test_html_assets_resolve_in_served_directory():
    pages = list(FRONTEND.glob("*.html"))
    assert pages, "The portal must contain an HTML entry point"
    for page in pages:
        parser = AssetParser()
        parser.feed(page.read_text(encoding="utf-8"))
        for asset in parser.assets:
            url = urlsplit(asset)
            if url.scheme or url.netloc:
                continue
            target = (FRONTEND / url.path.lstrip("/")) if url.path.startswith("/") else page.parent / url.path
            assert target.is_file(), f"{page.name} references missing asset {asset}"


def test_local_es_module_imports_resolve():
    # Includes static imports and re-exports, preserving query-versioned paths.
    pattern = re.compile(r"(?:import|export)\s+(?:[^;]*?\s+from\s+)?['\"]([^'\"]+)['\"]")
    for module in (FRONTEND / "js").rglob("*.js"):
        for specifier in pattern.findall(module.read_text(encoding="utf-8")):
            if specifier.startswith("."):
                target = module.parent / urlsplit(specifier).path
                assert target.is_file(), f"{module.name} imports missing module {specifier}"


def test_frontend_needs_no_bundler():
    for name in ("webpack.config.js", "vite.config.js", "rollup.config.js", "esbuild.config.js"):
        assert not (FRONTEND.parent / name).exists()
