"""Interim shared access UI gates only the three custom workspaces."""
import pytest

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def test_access_prompt_unlock_switch_and_lock(module_portal_url, browser_context):
    page = browser_context.new_page()
    state = {"authorized": False}

    def access(route):
        method = route.request.method
        if method == "POST":
            if route.request.post_data_json["key"] != "test-browser-access":
                route.fulfill(status=401, json={"detail": "The shared module access key is incorrect."})
                return
            state["authorized"] = True
        elif method == "DELETE":
            state["authorized"] = False
            route.fulfill(status=204)
            return
        route.fulfill(json={"authorized": state["authorized"], "local": False})

    page.route("**/api/v1/modules/access", access)
    page.goto(module_portal_url)
    page.get_by_role("button", name="Vendor Management", exact=True).click()
    prompt = page.get_by_role("dialog", name="Open shared modules")
    expect(prompt).to_be_visible()
    expect(page.get_by_role("region", name="Vendor submissions")).to_have_count(0)
    prompt.get_by_label("Shared module access key").fill("wrong-key")
    prompt.get_by_role("button", name="Open modules").click()
    expect(prompt.get_by_role("alert")).to_contain_text("incorrect")
    prompt.get_by_label("Shared module access key").fill("test-browser-access")
    prompt.get_by_role("button", name="Open modules").click()
    expect(page.get_by_role("heading", name="Vendor Management", exact=True)).to_be_visible()
    page.get_by_role("button", name="Knowledge Center", exact=True).click()
    expect(page.get_by_role("heading", name="Knowledge workspace")).to_be_visible()
    page.get_by_role("button", name="Assets Analytics", exact=True).click()
    expect(page.get_by_role("region", name="Asset inventory summary").get_by_role("button")).to_have_count(3)
    page.get_by_role("button", name="Lock shared modules").click()
    expect(prompt).to_be_visible()
    page.close()


def test_network_mode_opens_modules_without_key_or_session_toolbar(module_portal_url, browser_context):
    page = browser_context.new_page()
    page.route("**/api/v1/modules/access", lambda route: route.fulfill(
        json={"authorized": True, "local": False, "network": True}))
    page.goto(module_portal_url)
    page.get_by_role("button", name="Vendor Management", exact=True).click()
    expect(page.get_by_role("heading", name="Vendor Management", exact=True)).to_be_visible()
    expect(page.get_by_role("dialog", name="Open shared modules")).to_have_count(0)
    expect(page.get_by_role("button", name="Lock shared modules")).to_have_count(0)
    page.get_by_role("button", name="Knowledge Center", exact=True).click()
    expect(page.get_by_role("heading", name="Knowledge workspace")).to_be_visible()
    page.get_by_role("button", name="Assets Analytics", exact=True).click()
    expect(page.get_by_role("region", name="Asset inventory summary").get_by_role("button")).to_have_count(3)
    expect(page.get_by_role("dialog", name="Open shared modules")).to_have_count(0)
    page.close()
