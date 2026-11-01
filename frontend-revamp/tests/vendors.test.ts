import test from "node:test";
import assert from "node:assert/strict";
import { validateVendorDraft, vendorSubmissionBody } from "../src/vendors.ts";

test("submit validates numbered steps before asking about an optional SOP", () => {
  assert.throws(() => validateVendorDraft({ vendor: "", method: "Portal", steps: [] }));
  assert.throws(() => validateVendorDraft({
    vendor: "Example", method: "Portal", steps: [{ what_to_do: "Open", how_to_do: "" }],
  }));
  const draft = { vendor: "Example", method: "Portal", steps: [{ what_to_do: "Open", how_to_do: "Sign in" }] };
  assert.doesNotThrow(() => validateVendorDraft(draft));
  assert.equal(vendorSubmissionBody(draft, "a".repeat(32), null).sop, null);
  assert.equal(vendorSubmissionBody(draft, "a".repeat(32), null).steps.length, 1);
});
