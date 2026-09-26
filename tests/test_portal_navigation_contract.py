"""Navigation contracts for the primary portal and its tucked-away operations views."""

from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PortalParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.primary_views = []
        self.sections = {}
        self.footer_views = []
        self.current_section = None
        self.section_text = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "button" and "nav-tab" in classes:
            self.primary_views.append(attrs.get("data-view"))
        if tag == "section" and attrs.get("id", "").startswith("view-"):
            self.current_section = attrs["id"]
            self.sections[self.current_section] = ""
        if tag == "button" and "footer-operation-link" in classes:
            self.footer_views.append(attrs.get("data-target-view"))

    def handle_endtag(self, tag):
        if tag == "section":
            self.current_section = None

    def handle_data(self, data):
        if self.current_section:
            self.sections[self.current_section] += data


def portal():
    parser = PortalParser()
    parser.feed((ROOT / "frontend/index.html").read_text(encoding="utf-8"))
    return parser


def test_primary_navigation_has_six_user_facing_modules():
    assert portal().primary_views == [
        "home", "infrastructure", "endpoints", "cmdb", "knowledge", "automations"
    ]


def test_sync_pages_are_only_linked_from_operations_footer():
    parser = portal()
    assert parser.footer_views == ["sync", "sync-schedule"]
    assert "data-view=\"sync\"" not in (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert "data-view=\"sync-schedule\"" not in (ROOT / "frontend/index.html").read_text(encoding="utf-8")


def test_new_modules_have_clear_coming_soon_content():
    parser = portal()
    knowledge = parser.sections["view-knowledge"].lower()
    automations = parser.sections["view-automations"].lower()
    assert "coming soon" in knowledge
    assert "onboarding" in knowledge and "recorded" in knowledge
    assert "coming soon" in automations
    assert "operational workflows" in automations


def test_home_workspace_links_to_new_modules_without_direct_sync_links():
    home = (ROOT / "frontend/js/components/home.js").read_text(encoding="utf-8")
    assert 'data-target-view="knowledge"' in home
    assert 'data-target-view="automations"' in home
    assert 'data-target-view="sync"' not in home


def test_scheduler_view_has_distinct_id_and_remains_wired():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    app = (ROOT / "frontend/js/app.js").read_text(encoding="utf-8")
    scheduler = (ROOT / "frontend/js/components/syncSchedule.js").read_text(encoding="utf-8")
    assert 'id="view-sync-schedule"' in html
    assert "case 'sync-schedule':" in app
    assert "view-sync-schedule" in scheduler


def test_operations_footer_adapts_on_small_screens():
    css = (ROOT / "frontend/css/style.css").read_text(encoding="utf-8")
    assert ".footer-operations" in css
    assert "@media (max-width: 600px)" in css
