import test from "node:test";
import assert from "node:assert/strict";
import { knowledgeSummary, filterKnowledge, validateKnowledgeDraft, validateKnowledgeFile } from "../src/knowledge.ts";

test("knowledge counts and filters come only from persisted records", () => {
  const rows = [
    { name: "Router guide", description: "Configure routing", category: "Runbook", file: { name: "guide.txt" }, validatedOn: "2026-10-01" },
    { name: "Training", description: "Onboarding", category: "Training Video", file: { name: "training.mp4" }, validatedOn: null },
  ];
  assert.deepEqual(knowledgeSummary(rows), { total: 2, validated: 1, pending: 1 });
  assert.equal(filterKnowledge(rows, "GUIDE.TXT", "Validated").length, 1);
  assert.equal(filterKnowledge(rows, "Onboarding", "Pending").length, 1);
  assert.deepEqual(knowledgeSummary([]), { total: 0, validated: 0, pending: 0 });
});

test("knowledge content requires description and category, without editor validation metadata", () => {
  const draft = { name: "Guide", description: "Instructions", category: "SOP" };
  assert.doesNotThrow(() => validateKnowledgeDraft(draft));
  assert.throws(() => validateKnowledgeDraft({ ...draft, category: "" }));
  assert.throws(() => validateKnowledgeDraft({ ...draft, description: "" }));
});

test("knowledge accepts any non-empty file type and enforces the exact 5 MiB limit", () => {
  for (const [name, type] of [["guide.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"], ["training.mp4", "video/mp4"], ["sheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"], ["slides.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"]]) {
    assert.equal(validateKnowledgeFile({ name, type, size: 5 * 1024 * 1024 }), "application/octet-stream");
  }
  assert.equal(validateKnowledgeFile({ name: "payload.exe", type: "application/x-msdownload", size: 100 }), "application/octet-stream");
  assert.equal(validateKnowledgeFile({ name: "extensionless", type: "", size: 100 }), "application/octet-stream");
  assert.throws(() => validateKnowledgeFile({ name: "guide.txt", type: "text/plain", size: 5 * 1024 * 1024 + 1 }));
  assert.throws(() => validateKnowledgeFile({ name: "empty.bin", type: "application/octet-stream", size: 0 }));
});
