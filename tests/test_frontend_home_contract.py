"""Regression checks for the presentation-ready portal landing page."""

from pathlib import Path
import re


FRONTEND_HOME = Path(__file__).resolve().parents[1] / "frontend" / "index.html"


def test_home_operations_area_is_freshness_only():
    """The clean landing page must not expose sync controls beside module discovery."""
    html = FRONTEND_HOME.read_text(encoding="utf-8")
    match = re.search(
        r'<div class="portal-operations"[^>]*>(.*?)</div>\s*</div>\s*<!-- Multi-Domain',
        html,
        re.DOTALL,
    )
    assert match, "Expected the home-page operations area"
    operations = match.group(1)

    assert 'id="headerSyncPill"' in operations
    assert 'id="btnTriggerSync"' not in operations
    assert 'id="btnSyncLedger"' not in operations


def test_dex_does_not_claim_unsupported_security_or_sla_data():
    """DEX must label unavailable fields honestly instead of presenting invented values."""
    html = FRONTEND_HOME.read_text(encoding="utf-8")
    start = html.index('<section id="view-endpoints"')
    dex = html[start:html.index("</section>", start)]

    assert "Target: 95.0% SLA" not in dex
    assert "Hardware TPM 2.0 Enforced" not in dex
