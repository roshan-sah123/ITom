import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPortalModel,
  donutGradient,
  donutSlice,
  csvText,
} from "../src/data.ts";

test("unavailable sources never become zero fleets or fresh snapshots", () => {
  const model = buildPortalModel({});
  assert.equal(model.kpis[0].value, "—");
  assert.equal(model.freshness, "UNAVAILABLE");
  assert.deepEqual(model.locations, []);
  assert.deepEqual(model.workspaceConfigs["Digital Workspace"].chartLegend, []);
});

test("uses API counts and preserves stale group scores and exact source names", () => {
  const model = buildPortalModel({
    intune: {
      metrics: {
        total_managed_devices: 12,
        compliant_devices: 9,
        noncompliant_devices: 2,
      },
      os_distribution: { Windows: 10, macOS: 2 },
    },
    solarwinds: {
      metrics: {
        total_nodes: 7,
        available_nodes: 5,
        server_nodes_count: 3,
        network_devices_count: 4,
      },
      status_breakdown: { Up: 5, Warning: 1, Unmanaged: 1 },
    },
    cmdb: { data_available: true, total_cis: 19 },
    freshness: { overall_status: "STALE", sources: {} },
    groups: {
      data_available: true,
      items: [
        {
          group: {
            group_id: 42,
            name: "India - Exact Source Group",
            status: "Warning",
          },
          total_devices: 7,
          server_count: 3,
          network_count: 4,
          site_score: {
            value: null,
            reason: "Source data is stale or unavailable",
          },
          status_breakdown: { Up: 5, Warning: 1, Unmanaged: 1 },
          components: { node_status: { value: 83.33, usable: false } },
        },
      ],
    },
  });
  assert.equal(model.kpis[0].value, "12");
  assert.equal(model.kpis[1].value, "7");
  assert.equal(model.freshness, "STALE");
  assert.equal(model.locations[0].score, null);
  assert.equal(model.locations[0].name, "India - Exact Source Group");
  assert.equal(model.siteRows[0].availability, "—");
  assert.equal(model.locations[0].servers, 3);
  assert.equal(model.locations[0].total, 7);
  assert.equal(
    model.workspaceConfigs["Digital Workspace"].chartLegend[0].value,
    "10",
  );
});

test("successful empty group snapshots remain distinct from unavailable groups", () => {
  const model = buildPortalModel({
    groups: { data_available: true, items: [] },
  });
  assert.equal(model.groupsAvailable, true);
  assert.deepEqual(model.siteRows, []);
});

test("donut segments use actual proportions including zero and missing data", () => {
  assert.equal(donutGradient([]), "#e3e9f2");
  assert.equal(
    donutGradient([{ label: "Empty", value: "0", tone: "blue" }]),
    "#e3e9f2",
  );
  assert.match(
    donutGradient([
      { label: "A", value: "3", tone: "blue" },
      { label: "B", value: "1", tone: "green" },
    ]),
    /75%/,
  );
});

test("donut hit testing follows live proportions and ignores empty segments", () => {
  const rows = [
    { label: "High", value: "3", tone: "green" },
    { label: "Empty", value: "0", tone: "slate" },
    { label: "Low", value: "1", tone: "red" },
  ];
  assert.equal(donutSlice(rows, 0.1)?.label, "High");
  assert.equal(donutSlice(rows, 0.8)?.label, "Low");
  assert.equal(donutSlice(rows, -0.2)?.label, "Low");
  assert.equal(donutSlice([], 0.5), undefined);
});

test("CSV quotes content and neutralizes spreadsheet formula injection", () => {
  const csv = csvText(
    ["Name", "Vendor"],
    [
      ['=HYPERLINK("bad")', "A,B"],
      ["normal\nname", "+formula"],
    ],
  );
  assert.ok(csv.includes('"\'=HYPERLINK(""bad"")"'));
  assert.ok(csv.includes('"A,B"'));
  assert.ok(csv.includes('"\'+formula"'));
});

test("summary and chart drill-downs preserve native filter values", () => {
  const model = buildPortalModel({
    solarwinds: {
      metrics: {
        total_nodes: 8,
        server_nodes_count: 5,
        network_devices_count: 3,
        low_critical_nodes: 2,
      },
      source_categories: [
        { value: "SERVER", count: 5 },
        { value: "Network", count: 3 },
      ],
      health_breakdown: { High: 6, Low: 2 },
      status_breakdown: { Up: 7, Critical: 1 },
    },
  });
  const config = model.workspaceConfigs["Operations Analytics"];
  assert.deepEqual(config.metrics[0].action?.filters, { category: "SERVER" });
  assert.deepEqual(config.metrics[1].action?.filters, { category: "Network" });
  assert.equal(config.metrics[2].action?.target, "groups");
  assert.deepEqual(config.metrics[3].action?.filters, { health_tier: "Low" });
  assert.deepEqual(
    config.chartLegend.find((row) => row.label === "Low")?.action?.filters,
    { health_tier: "Low" },
  );
  assert.deepEqual(
    config.bars.find((row) => row.label === "Critical")?.action?.filters,
    { status: "Critical" },
  );
});

test("source counts and health distributions never invent fixed values", () => {
  const model = buildPortalModel({
    cmdb: {
      data_available: true,
      total_cis: 13,
      source_breakdown: { INTUNE: 8, SOLARWINDS: 4, OTHER: 1 },
    },
  });
  const config = model.workspaceConfigs["Assets Analytics"];
  assert.equal(config.metrics[3].value, "3");
  assert.equal(
    config.chartLegend.find((row) => row.label === "OTHER")?.value,
    "1",
  );
  assert.deepEqual(
    config.chartLegend.find((row) => row.label === "OTHER")?.action?.filters,
    { source_system: "OTHER" },
  );
  assert.deepEqual(config.bars, []);
});
