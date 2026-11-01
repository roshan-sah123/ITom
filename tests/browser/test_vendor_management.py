"""Portal-native vendor journeys against a migrated, isolated test database."""

import io
from pathlib import Path

import pytest
from PIL import Image
from tests.browser.dialog_assertions import assert_centered, assert_no_review_metadata

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


@pytest.fixture
def vendor_url(module_portal_url):
    return module_portal_url


def open_vendor(page, url):
    page.goto(url)
    page.get_by_role("button", name="Vendor Management", exact=True).click()
    expect(page.get_by_role("heading", name="Vendor Management", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="+ Fill vendor form", exact=True)).to_be_enabled()
    assert page.url == url


def fill_vendor(page):
    page.get_by_role("button", name="+ Fill vendor form", exact=True).click()
    page.get_by_role("textbox", name="Vendor name", exact=True).fill("Journey partner")
    page.get_by_role("textbox", name="Method", exact=True).fill("Portal")
    page.get_by_role("textbox", name="Step 1 What to do", exact=True).fill("Open support")
    page.get_by_role("textbox", name="Step 1 How to do", exact=True).fill("Follow the approved process")


def test_vendor_submit_prompt_review_edit_details_and_delete(vendor_url, browser_context):
    page = browser_context.new_page()
    open_vendor(page, vendor_url)
    fill_vendor(page)
    page.get_by_role("button", name="Submit", exact=True).click()
    dialog = page.get_by_role("dialog", name="Do you want to attach SOP?")
    expect(dialog).to_be_visible()
    assert_centered(dialog)
    assert browser_context.request.get(vendor_url + "api/v1/vendors/submissions").json()["total"] == 0
    dialog.get_by_role("button", name="Cancel", exact=True).click()
    expect(page.get_by_role("textbox", name="Vendor name", exact=True)).to_have_value("Journey partner")
    page.get_by_role("button", name="Submit", exact=True).click()
    page.get_by_role("button", name="No, save submission", exact=True).click()
    row = page.locator(".vendor-table tbody tr")
    expect(row).to_contain_text("Journey partner")
    expect(row).to_contain_text("Pending")
    page.get_by_role("button", name="Open submission", exact=True).click()
    expect(page.get_by_role("dialog", name="Submission details")).to_contain_text("Follow the approved process")
    assert_centered(page.get_by_role("dialog", name="Submission details"))
    assert_no_review_metadata(page.get_by_role("dialog", name="Submission details"))
    page.get_by_role("button", name="Close Submission details", exact=True).click()
    page.get_by_role("button", name="Validate", exact=True).click()
    review = page.get_by_role("dialog", name="Validate submission")
    assert_centered(review)
    review.get_by_label("Reviewer name", exact=True).fill("Journey reviewer")
    review.get_by_label("CMDB admin key", exact=True).fill("wrong-key")
    review.get_by_role("button", name="Validate", exact=True).click()
    expect(review.get_by_role("alert")).to_contain_text("valid CMDB admin key")
    review.get_by_label("CMDB admin key", exact=True).fill("isolated-review-key")
    review.get_by_role("button", name="Validate", exact=True).click()
    expect(row).to_contain_text("Validated")
    page.get_by_role("button", name="Edit", exact=True).click()
    page.get_by_label("CMDB admin key", exact=True).fill("isolated-review-key")
    page.get_by_role("button", name="+ Add step", exact=True).click()
    page.get_by_role("textbox", name="Step 2 What to do", exact=True).fill("Check receipt")
    page.get_by_role("textbox", name="Step 2 How to do", exact=True).fill("Record reference")
    page.get_by_role("button", name="Submit", exact=True).click()
    page.get_by_role("button", name="Yes, attach SOP", exact=True).click()
    page.locator(".vendor-sop-picker input").set_input_files({
        "name": "journey.txt", "mimeType": "text/plain", "buffer": b"Approved procedure",
    })
    page.get_by_role("button", name="Attach SOP and save", exact=True).click()
    expect(row).to_contain_text("2 steps")
    expect(row).to_contain_text("Pending")
    page.reload()
    page.get_by_role("button", name="Vendor Management", exact=True).click()
    expect(row).to_contain_text("Journey partner")
    page.get_by_role("button", name="Open submission", exact=True).click()
    expect(page.get_by_role("dialog", name="Submission details")).to_contain_text("Record reference")
    page.get_by_role("button", name="View SOP", exact=True).click()
    preview = page.get_by_role("dialog", name="SOP preview")
    assert_centered(preview)
    expect(preview.locator("pre")).to_have_text("Approved procedure")
    preview.get_by_role("button", name="Close SOP preview", exact=True).click()
    with page.expect_download() as downloaded:
        page.get_by_role("link", name="journey.txt", exact=True).click()
    assert Path(downloaded.value.path()).read_bytes() == b"Approved procedure"
    page.get_by_role("button", name="Close Submission details", exact=True).click()
    page.get_by_role("button", name="Delete", exact=True).click()
    deletion = page.get_by_role("dialog", name="Delete submission")
    assert_centered(deletion)
    deletion.get_by_label("CMDB admin key", exact=True).fill("isolated-review-key")
    deletion.get_by_role("button", name="Delete", exact=True).click()
    expect(row).to_have_count(0)
    fill_vendor(page)
    page.get_by_role("button", name="Submit", exact=True).click()
    page.get_by_role("button", name="No, save submission", exact=True).click()
    expect(row.locator("td").first).to_have_text("1")
    records = browser_context.request.get(vendor_url + "api/v1/vendors/submissions").json()["items"]
    assert records[0]["id"] > 1 and records[0]["serial"] == 1
    assert page.url == vendor_url
    assert [tab.url for tab in browser_context.pages if tab.url.startswith("http")] == [vendor_url]
    page.close()


def test_vendor_image_and_mobile_form(vendor_url, browser_context):
    page = browser_context.new_page()
    open_vendor(page, vendor_url)
    fill_vendor(page)
    content = io.BytesIO()
    Image.new("RGB", (4, 4)).save(content, format="PNG")
    page.get_by_label("Step 1 Screenshot", exact=True).set_input_files({
        "name": "step.png", "mimeType": "image/png", "buffer": content.getvalue(),
    })
    expect(page.locator(".vendor-selected-file")).to_contain_text("step.png")
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_role("textbox", name="Vendor name", exact=True)).to_be_visible()
    assert page.locator(".vendor-form-columns").last.evaluate(
        "el => getComputedStyle(el).gridTemplateColumns.split(' ').length"
    ) == 1
    page.get_by_role("button", name="Submit", exact=True).click()
    page.get_by_role("button", name="No, save submission", exact=True).click()
    page.get_by_role("button", name="Open submission", exact=True).click()
    assert_centered(page.get_by_role("dialog", name="Submission details"))
    image = page.locator(".vendor-detail-image img")
    expect(image).to_be_visible()
    page.wait_for_function("document.querySelector('.vendor-detail-image img').naturalWidth === 4")
    assert page.url == vendor_url
    page.get_by_role("button", name="Enlarge Step 1 screenshot", exact=True).click()
    expect(page.get_by_role("dialog", name="Screenshot preview").get_by_role("img")).to_be_visible()
    assert_centered(page.get_by_role("dialog", name="Screenshot preview"))
    page.close()
