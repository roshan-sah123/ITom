export type IconName =
  | "search"
  | "refresh"
  | "chevron"
  | "server"
  | "monitor"
  | "database"
  | "activity"
  | "map"
  | "alert"
  | "check"
  | "clock"
  | "external";
type Counts = Record<string, number>;
type Metric = {
  value?: number | null;
  numerator?: number;
  denominator?: number;
  usable?: boolean;
  definition?: string;
};
export type Summary = {
  metrics?: Counts;
  total_cis?: number;
  data_available?: boolean;
  source_counts?: Counts;
  source_breakdown?: Counts;
  high_health_count?: number;
  medium_health_count?: number;
  low_health_count?: number;
  status_breakdown?: Counts;
  health_breakdown?: Counts;
  os_distribution?: Counts;
  source_categories?: Array<{ value: string | null; count: number }>;
  decision_metrics?: {
    confirmed_compliance?: Metric;
    current_node_status?: Metric;
    resource_pressure?: Metric;
  };
};
export type Group = {
  group: { group_id: number; name: string; status: string };
  total_devices: number;
  server_count: number;
  network_count: number;
  site_score: { value: number | null; status?: string; reason?: string };
  status_breakdown: Counts;
  components?: { node_status?: Metric };
};
export type Freshness = {
  overall_status?: string;
  oldest_age_seconds?: number;
  sources?: Record<
    string,
    { status?: string; last_synchronized_at?: string; age_seconds?: number }
  >;
};
export type Snapshot = {
  intune?: Summary;
  solarwinds?: Summary;
  cmdb?: Summary;
  freshness?: Freshness;
  groups?: { data_available: boolean; items: Group[]; as_of?: string };
  locations?: { items: Array<{ id: string; name: string; endpoints: number }> };
};
export type InventoryFilters = {
  status?: string;
  health_tier?: string;
  category?: string;
  category_missing?: boolean;
  source_system?: string;
  ci_type?: string;
  resource_pressure?: boolean;
};
export type Drilldown = {
  label: string;
  filters?: InventoryFilters;
  target?: "groups" | "chart";
  groupId?: number;
};
export type Legend = {
  label: string;
  value: string;
  tone: string;
  action?: Drilldown;
};
export type WorkspaceConfig = {
  eyebrow: string;
  title: string;
  description: string;
  metrics: Array<{
    label: string;
    value: string;
    meta: string;
    icon: IconName;
    tone: string;
    action?: Drilldown;
  }>;
  chartTitle: string;
  chartCenter: string;
  chartLegend: Legend[];
  barsTitle: string;
  bars: Array<{
    label: string;
    value: number;
    display: string;
    tone: string;
    action?: Drilldown;
  }>;
  tableTitle: string;
  searchPlaceholder: string;
  columns: string[];
  endpoint?: string;
  unavailable?: string;
  statuses?: string[];
  categories?: Array<{ value: string | null; count: number }>;
  sources?: Array<{ value: string; label: string }>;
};
export const number = (value?: number | null): string =>
  Number.isFinite(value) ? value!.toLocaleString("en-US") : "—";
export const percent = (value?: number | null): string =>
  Number.isFinite(value)
    ? `${value!.toLocaleString("en-US", { maximumFractionDigits: 2 })}%`
    : "—";
export function time(value?: string): string {
  if (!value) return "No successful sync";
  const normalized = /T\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(value)
    ? `${value}Z`
    : value;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime())
    ? "Unknown time"
    : parsed.toLocaleString("en-IN", {
        timeZone: "Asia/Kolkata",
        dateStyle: "medium",
        timeStyle: "short",
      });
}
const tones = ["blue", "green", "amber", "purple", "red", "slate"];
function legend(counts?: Counts, filter?: keyof InventoryFilters): Legend[] {
  const semantic: Record<string, string> = {
    High: "green",
    Medium: "amber",
    Low: "red",
    Up: "green",
    Warning: "amber",
    Critical: "red",
    Down: "red",
    Unmanaged: "slate",
    Unknown: "slate",
    Compliant: "green",
    NonCompliant: "red",
    InGracePeriod: "amber",
    ConfigManager: "blue",
  };
  return Object.entries(counts ?? {}).map(([label, value], i) => ({
    label,
    value: number(value),
    tone: semantic[label] ?? tones[i % tones.length],
    ...(filter ? { action: { label, filters: { [filter]: label } } } : {}),
  }));
}
function bars(counts?: Counts, filter?: keyof InventoryFilters) {
  const total = Object.values(counts ?? {}).reduce(
    (sum, value) => sum + value,
    0,
  );
  return legend(counts, filter).map((item) => ({
    ...item,
    display: item.value,
    value: total ? (counts![item.label] / total) * 100 : 0,
  }));
}
function metric(
  label: string,
  value: number | undefined | null,
  meta: string,
  icon: IconName,
  tone: string,
  action?: Drilldown,
) {
  return { label, value: number(value), meta, icon, tone, action };
}

export function ageLabel(seconds?: number) {
  if (!Number.isFinite(seconds)) return "Unknown age";
  if (seconds! < 60) return "Just synchronized";
  if (seconds! < 3600) return `${Math.floor(seconds! / 60)}m old`;
  return `${Math.floor(seconds! / 3600)}h ${Math.floor((seconds! % 3600) / 60)}m old`;
}

export function buildPortalModel(snapshot: Snapshot) {
  const im = snapshot.intune?.metrics,
    sm = snapshot.solarwinds?.metrics;
  const cmdb =
    snapshot.cmdb?.data_available === false ? undefined : snapshot.cmdb;
  const sourceCounts =
    cmdb?.source_breakdown ??
    (cmdb &&
    im &&
    sm &&
    Number.isFinite(im.total_managed_devices) &&
    Number.isFinite(sm.total_nodes)
      ? { INTUNE: im.total_managed_devices, SOLARWINDS: sm.total_nodes }
      : undefined);
  const sourceEntries = sourceCounts
    ? Object.entries(sourceCounts).filter(([, count]) => count > 0)
    : undefined;
  const sourceNames: Record<string, string> = {
    INTUNE: "Microsoft Intune",
    SOLARWINDS: "SolarWinds Orion",
  };
  const sourceChart =
    sourceEntries?.map(([source, count], index) => ({
      label: sourceNames[source] ?? source,
      value: number(count),
      tone: tones[index % tones.length],
      action: {
        label: sourceNames[source] ?? source,
        filters: { source_system: source },
      },
    })) ?? [];
  const category = (name: string) =>
    snapshot.solarwinds?.source_categories?.find(
      (row) => row.value?.toLowerCase() === name.toLowerCase(),
    )?.value ?? name;
  const groupsAvailable = snapshot.groups?.data_available === true;
  const groups = groupsAvailable ? snapshot.groups!.items : [];
  const locations = groups.map((row) => ({
    id: row.group.group_id,
    name: row.group.name,
    servers: row.server_count,
    network: row.network_count,
    total: row.total_devices,
    score: row.site_score.value,
    scoreStatus:
      row.site_score.value == null
        ? "Unavailable"
        : ({ healthy: "Healthy", warning: "Warning", critical: "Critical" } as Record<string, string>)[
            row.site_score.status ?? ""
          ] ?? "Unknown",
    scoreReason: row.site_score.reason ?? "Backend Site Score",
    healthy: row.status_breakdown.Up ?? 0,
    warning: row.status_breakdown.Warning ?? 0,
    critical:
      (row.status_breakdown.Critical ?? 0) + (row.status_breakdown.Down ?? 0),
    status: row.group.status,
    monitored: row.components?.node_status?.denominator,
    availabilityValue: row.components?.node_status?.usable
      ? (row.components.node_status.value ?? null)
      : null,
    availability: row.components?.node_status?.usable
      ? percent(row.components.node_status.value)
      : "—",
  }));
  const swFreshness = snapshot.freshness?.sources?.SOLARWINDS;
  const siteRows = locations.map((row) => ({
    ...row,
    site: row.name,
    region: "SolarWinds regular group",
    updated: time(snapshot.groups?.as_of ?? swFreshness?.last_synchronized_at),
  }));
  const needsAttention = groupsAvailable
    ? groups.filter((row) =>
        ["warning", "critical", "down"].includes(
          row.group.status.toLowerCase(),
        ),
      ).length
    : undefined;
  const freshness =
    !im || !sm || !cmdb || !snapshot.freshness
      ? "UNAVAILABLE"
      : (snapshot.freshness.overall_status ?? "UNKNOWN");
  const kpis = [
    {
      ...metric(
        "Managed endpoints",
        im?.total_managed_devices,
        `${number(im?.compliant_devices)} compliant`,
        "monitor",
        "blue",
      ),
      trend: percent(
        snapshot.intune?.decision_metrics?.confirmed_compliance?.value,
      ),
    },
    {
      ...metric(
        "SolarWinds nodes",
        sm?.total_nodes,
        `${number(sm?.available_nodes)} reporting up`,
        "server",
        "green",
      ),
      trend: percent(
        snapshot.solarwinds?.decision_metrics?.current_node_status?.value,
      ),
    },
    {
      ...metric(
        "Configuration items",
        cmdb?.total_cis,
        "Persisted source records",
        "database",
        "purple",
      ),
      trend: "Snapshot",
    },
    {
      ...metric(
        "Groups requiring attention",
        needsAttention,
        `${groupsAvailable ? groups.length : "—"} regular groups · may overlap`,
        "activity",
        "orange",
      ),
      trend: "Native status",
    },
  ];
  const workspaceConfigs: Record<string, WorkspaceConfig> = {
    "Operations Analytics": {
      eyebrow: "SOLARWINDS OPERATIONS",
      title: "Infrastructure intelligence",
      description:
        "Monitor node health, network capacity, and server performance across every location.",
      metrics: [
        metric(
          "Classified servers",
          sm?.server_nodes_count,
          `of ${number(sm?.total_nodes)} SolarWinds nodes`,
          "server",
          "blue",
          {
            label: "Classified servers",
            filters: { category: category("Server") },
          },
        ),
        metric(
          "Network infrastructure",
          sm?.network_devices_count,
          "SolarWinds node inventory",
          "activity",
          "green",
          {
            label: "Network infrastructure",
            filters: { category: category("Network") },
          },
        ),
        metric(
          "Location health",
          groupsAvailable ? groups.length : undefined,
          "Regular groups · mixed levels",
          "map",
          "purple",
          { label: "Location health", target: "groups" },
        ),
        metric(
          "Nodes needing attention",
          sm?.low_critical_nodes,
          "Low health classification",
          "alert",
          "orange",
          { label: "Nodes needing attention", filters: { health_tier: "Low" } },
        ),
      ],
      chartTitle: "Health classification",
      chartCenter: number(sm?.total_nodes),
      chartLegend: legend(snapshot.solarwinds?.health_breakdown, "health_tier"),
      barsTitle: "Operational status",
      bars: bars(snapshot.solarwinds?.status_breakdown, "status"),
      tableTitle: "SolarWinds node inventory",
      searchPlaceholder: "Search node name, IP, serial, vendor",
      columns: [
        "Node name",
        "IP address",
        "Operational status",
        "Device type",
        "Vendor",
        "Health tier",
        "CPU load",
      ],
      endpoint: "/solarwinds/nodes",
      statuses: Object.keys(snapshot.solarwinds?.status_breakdown ?? {}),
      categories: snapshot.solarwinds?.source_categories,
    },
    "Digital Workspace": {
      eyebrow: "MICROSOFT INTUNE",
      title: "Digital employee experience",
      description:
        "Track managed devices, compliance posture, operating systems, and storage health.",
      metrics: [
        metric(
          "Total managed endpoints",
          im?.total_managed_devices,
          `${number(im?.compliant_devices)} compliant`,
          "monitor",
          "blue",
          { label: "All managed endpoints", filters: {} },
        ),
        {
          ...metric(
            "Compliance posture rate",
            null,
            "Confirmed compliant / all managed endpoints",
            "check",
            "green",
            {
              label: "Confirmed compliant endpoints",
              filters: { status: "Compliant" },
            },
          ),
          value: percent(
            snapshot.intune?.decision_metrics?.confirmed_compliance?.value,
          ),
        },
        metric(
          "OS distribution",
          snapshot.intune?.os_distribution
            ? Object.keys(snapshot.intune.os_distribution).length
            : undefined,
          "Reported OS families",
          "database",
          "purple",
          { label: "Operating system families", target: "chart" },
        ),
        metric(
          "Devices requiring action",
          im?.noncompliant_devices,
          "Confirmed noncompliant endpoints",
          "alert",
          "orange",
          {
            label: "Noncompliant endpoints",
            filters: { status: "NonCompliant" },
          },
        ),
      ],
      chartTitle: "Operating system fleet",
      chartCenter: number(im?.total_managed_devices),
      chartLegend: legend(snapshot.intune?.os_distribution, "ci_type"),
      barsTitle: "Device compliance policy",
      bars: bars(snapshot.intune?.status_breakdown, "status"),
      tableTitle: "Managed endpoint inventory",
      searchPlaceholder: "Search device name, user, serial",
      columns: [
        "Device name",
        "Primary user",
        "OS version",
        "Manufacturer",
        "Compliance",
        "Reporting location",
        "Serial number",
      ],
      endpoint: "/intune/devices",
      statuses: Object.keys(snapshot.intune?.status_breakdown ?? {}),
    },
    "Assets Analytics": {
      eyebrow: "UNIFIED CONFIGURATION DATA",
      title: "Assets intelligence",
      description:
        "Explore normalized configuration records from Intune and SolarWinds in one view.",
      metrics: [
        metric(
          "Total source records",
          cmdb?.total_cis,
          "Combined source records",
          "database",
          "purple",
          { label: "All configuration items", filters: {} },
        ),
        metric(
          "Intune records",
          sourceCounts ? (sourceCounts.INTUNE ?? 0) : undefined,
          "Managed endpoint records",
          "monitor",
          "blue",
          { label: "Intune records", filters: { source_system: "INTUNE" } },
        ),
        metric(
          "SolarWinds records",
          sourceCounts ? (sourceCounts.SOLARWINDS ?? 0) : undefined,
          "Infrastructure node records",
          "server",
          "green",
          {
            label: "SolarWinds records",
            filters: { source_system: "SOLARWINDS" },
          },
        ),
        metric(
          "Source systems",
          sourceEntries?.length,
          sourceEntries
            ?.map(([source]) => sourceNames[source] ?? source)
            .join(" · ") ?? "Source breakdown unavailable",
          "check",
          "orange",
          { label: "Source systems", target: "chart" },
        ),
      ],
      chartTitle: "Records by source",
      chartCenter: number(cmdb?.total_cis),
      chartLegend: sourceChart,
      barsTitle: "Configuration item health",
      bars: cmdb?.health_breakdown
        ? bars(cmdb.health_breakdown, "health_tier")
        : cmdb &&
            [
              cmdb.high_health_count,
              cmdb.medium_health_count,
              cmdb.low_health_count,
            ].every(Number.isFinite)
          ? bars(
              {
                High: cmdb.high_health_count!,
                Medium: cmdb.medium_health_count!,
                Low: cmdb.low_health_count!,
              },
              "health_tier",
            )
          : [],
      tableTitle: "Configuration item inventory",
      searchPlaceholder: "Search CI name, serial, IP address",
      columns: [
        "Configuration item",
        "Source system",
        "CI type",
        "Vendor",
        "Location",
        "Health tier",
        "Serial number",
      ],
      endpoint: "/cmdb/cis",
      sources: sourceEntries?.map(([value]) => ({
        value,
        label: sourceNames[value] ?? value,
      })),
      statuses: Array.from(
        new Set([
          ...Object.keys(snapshot.intune?.status_breakdown ?? {}),
          ...Object.keys(snapshot.solarwinds?.status_breakdown ?? {}),
        ]),
      ),
    },
  };
  for (const title of ["Knowledge Center", "Automations"]) {
    workspaceConfigs[title] = {
      eyebrow:
        title === "Automations"
          ? "OPERATIONAL WORKFLOWS"
          : "KNOWLEDGE & ENABLEMENT",
      title,
      description:
        title === "Automations"
          ? "Workflow execution data is not connected. Source synchronization history is available below."
          : "A knowledge content service is not connected to this portal.",
      metrics: [],
      chartTitle: "",
      chartCenter: "—",
      chartLegend: [],
      barsTitle: "",
      bars: [],
      tableTitle: title,
      searchPlaceholder: "",
      columns: [],
      unavailable: "This workspace has no connected data service.",
    };
  }
  return {
    kpis,
    locations,
    siteRows,
    workspaceConfigs,
    freshness,
    groupsAvailable,
  };
}

export function donutGradient(items: Legend[]): string {
  const colors: Record<string, string> = {
    blue: "#1554bf",
    green: "#16a374",
    amber: "#f1a52d",
    purple: "#7957bf",
    red: "#e05260",
    slate: "#98a2b3",
  };
  const values = items.map(
    (item) => Number(item.value.replaceAll(",", "")) || 0,
  );
  const total = values.reduce((sum, value) => sum + value, 0);
  if (!total) return "#e3e9f2";
  let end = 0;
  return `conic-gradient(${items
    .map((item, i) => {
      const start = end;
      end += (values[i] / total) * 100;
      return `${colors[item.tone] ?? colors.slate} ${start}% ${end}%`;
    })
    .join(", ")})`;
}

export function donutSlice(
  items: Legend[],
  fraction: number,
): Legend | undefined {
  const values = items.map((item) =>
    Math.max(0, Number(item.value.replaceAll(",", "")) || 0),
  );
  const total = values.reduce((sum, value) => sum + value, 0);
  if (!total) return undefined;
  const position = (((fraction % 1) + 1) % 1) * total;
  let accumulated = 0;
  return items.find((_, index) => {
    accumulated += values[index];
    return position < accumulated;
  });
}

export function csvText(columns: string[], rows: string[][]): string {
  const quote = (value: string) => {
    const safe = /^[\s]*[=+@-]/.test(value) ? `'${value}` : value;
    return `"${safe.replaceAll('"', '""')}"`;
  };
  return (
    "\uFEFF" +
    [columns, ...rows].map((row) => row.map(quote).join(",")).join("\r\n")
  );
}

export function downloadCsv(
  filename: string,
  columns: string[],
  rows: string[][],
) {
  const url = URL.createObjectURL(
    new Blob([csvText(columns, rows)], { type: "text/csv;charset=utf-8" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
