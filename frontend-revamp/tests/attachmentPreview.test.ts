import test from "node:test";
import assert from "node:assert/strict";
import { attachmentViewUrl, previewEndpoint, previewText } from "../src/attachmentPreview.ts";

test("viewer URLs remain local and accept only stored module attachments", () => {
  const path = "/api/v1/knowledge/content/12/file";
  assert.equal(previewEndpoint(path), `${path}?preview=true`);
  assert.equal(previewEndpoint("/api/v1/vendors/submissions/7/sop"), "/api/v1/vendors/submissions/7/sop?preview=true");
  const url = new URL(attachmentViewUrl(path, "guide & notes.docx"), "http://localhost:5173");
  assert.equal(url.searchParams.get("name"), "guide & notes.docx");
  for (const invalid of ["https://example.com/doc", "//example.com", "/api/v1/sync", "/api/v1/knowledge/content/1/file?view=true"])
    assert.throws(() => previewEndpoint(invalid));
});

test("text previews decode UTF-8 and UTF-16 without interpreting markup", () => {
  assert.equal(previewText(new TextEncoder().encode("<script>not executable</script>")), "<script>not executable</script>");
  assert.equal(previewText(new Uint8Array([255, 254, 84, 0])), "T");
});
