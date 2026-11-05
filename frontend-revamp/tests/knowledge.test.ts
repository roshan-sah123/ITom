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

test("knowledge allows only viewable documents and supported videos at the exact 5 MiB limit", () => {
  for (const name of ["guide.docx", "guide.PDF", "slides.pptx", "guide.txt", "training.mp4", "training.webm", "training.mov"]) {
    assert.equal(validateKnowledgeFile({ name, type: "", size: 5 * 1024 * 1024 }), "application/octet-stream");
  }
  for (const name of ["sheet.xlsx", "sheet.xls", "sheet.csv", "payload.exe", "extensionless", "image.png", "page.html", "movie.avi", "guide.docx.exe"]) {
    assert.throws(() => validateKnowledgeFile({ name, type: "application/pdf", size: 100 }), /DOCX, PDF, PPTX, TXT/);
  }
  assert.throws(() => validateKnowledgeFile({ name: "guide.txt", type: "text/plain", size: 5 * 1024 * 1024 + 1 }));
  assert.throws(() => validateKnowledgeFile({ name: "empty.bin", type: "application/octet-stream", size: 0 }));
});
