import test from "node:test";
import assert from "node:assert/strict";
import {
  missingNetworkWorkbookColumns,
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
  assert.equal(assetCellDisplay("server", "EOL", "2032-03-21T00:00:00"), "2032-03-21T00:00:00");
  assert.equal(assetCellDisplay("network", "Other", "2032-03-21T00:00:00"), "2032-03-21T00:00:00");
});


test("network AMC end date and workbook validation date omit time in the table", () => {
  assert.equal(assetCellDisplay("network", "AMC END DATE", "2029-10-30T00:00:00"), "2029-10-30");
  assert.equal(assetCellDisplay("network", "Validated on", "2026-11-05T00:00:00"), "2026-11-05");
  assert.equal(assetCellDisplay("network", "AMC END DATE", "Not announced"), "Not announced");
});

test("network workbook fields missing from the stored schema appear as unavailable columns", () => {
  assert.deepEqual(missingNetworkWorkbookColumns("network", ["REGION", "SITE", "PROVIDER"]), ["Country", "Make", "Firmware/IOS Version", "Login Status"]);
  assert.deepEqual(missingNetworkWorkbookColumns("network", ["Country", "Make", "Firmware/IOS Version", "Login Status"]), []);
  assert.deepEqual(missingNetworkWorkbookColumns("server", []), []);
});


test("network portal review status uses verified wording", () => {
  assert.equal(assetReviewLabel("network", true), "Verified");
  assert.equal(assetReviewLabel("network", false), "Pending");
  assert.equal(assetReviewLabel("server", true), "Validated");
});
