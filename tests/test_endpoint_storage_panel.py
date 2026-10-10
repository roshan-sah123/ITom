"""Contracts for source-backed endpoint storage metrics."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_endpoint_charts_include_storage_panel():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert 'id="epStoragePanel"' in html
    assert 'id="epStorageBadge"' in html
    assert 'id="epStorageContent"' in html


def test_live_storage_panel_uses_intune_metrics_and_labels_coverage():
    js = (ROOT / "frontend/js/components/endpoints.js").read_text(encoding="utf-8")
    assert "median_device_storage_used_pct" in js
    assert "fleet_capacity_used_pct" in js
    assert "storage_sample_size" in js
    assert "Live Intune data" in js
    assert "Based on ${formatNumber(sample)} devices with storage data" in js
