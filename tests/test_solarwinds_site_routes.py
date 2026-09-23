import asyncio

from app.repositories.ci_repository import CIRepository
from app.services.ci_service import CIService


def test_solarwinds_sites_service_returns_demo_sites():
    """The site dashboard can obtain a non-empty site catalog offline."""
    sites = asyncio.run(CIService(CIRepository()).get_solarwinds_sites())

    assert sites
    assert {"id", "name", "availability_pct"} <= sites[0].keys()


def test_solarwinds_site_trend_service_returns_requested_window():
    """Site drilldown returns the requested number of hourly samples."""
    trend = asyncio.run(CIService(CIRepository()).get_solarwinds_site_trend("demo", hours=24))

    assert trend["hours"] == 24
    assert len(trend["data_points"]) == 24
