import base64
from pathlib import Path

import pytest
from tests.browser.dialog_assertions import assert_centered, assert_no_review_metadata

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def open_knowledge(page, url):
    page.goto(url)
    page.get_by_role("button", name="Knowledge Center", exact=True).click()
    expect(page.get_by_role("button", name="+ Add content", exact=True)).to_be_enabled()
    expect(page.locator(".knowledge-local-note")).to_have_count(0)
    expect(page.get_by_role("button", name="Copy browser library", exact=True)).to_have_count(0)


def add_content(page, name="Journey guide"):
    page.get_by_role("button", name="+ Add content", exact=True).click()
    form = page.get_by_role("dialog", name="Add content", exact=True)
    assert_centered(form)
    for field in ["Validation status", "Validated by", "Validated on", "Serial no"]:
        expect(form.get_by_label(field, exact=True)).to_have_count(0)
    form.get_by_label("Content name *", exact=True).fill(name)
    form.get_by_label("Description *", exact=True).fill("Approved operational instructions")
    form.get_by_label("Content type *", exact=True).select_option("Other")
    form.get_by_label("Other category *", exact=True).fill("Operational reference")
    form.locator("input[type=file]").set_input_files({
        "name": "guide.txt", "mimeType": "text/plain", "buffer": b"Instructions <script>not executable</script>",
    })
    form.get_by_role("button", name="Add content", exact=True).click()
    expect(form).not_to_be_visible()


@pytest.mark.parametrize("filename,mime,raw", [
    ("compressed.pdf", "application/pdf", b"%PDF-1.7 /ObjStm /Encrypt"),
    ("linked.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK\x03\x04opaque document"),
    ("encoded.txt", "text/plain", b"\xff\xfeT\x00e\x00x\x00t\x00"),
])
def test_knowledge_opaque_document_upload_download(module_portal_url, browser_context, filename, mime, raw):
    page = browser_context.new_page()
    open_knowledge(page, module_portal_url)
    page.get_by_role("button", name="+ Add content", exact=True).click()
    form = page.get_by_role("dialog", name="Add content", exact=True)
    form.get_by_label("Content name *", exact=True).fill("Opaque document")
    form.get_by_label("Description *", exact=True).fill("Download only")
    form.get_by_label("Content type *", exact=True).select_option("Other")
    form.get_by_label("Other category *", exact=True).fill("Reference")
    form.locator("input[type=file]").set_input_files({"name": filename, "mimeType": mime, "buffer": raw})
    form.get_by_role("button", name="Add content", exact=True).click()
    expect(form).not_to_be_visible()
    page.get_by_role("button", name="Open", exact=True).click()
    details = page.get_by_role("dialog", name="Opaque document", exact=True)
    expect(details).to_contain_text("not scanned or previewed")
    expect(details.locator("iframe, pre")).to_have_count(0)
    expect(details.get_by_role("button", name="View file", exact=True)).to_have_count(0)
    with page.expect_download() as downloaded:
        details.get_by_role("link", name="Download file", exact=True).click()
    assert Path(downloaded.value.path()).read_bytes() == raw
    page.close()


def test_knowledge_grid_list_filter_edit_review_download_and_delete(module_portal_url, browser_context, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CMDB_INVENTORY_ADMIN_TOKEN", "isolated-review-key")
    page = browser_context.new_page()
    open_knowledge(page, module_portal_url)
    add_content(page)
    card = page.locator(".knowledge-card")
    expect(card).to_contain_text("Operational reference")
    expect(card).to_contain_text("Pending")
    page.get_by_role("button", name="Validate", exact=True).click()
    review = page.get_by_role("dialog", name="Validate content", exact=True)
    assert_centered(review)
    review.get_by_label("Validated by", exact=True).fill("Journey reviewer")
    review.get_by_label("CMDB admin key", exact=True).fill("wrong-key")
    review.get_by_role("button", name="Validate", exact=True).click()
    expect(review.get_by_role("alert")).to_contain_text("valid CMDB admin key")
    review.get_by_label("CMDB admin key", exact=True).fill("isolated-review-key")
    review.get_by_role("button", name="Validate", exact=True).click()
    expect(card).to_contain_text("Journey reviewer")
    expect(card.get_by_role("button", name="Validated", exact=True)).to_be_disabled()
    page.get_by_role("button", name="Pending", exact=True).click()
    expect(card).to_have_count(0)
    page.get_by_role("button", name="All", exact=True).click()
    page.get_by_role("searchbox", name="Search knowledge content").fill("guide.txt")
    expect(card).to_have_count(1)
    page.get_by_role("button", name="List", exact=True).click()
    expect(page.locator(".knowledge-table tbody tr")).to_contain_text("Journey reviewer")
    page.get_by_role("button", name="Edit", exact=True).click()
    edit = page.get_by_role("dialog", name="Edit content", exact=True)
    assert_centered(edit)
    expect(edit.get_by_label("Validation status", exact=True)).to_have_count(0)
    edit.get_by_label("Description *", exact=True).fill("Updated instructions")
    edit.get_by_label("CMDB admin key", exact=True).fill("isolated-review-key")
    edit.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.locator(".knowledge-table tbody tr")).to_contain_text("Pending")
    page.reload()
    page.get_by_role("button", name="Knowledge Center", exact=True).click()
    expect(page.locator(".knowledge-card")).to_contain_text("Updated instructions")
    page.get_by_role("button", name="Open", exact=True).click()
    details = page.get_by_role("dialog", name="Journey guide", exact=True)
    assert_centered(details)
    assert_no_review_metadata(details)
    expect(details.get_by_role("button", name="View file", exact=True)).to_have_count(0)
    expect(details).to_contain_text("Download only")
    with page.expect_download() as download:
        details.get_by_role("link", name="Download file", exact=True).click()
    assert Path(download.value.path()).read_bytes() == b"Instructions <script>not executable</script>"
    details.get_by_role("button", name="Close", exact=True).click()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.locator(".knowledge-grid").evaluate("el => getComputedStyle(el).gridTemplateColumns.split(' ').length") == 1
    page.get_by_role("button", name="Delete", exact=True).click()
    deletion = page.get_by_role("dialog", name="Delete content", exact=True)
    assert_centered(deletion)
    deletion.get_by_label("CMDB admin key", exact=True).fill("isolated-review-key")
    deletion.get_by_role("button", name="Delete", exact=True).click()
    expect(page.locator(".knowledge-card")).to_have_count(0)
    assert page.url == module_portal_url
    assert (browser_context.request.get(module_portal_url + "api/v1/vendors/submissions").json())["total"] == 0
    page.close()


def test_knowledge_submission_shared_across_profiles_without_publishing_legacy_content(module_portal_url, browser_context):
    page = browser_context.new_page()
    page.add_init_script("""if (!localStorage.getItem('test-legacy-seeded')) {
      localStorage.setItem('test-legacy-seeded','true');
      localStorage.setItem('itom-knowledge-centre-v1', JSON.stringify([{
        id:'legacy-record',serial:7,name:'Legacy guide',description:'Legacy instructions',category:'SOP',
        file:{name:'legacy.txt',type:'text/plain',size:6,data:'data:text/plain;base64,bGVnYWN5'},
        validatedOn:null,validatedBy:''
      }]));
    }""")
    open_knowledge(page, module_portal_url)
    expect(page.locator(".knowledge-card")).to_have_count(0)
    add_content(page, "Shared guide")
    expect(page.locator(".knowledge-card")).to_contain_text("Shared guide")
    independent = browser_context.browser.new_context()
    second = independent.new_page()
    open_knowledge(second, module_portal_url)
    second.get_by_role("button", name="Edit", exact=True).click()
    page.get_by_role("button", name="Edit", exact=True).click()
    edit = page.get_by_role("dialog", name="Edit content", exact=True)
    edit.get_by_label("Description *", exact=True).fill("Revision two")
    edit.get_by_label("CMDB admin key", exact=True).fill("isolated-review-key")
    edit.get_by_role("button", name="Save changes", exact=True).click()
    expect(edit).not_to_be_visible()
    expect(page.locator(".knowledge-card")).to_contain_text("Revision two")
    stale = second.get_by_role("dialog", name="Edit content", exact=True)
    stale.get_by_label("CMDB admin key", exact=True).fill("isolated-review-key")
    stale.get_by_role("button", name="Save changes", exact=True).click()
    expect(stale.get_by_role("alert")).to_contain_text("another view")
    stale.get_by_role("button", name="Cancel", exact=True).click()
    page.get_by_role("button", name="Open", exact=True).click()
    details = page.get_by_role("dialog", name="Shared guide", exact=True)
    expect(details.get_by_role("button", name="View file", exact=True)).to_have_count(0)
    expect(details).to_contain_text("Download only")
    details.get_by_role("button", name="Close", exact=True).click()
    page.get_by_role("button", name="Delete", exact=True).click()
    deletion = page.get_by_role("dialog", name="Delete content", exact=True)
    deletion.get_by_label("CMDB admin key", exact=True).fill("isolated-review-key")
    deletion.get_by_role("button", name="Delete", exact=True).click()
    expect(page.locator(".knowledge-card")).to_have_count(0)
    page.reload()
    page.get_by_role("button", name="Knowledge Center", exact=True).click()
    expect(page.get_by_role("button", name="+ Add content", exact=True)).to_be_enabled()
    expect(page.locator(".knowledge-card")).to_have_count(0)
    add_content(page, "Next guide")
    page.get_by_role("button", name="List", exact=True).click()
    expect(page.locator(".knowledge-table tbody tr td").first).to_have_text("1")
    assert page.evaluate("JSON.parse(localStorage.getItem('itom-knowledge-centre-v1'))[0].serial") == 7
    independent.close()
    page.close()


def test_knowledge_video_playback_and_browser_storage_independence(module_portal_url, browser_context):
    page = browser_context.new_page()
    open_knowledge(page, module_portal_url)
    video = page.evaluate("""async () => {
      const canvas = document.createElement('canvas'); canvas.width=16; canvas.height=16;
      const stream = canvas.captureStream(10), chunks=[];
      const recorder=new MediaRecorder(stream,{mimeType:'video/webm'});
      const done=new Promise(resolve => recorder.onstop=resolve);
      recorder.ondataavailable=event=>chunks.push(event.data);
      recorder.start();
      const context=canvas.getContext('2d');
      for(let frame=0;frame<10;frame++){
        context.fillStyle=frame%2?'#155bd9':'#ffffff';context.fillRect(0,0,16,16);
        await new Promise(resolve=>setTimeout(resolve,100));
      }
      recorder.stop();await done;stream.getTracks().forEach(track=>track.stop());
      const data=await new Blob(chunks,{type:'video/webm'}).arrayBuffer();
      return btoa(String.fromCharCode(...new Uint8Array(data)));
    }""")
    page.get_by_role("button", name="+ Add content", exact=True).click()
    form = page.get_by_role("dialog", name="Add content", exact=True)
    form.get_by_label("Content name *", exact=True).fill("Video journey")
    form.get_by_label("Description *", exact=True).fill("Recorded local test video")
    form.get_by_label("Content type *", exact=True).select_option("Training Video")
    form.locator("input[type=file]").set_input_files({"name": "journey.webm", "mimeType": "video/webm", "buffer": base64.b64decode(video)})
    form.get_by_role("button", name="Add content", exact=True).click()
    page.get_by_role("button", name="Open", exact=True).click()
    player = page.get_by_role("dialog", name="Video journey").locator("video")
    expect(player).to_be_visible()
    page.wait_for_function("document.querySelector('.knowledge-preview video').readyState >= 2")
    player.evaluate("video => video.play()")
    page.wait_for_function("document.querySelector('.knowledge-preview video').currentTime > 0")
    page.close()
    unavailable = browser_context.new_page()
    unavailable.add_init_script("Object.defineProperty(window, 'indexedDB', {value: undefined});")
    unavailable.goto(module_portal_url)
    unavailable.get_by_role("button", name="Knowledge Center", exact=True).click()
    expect(unavailable.get_by_role("button", name="+ Add content", exact=True)).to_be_enabled()
    expect(unavailable.locator(".knowledge-card")).to_contain_text("Video journey")
    expect(unavailable.get_by_role("button", name="Copy browser library", exact=True)).to_have_count(0)
    add_content(unavailable, "No browser storage required")
    unavailable.reload()
    unavailable.get_by_role("button", name="Knowledge Center", exact=True).click()
    expect(unavailable.locator(".knowledge-card").filter(has_text="No browser storage required")).to_have_count(1)
    unavailable.close()


def test_knowledge_server_replacement_preserves_unrelated_legacy_browser_files(module_portal_url, browser_context):
    page = browser_context.new_page()
    page.goto(module_portal_url)
    page.evaluate("""async () => {
      const db=await new Promise((resolve,reject)=>{
        const request=indexedDB.open('itom-knowledge-files-v1',1);
        request.onupgradeneeded=()=>request.result.createObjectStore('files');
        request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
      });
      await new Promise((resolve,reject)=>{
        const tx=db.transaction('files','readwrite');
        tx.objectStore('files').put(new File(['reference instructions'],'reference.txt',{type:'text/plain'}),'reference-file');
        tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);
      });db.close();
      localStorage.setItem('itom-knowledge-centre-v1',JSON.stringify([{
        id:'reference',serial:9,name:'Reference guide',description:'Stored by the VM branch',category:'Runbook',
        file:{name:'reference.txt',type:'text/plain',size:22,storageId:'reference-file'},validatedOn:null,validatedBy:''
      }]));
    }""")
    page.get_by_role("button", name="Knowledge Center", exact=True).click()
    expect(page.locator(".knowledge-card")).to_have_count(0)
    expect(page.get_by_role("button", name="Copy browser library", exact=True)).to_have_count(0)
    add_content(page, "Reference guide")
    expect(page.locator(".knowledge-card")).to_have_count(1)
    page.get_by_role("button", name="Open", exact=True).click()
    details = page.get_by_role("dialog", name="Reference guide", exact=True)
    expect(details.get_by_role("button", name="View file", exact=True)).to_have_count(0)
    expect(details).to_contain_text("Download only")
    details.get_by_role("button", name="Close", exact=True).click()
    page.get_by_role("button", name="Edit", exact=True).click()
    form = page.get_by_role("dialog", name="Edit content", exact=True)
    form.locator("input[type=file]").set_input_files({"name": "replacement.txt", "mimeType": "text/plain", "buffer": b"Replacement instructions"})
    form.get_by_label("CMDB admin key", exact=True).fill("isolated-review-key")
    form.get_by_role("button", name="Save changes", exact=True).click()
    expect(form).not_to_be_visible()
    page.reload()
    page.get_by_role("button", name="Knowledge Center", exact=True).click()
    expect(page.locator(".knowledge-card")).to_contain_text("replacement.txt")
    page.get_by_role("button", name="Open", exact=True).click()
    expect(details.get_by_role("button", name="View file", exact=True)).to_have_count(0)
    with page.expect_download() as downloaded:
        details.get_by_role("link", name="Download file", exact=True).click()
    assert Path(downloaded.value.path()).read_bytes() == b"Replacement instructions"
    assert page.evaluate("""async () => {
      const db=await new Promise(resolve=>{const request=indexedDB.open('itom-knowledge-files-v1',2);request.onsuccess=()=>resolve(request.result)});
      const value=await new Promise(resolve=>{const request=db.transaction('files').objectStore('files').get('reference-file');request.onsuccess=()=>resolve(request.result)});
      db.close();return value instanceof Blob && await value.text()==='reference instructions';
    }""")
    page.close()
