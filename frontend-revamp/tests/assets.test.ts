import test from "node:test";
import assert from "node:assert/strict";
import {
  assetImportLabel,
  assetReviewLabel,
  assetCellDisplay,
  assetCount,
  assetExportRows,
  assetWorkbookSources,
  editedAssetValue,
} from "../src/assets.ts";

test("asset summary tiles are limited to the three workbook inventories", () => {
  assert.deepEqual(
    assetWorkbookSources.map((source) => source.category),
    ["server", "network", "telecom"],
  );
});

test("CMDB editing preserves unchanged primitive types and explicit empty values", () => {
  assert.equal(editedAssetValue(42, "43"), 43);
  assert.equal(editedAssetValue(true, "false"), false);
  assert.equal(editedAssetValue("00123", "00123"), "00123");
  assert.equal(editedAssetValue(null, ""), null);
  assert.equal(editedAssetValue(42, "not numeric"), "not numeric");
  assert.equal(editedAssetValue(42, "Infinity"), "Infinity");
});

test("unavailable asset sources are not reported as empty inventories", () => {
  assert.equal(assetCount({ data_available: false, total: null }), "—");
  assert.equal(assetCount({ data_available: true, total: 0 }), "0");
  assert.equal(assetCount({ data_available: true, total: 1732 }), "1,732");
});

test("asset CSV rows follow workbook column order and preserve empty cells", () => {
  const rows = assetExportRows({
    category: "server",
    columns: ["Host name", "Status"],
    items: [{ "Host name": "srv-01", Status: null }],
    total: 1,
    page: 1,
    page_size: 25,
    total_pages: 1,
  });
  assert.deepEqual(rows, [["srv-01", ""]]);
});

test("network EOL dates display without timestamps and preserve other values", () => {
  assert.equal(assetCellDisplay("network", "EOL", "2032-03-21T00:00:00"), "2032-03-21");
  assert.equal(assetCellDisplay("network", "EOL Date", "2032-03-21 12:30:00"), "2032-03-21");
  assert.equal(assetCellDisplay("network", "EOL", "Not Announced"), "Not Announced");
  assert.equal(assetCellDisplay("network", "EOL", null), "—");
  assert.equal(assetCellDisplay("server", "EOL", "2032-03-21T00:00:00"), "2032-03-21");
  assert.equal(assetCellDisplay("server", "AMC START DATE", "2024-08-31T00:00:00"), "2024-08-31");
  assert.equal(assetCellDisplay("server", "WORKBOOK VALIDATED ON", "2026-11-13T00:00:00"), "2026-11-13");
  assert.equal(assetCellDisplay("server", "AMC START DATE", "Azure"), "Azure");
  assert.equal(assetCellDisplay("server", "HOST NAME", "2032-03-21T00:00:00"), "2032-03-21T00:00:00");
  assert.equal(assetCellDisplay("telecom", "AMC End Date", "2026-12-31T00:00:00"), "2026-12-31");
  assert.equal(assetCellDisplay("telecom", "AMC Status", "2025-11-26T00:00:00"), "2025-11-26");
  assert.equal(assetCellDisplay("telecom", "Circuit ID", "2026-12-31T00:00:00"), "2026-12-31T00:00:00");
  assert.equal(assetCellDisplay("network", "Other", "2032-03-21T00:00:00"), "2032-03-21T00:00:00");
});


test("network AMC end date and workbook validation date omit time in the table", () => {
  assert.equal(assetCellDisplay("network", "AMC END DATE", "2029-10-30T00:00:00"), "2029-10-30");
  assert.equal(assetCellDisplay("network", "Validated on", "2026-11-05T00:00:00"), "2026-11-05");
  assert.equal(assetCellDisplay("network", "WORKBOOK VALIDATED ON", "2026-11-22T00:00:00"), "2026-11-22");
  assert.equal(assetCellDisplay("network", "AMC END DATE", "Not announced"), "Not announced");
});

test("asset tiles describe the latest persisted workbook import only when one exists", () => {
  const base = { category: "server" as const, label: "Servers", data_available: true, total: 721 };
  assert.equal(
    assetImportLabel({ ...base, last_import: { at: "2026-11-16T14:34:07+00:00", updated: 571, added: 125 } }),
    "Excel update 16 Nov 2026 · 571 updated · 125 added",
  );
  assert.equal(assetImportLabel({ ...base, last_import: null }), null);
  assert.equal(assetImportLabel(base), null);
  assert.equal(assetImportLabel({ ...base, last_import: { at: "not a date", updated: 1, added: 0 } }), null);
});


test("network portal review status uses verified wording", () => {
  assert.equal(assetReviewLabel("network", true), "Verified");
  assert.equal(assetReviewLabel("network", false), "Pending");
  assert.equal(assetReviewLabel("server", true), "Validated");
});
