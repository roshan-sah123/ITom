import test from "node:test";
import assert from "node:assert/strict";
import {
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
