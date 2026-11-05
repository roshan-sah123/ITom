"""Portal-native vendor journeys against a migrated, isolated test database."""

import io
from urllib.parse import parse_qs, urljoin, urlsplit

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
    details = page.get_by_role("dialog", name="Submission details")
    expect(details).not_to_contain_text("not scanned")
    view = details.get_by_role("link", name="View SOP", exact=True)
    expect(view).to_have_attribute("target", "_blank")
    assert "attachment=" in view.get_attribute("href")
    with page.expect_popup() as popup:
        view.click()
    preview = popup.value
    expect(preview.locator("body")).to_contain_text("Approved procedure")
    assert "attachment=" in preview.url
    expect(preview.locator("pre")).to_have_text("Approved procedure")
    preview.close()
    expect(details.locator("a[download]")).to_have_count(0)
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


@pytest.mark.parametrize("filename,mime,content", [
    ("compressed.pdf", "application/pdf", b"%PDF-1.7\n1 0 obj << /Type /ObjStm /Encrypt 2 0 R >> endobj\nstartxref\n0\n%%EOF"),
    ("linked.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK\x03\x04opaque document"),
    ("instructions.txt", "text/plain", b"\xff\xfeT\x00e\x00x\x00t\x00"),
])
def test_vendor_sop_download_only_accepts_opaque_documents(vendor_url, browser_context, filename, mime, content):
    page = browser_context.new_page()
    open_vendor(page, vendor_url)
    fill_vendor(page)
    page.get_by_role("button", name="Submit", exact=True).click()
    page.get_by_role("button", name="Yes, attach SOP", exact=True).click()
    page.locator(".vendor-sop-picker input").set_input_files({
        "name": filename, "mimeType": mime, "buffer": content,
    })
    page.get_by_role("button", name="Attach SOP and save", exact=True).click()
    expect(page.locator(".vendor-table tbody tr")).to_contain_text("Journey partner")
    page.get_by_role("button", name="Open submission", exact=True).click()
    details = page.get_by_role("dialog", name="Submission details")
    expect(details).not_to_contain_text("not scanned")
    expect(details.locator("iframe")).to_have_count(0)
    expect(details.get_by_role("link", name="View SOP", exact=True)).to_have_attribute("target", "_blank")
    expect(details.locator("a[download]")).to_have_count(0)
    href = details.get_by_role("link", name="View SOP", exact=True).get_attribute("href")
    path = parse_qs(urlsplit(href).query)["attachment"][0]
    assert browser_context.request.get(urljoin(page.url, path)).body() == content
    page.close()
