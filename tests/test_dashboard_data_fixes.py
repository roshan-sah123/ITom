"""Regression contracts for the dashboard data audit fixes."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cmdb_provenance_is_rendered_from_the_summary_payload():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/js/components/cmdb.js").read_text(encoding="utf-8")

    assert 'id="cmdbProvenanceIntuneBar"' in html
    assert 'id="cmdbProvenanceSolarWindsBar"' in html
    assert 'id="cmdbProvenanceIntuneLabel"' in html
    assert 'id="cmdbProvenanceSolarWindsLabel"' in html
    assert "renderCmdbProvenance(summary)" in js
    assert "intuneBar.style.width" in js
    assert "solarWindsBar.style.width" in js
    assert "formatPercent" in js
    assert "27,412 CIs (94.6%)" not in html
    assert "1,572 CIs (5.4%)" not in html


def test_infrastructure_labels_all_solarwinds_nodes_and_reports_server_count_separately():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/js/components/infraWorkspace.js").read_text(encoding="utf-8")
    summary_repo = (ROOT / "app/repositories/summary_repository.py").read_text(encoding="utf-8")

    assert "TOTAL SOLARWINDS NODES" in html
    assert "SOLARWINDS NODE INVENTORY" in html
    assert "server_nodes_count" in js
    assert "renderSwSaturatedTriage(summary.top_saturated_servers" in js
    assert "solarwinds_role(row.vendor, row.ci_type) != \"server\"" in summary_repo
    assert "Classified servers of ${formatNumber(totalNodes)} SolarWinds nodes" in js
    assert "${formatNumber(serverCount ?? 0)} servers" in js


def test_endpoint_kpis_start_and_fail_as_unavailable_instead_of_old_sample_values():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/js/components/endpoints.js").read_text(encoding="utf-8")

    assert 'id="epTotalVal">Unavailable<' in html
    assert 'id="epCompRateVal">Unavailable<' in html
    assert 'id="epTotalSub">22,735 Compliant Fleet<' not in html
    assert "renderEndpointsUnavailable()" in js
    assert "function renderEndpointsUnavailable()" in js
