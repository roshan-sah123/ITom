import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPortalModel,
  donutGradient,
  donutSlice,
  csvText,
  buildOperationsCharts,
} from "../src/data.ts";

test("operations charts use the selected source category and keep its inventory filters", () => {
  const snapshot = { solarwinds: { metrics: { total_nodes: 5 }, health_breakdown: { High: 3, Low: 2 }, status_breakdown: { Up: 3, Down: 2 },
    source_categories: [{ value: "Telecom", count: 2, health_counts: { High: 1, Low: 1 }, status_counts: { Up: 1, Down: 1 } }] } };
  const result = buildOperationsCharts(snapshot, "Telecom");
  assert.equal(result.chartCenter, "2");
  assert.equal(result.chartLegend.find((row) => row.label === "Low")?.value, "1");
  assert.deepEqual(result.bars.find((row) => row.label === "Down")?.action?.filters, { category: "Telecom", status: "Down" });
  const missing = buildOperationsCharts(snapshot, "Network");
  assert.equal(missing.chartCenter, "0");
  assert.deepEqual(missing.chartLegend, []);
  const total = buildOperationsCharts(snapshot, "Total Nodes");
  assert.equal(total.chartCenter, "5");
  const location = buildOperationsCharts({ geographicScores: { items: [
    { id: "a", name: "A", endpoints: 2, match_level: "city", scores: { combined: { value: 80, status: "critical" } } },
    { id: "b", name: "B", endpoints: 2, match_level: "country", scores: { combined: { value: null, status: "unavailable" } } },
  ] } }, "Location");
  assert.equal(location.chartCenter, "2");
  assert.equal(location.chartLegend.find((row) => row.label === "critical")?.value, "1");
  assert.equal(location.bars.find((row) => row.label === "country")?.display, "1");
});
import { scorePriority, componentEvidence } from "../src/locationScoreData.ts";

test("ticket guidance follows the backend combined status and preserves component evidence", () => {
  assert.equal(scorePriority("combined", { value: 84.3, status: "critical" }), "P1");
  assert.equal(scorePriority("combined", { value: 91, status: "warning" }), "P2");
  assert.equal(scorePriority("combined", { value: null, status: "critical" }), "—");
  assert.equal(scorePriority("infrastructure", { value: 20, status: "critical" }), "—");
  assert.equal(componentEvidence({ value: 73.54, numerator: 1009, denominator: 1372, usable: true }), "73.54% (1009 / 1372)");
  assert.equal(componentEvidence({ value: 90, usable: false, reason: "Source data is stale or unavailable" }), "Unavailable: Source data is stale or unavailable");
});

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

test("site scores retain their policy status and monitored-node denominator", () => {
  const model = buildPortalModel({
    groups: {
      data_available: true,
      items: [
        {
          group: { group_id: 35, name: "Fenchurch", status: "Up" },
          total_devices: 19,
          server_count: 8,
          network_count: 9,
          site_score: { value: 94.4, status: "warning" },
          status_breakdown: { Up: 17, Warning: 1, Unmanaged: 1 },
          components: {
            node_status: { value: 94.44, denominator: 18, usable: true },
          },
        },
      ],
    },
  });
  assert.equal(model.locations[0].status, "Up");
  assert.equal(model.locations[0].scoreStatus, "Warning");
  assert.equal(model.locations[0].monitored, 18);
  assert.equal(model.locations[0].availability, "94.44%");
  assert.equal(model.siteRows[0].availability, model.locations[0].availability);
});

test("combined location scores retain approved mapping, components and unavailable reasons", () => {
  const group = {
    group: { group_id: 7, name: "Site", status: "Up" }, total_devices: 2,
    server_count: 1, network_count: 1, status_breakdown: { Up: 2 },
    site_score: { value: null, status: "unavailable", reason: "An explicit approved Intune location link is required" },
    mapping: { status: "UNMAPPED", location_name: null }, intune_endpoints: 0,
    components: { node_status: { value: 100, denominator: 2, usable: true } },
  };
  const model = buildPortalModel({ combinedGroups: { data_available: true, items: [group] } });
  assert.equal(model.combinedLocations[0].scoreStatus, "Unavailable");
  assert.equal(model.combinedLocations[0].scoreReason, group.site_score.reason);
  assert.equal(model.combinedLocations[0].mappingStatus, "UNMAPPED");
  assert.equal(model.combinedLocations[0].availability, "100%");
});

test("Intune location scores retain endpoint scope and backend status", () => {
  const model = buildPortalModel({ locations: { items: [
    { id: "city", name: "City", endpoints: 4, scores: { endpoints: { value: 88, status: "warning", reason: null } } },
    { id: "unassigned", name: "Unassigned", endpoints: 2, scores: { endpoints: { value: null, status: "unavailable", reason: "Unassigned location" } } },
  ] } });
  assert.equal(model.intuneLocations[0].score, 88);
  assert.equal(model.intuneLocations[0].scoreStatus, "Warning");
  assert.equal(model.intuneLocations[1].scoreReason, "Unassigned location");
});

test("canonical location scores preserve both sources and combined policy status", () => {
  const model = buildPortalModel({ locations: { items: [{ id: "site", name: "Site", endpoints: 100, nodes: 10,
    scores: { combined: { value: 84.3, status: "critical", reason: "A component is below 75%" } },
    components: { compliance: { value: 82.43, usable: true }, node_status: { value: 94.05, usable: true }, recent_checkins: { value: 73.54, usable: true } },
  }] } });
  assert.equal(model.locationScores[0].scores.combined?.value, 84.3);
  assert.equal(model.locationScores[0].scores.combined?.status, "critical");
  assert.equal(model.locationScores[0].nodes, 10);
  assert.equal(model.locationScores[0].components?.recent_checkins?.value, 73.54);
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
  assert.deepEqual(config.metrics.map((row) => row.label), ["Location", "Total Nodes", "Network", "Servers", "Telecom"]);
  assert.equal(config.metrics[0].action?.target, "groups");
  assert.deepEqual(config.metrics[2].action?.filters, { category: "Network" });
  assert.deepEqual(config.metrics[3].action?.filters, { category: "SERVER" });
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

test("snapshot requests publish results independently and isolate failures", async () => {
  const { loadSnapshotRoutes } = await import("../src/snapshot.ts");
  let resolveSlow: (value: unknown) => void = () => {};
  const slow = new Promise((resolve) => { resolveSlow = resolve; });
  const events: string[] = [];
  const done = loadSnapshotRoutes({ fast: "/fast", slow: "/slow", failed: "/failed" },
    (route) => route === "/fast" ? Promise.resolve({ value: 7 }) : route === "/slow" ? slow : Promise.reject(new Error("offline")),
    (key, value, error) => events.push(`${key}:${error ? "error" : JSON.stringify(value)}`));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.ok(events.includes('fast:{"value":7}'));
  assert.ok(events.includes('failed:error'));
  assert.equal(events.some((event) => event.startsWith('slow:')), false);
  resolveSlow({ value: 0 });
  await done;
  assert.ok(events.includes('slow:{"value":0}'));
});
