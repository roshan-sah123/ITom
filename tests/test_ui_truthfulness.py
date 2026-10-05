from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_served_legacy_shells_have_no_fabricated_live_metrics():
    content = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    cmdb = (ROOT / "frontend" / "cmdb_explorer.html").read_text(encoding="utf-8")
    analytics = (ROOT / "frontend" / "infrastructure_analytics.html").read_text(encoding="utf-8")
    assert "27,412" not in content + cmdb
    assert "0% Duplicates" not in content + cmdb
    assert "PostgreSQL 16" not in content + cmdb + analytics
    assert "Fresh &lt;1m" not in analytics


def test_infrastructure_analytics_entry_does_not_self_import():
    source = (ROOT / "frontend" / "js" / "infrastructure_analytics.js").read_text(encoding="utf-8")
    assert "import './infrastructure_analytics.js'" not in source
    assert "initializeInfrastructureAnalytics" in source


def test_unavailable_storage_has_no_demo_percentages():
    source = (ROOT / "frontend" / "js" / "components" / "endpoints.js").read_text(encoding="utf-8")
    assert "renderStorageDemo" not in source
    assert "renderStorageUnavailable" in source
    assert "(demo), 68" not in source
