import { useEffect, useMemo, useRef, useState } from "react";
import {
  buildPortalModel,
  buildOperationsCharts,
  operationsCategoryFilters,
  donutGradient,
  downloadCsv,
  number,
  ageLabel,
  time,
  donutSlice,
} from "./data";
import type { IconName, WorkspaceConfig, Drilldown, Snapshot } from "./data";
import { usePortalSnapshot } from "./api";
import { InventoryPanel, SyncHistory } from "./Inventory";
import { LocationScores } from "./LocationScores";
import { AssetsAnalytics } from "./AssetsAnalytics";
import { VendorManagement } from "./VendorManagement";
import { KnowledgeCentre } from "./KnowledgeCentre";
import { ModuleAccess } from "./ModuleAccess";

const iconPaths: Record<IconName, React.ReactNode> = {
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4-4" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 11a8 8 0 1 0-2.34 5.66" />
      <path d="M20 4v7h-7" />
    </>
  ),
  chevron: <path d="m8 10 4 4 4-4" />,
  server: (
    <>
      <rect x="4" y="4" width="16" height="6" rx="1.5" />
      <rect x="4" y="14" width="16" height="6" rx="1.5" />
      <path d="M8 7h.01M8 17h.01" />
    </>
  ),
  monitor: (
    <>
      <rect x="3" y="4" width="18" height="13" rx="2" />
      <path d="M8 21h8m-4-4v4" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v7c0 1.66 3.58 3 8 3s8-1.34 8-3V5" />
      <path d="M4 12v7c0 1.66 3.58 3 8 3s8-1.34 8-3v-7" />
    </>
  ),
  activity: <path d="M3 12h4l2.5-7 5 14 2.5-7h4" />,
  map: (
    <>
      <path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3Z" />
      <path d="M9 3v15m6-12v15" />
    </>
  ),
  alert: (
    <>
      <path d="M12 3 2.8 19h18.4Z" />
      <path d="M12 9v4m0 3h.01" />
    </>
  ),
  check: <path d="m5 12 4 4L19 6" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  external: (
    <>
      <path d="M14 4h6v6m0-6-9 9" />
      <path d="M19 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h6" />
    </>
  ),
};

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      className="icon"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
    >
      {iconPaths[name]}
    </svg>
  );
}

const navigation = [
  "Home Page",
  "Operations Analytics",
  "Digital Workspace",
  "Assets Analytics",
  "Knowledge Center",
  "Vendor Management",
  "Automations",
];

const navigationIcons: Record<string, IconName> = {
  "Home Page": "activity",
  "Operations Analytics": "server",
  "Digital Workspace": "monitor",
  "Assets Analytics": "database",
  "Knowledge Center": "check",
  Automations: "refresh",
  "Vendor Management": "external",
};

function WorkspacePage({
  config,
  lastRefresh,
  onRefresh,
  revision,
  globalSearch,
  groupId,
  initialStatus,
  initialHealth,
  initialPressure,
  groupName,
  locations,
  loading,
  sourceGroups,
  locationScores,
  geographicScores,
  geographicScoresAvailable,
  geographicScoresLoading,
  locationScoresAvailable,
  locationScoresLoading,
  snapshot,
  onClearSearch,
}: {
  config: WorkspaceConfig;
  lastRefresh: string;
  onRefresh: () => void;
  revision: number;
  globalSearch: string;
  groupId?: number;
  initialStatus: string;
  initialHealth: string;
  initialPressure: boolean;
  groupName?: string;
  locations: Array<{ id: string; name: string; endpoints: number }>;
  loading: boolean;
  sourceGroups: ReturnType<typeof buildPortalModel>["locations"];
  locationScores: ReturnType<typeof buildPortalModel>["locationScores"];
  geographicScores: ReturnType<typeof buildPortalModel>["geographicScores"];
  geographicScoresAvailable: boolean;
  geographicScoresLoading: boolean;
  locationScoresAvailable: boolean;
  locationScoresLoading: boolean;
  snapshot: Snapshot;
  onClearSearch: () => void;
}) {
  const [selection, setSelection] = useState<Drilldown>({
    label: groupName ?? "",
    groupId,
    filters: {
      ...(initialStatus ? { status: initialStatus } : {}),
      ...(initialHealth ? { health_tier: initialHealth } : {}),
      ...(initialPressure ? { resource_pressure: true } : {}),
    },
  });
  const [selectionId, setSelectionId] = useState(0);
  const [operationsScope, setOperationsScope] = useState("Total Nodes");
  const isOperations = config.title === "Infrastructure intelligence";
  const charts = isOperations ? buildOperationsCharts(snapshot, operationsScope) : config;
  const detailRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  const focusChart = useRef(false);
  function choose(action: Drilldown, showCharts = false) {
    focusChart.current = showCharts;
    setSelection(action);
    setSelectionId((value) => value + 1);
    onClearSearch();
    onRefresh();
  }
  useEffect(() => {
    if (!selectionId) return;
    const target =
      focusChart.current || selection.target === "chart" ? chartRef.current : detailRef.current;
    target?.focus({ preventScroll: true });
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [selectionId, selection.target]);
  return (
    <>
      <section className="workspace-hero">
        <div>
          <p className="eyebrow">{config.eyebrow}</p>
          <h1>{config.title}</h1>
          <p className="hero__subtitle">{config.description}</p>
        </div>
        <div className="hero__actions">
          <span className="freshness" data-status={lastRefresh.split(" · ")[0]}>
            <span className="freshness__dot" />
            {lastRefresh}
          </span>
          <button
            className="button button--secondary"
            disabled={loading}
            onClick={onRefresh}
            type="button"
          >
            <Icon name="refresh" size={16} /> Reload snapshot
          </button>
        </div>
      </section>

      {config.unavailable ? (
        <section className="panel unavailable-panel">
          <h2>Data service unavailable</h2>
          <p>{config.description}</p>
          {config.title === "Automations" ? (
            <SyncHistory revision={revision} />
          ) : (
            <p>
              Knowledge guides, onboarding and recorded learning are coming
              soon.
            </p>
          )}
        </section>
      ) : (
        <>
          <section
            className="kpi-grid workspace-kpis"
            aria-label={`${config.title} summary`}
          >
            {config.metrics.map((metric) => (
              <button
                className="kpi-card kpi-card--interactive"
                key={metric.label}
                type="button"
                aria-label={`View ${metric.label}`}
                aria-pressed={isOperations ? operationsScope === metric.label : selection.label === metric.action?.label}
                disabled={loading || metric.value === "—" || !metric.action}
                onClick={() => { if (isOperations) setOperationsScope(metric.label); if (metric.action) choose(metric.action, isOperations); }}
              >
                <div className={`icon-box icon-box--${metric.tone}`}>
                  <Icon name={metric.icon} size={18} />
                </div>
                <div className="kpi-card__content">
                  <p>{metric.label}</p>
                  <div className="kpi-card__value-row">
                    <strong>{metric.value}</strong>
                  </div>
                  <small>{metric.meta}</small>
                </div>
              </button>
            ))}
          </section>

          <div
            ref={chartRef}
            tabIndex={-1}
            className={`drilldown-target${isOperations && operationsScope === "Location" ? " location-charts" : ""}`}
            aria-label={isOperations && operationsScope === "Location" ? "Location score charts" : "Interactive chart filters"}
          >
            <section className="analytics-grid">
              <article className="panel chart-panel">
                <div className="compact-panel-header">
                  <div>
                    <p className="eyebrow">DISTRIBUTION</p>
                    <h2>{charts.chartTitle}</h2>
                    {isOperations && <small>{operationsScope}</small>}
                  </div>
                </div>
                <div className="donut-layout">
                  <button
                    type="button"
                    className="analytics-donut"
                    disabled={loading || !charts.chartLegend.length || (isOperations && operationsScope === "Location")}
                    aria-label={`View all ${charts.chartTitle} records`}
                    title={
                      charts.chartLegend
                        .map((item) => `${item.label}: ${item.value}`)
                        .join(", ") || "Distribution unavailable"
                    }
                    onClick={(event) => {
                      const box = event.currentTarget.getBoundingClientRect();
                      const x = event.clientX - box.left - box.width / 2,
                        y = event.clientY - box.top - box.height / 2;
                      const onRing =
                        event.detail > 0 && Math.hypot(x, y) > box.width * 0.31;
                      const slice = onRing
                        ? donutSlice(
                            charts.chartLegend,
                            (Math.atan2(y, x) + Math.PI / 2) / (2 * Math.PI),
                          )
                        : undefined;
                      choose(
                        slice?.action ?? {
                          label: isOperations ? operationsScope : "All current inventory",
                          filters: isOperations && !["Total Nodes", "Location"].includes(operationsScope) ? operationsCategoryFilters(snapshot, operationsScope) : {},
                        },
                      );
                    }}
                    style={{ background: donutGradient(charts.chartLegend) }}
                  >
                    <div>
                      <strong>{charts.chartCenter}</strong>
                      <span>{isOperations && operationsScope === "Location" ? "Locations" : "Total records"}</span>
                    </div>
                  </button>
                  <ul className="chart-legend">
                    {charts.chartLegend.map((item) => (
                      <li key={item.label}>
                        <button
                          className="chart-filter"
                          type="button"
                          aria-label={`Filter ${charts.chartTitle}: ${item.label}`}
                          aria-pressed={selection.label === item.action?.label}
                          disabled={loading || !item.action}
                          onClick={() => item.action && choose(item.action)}
                        >
                          <span
                            className={`chart-key chart-key--${item.tone}`}
                          />
                          <span>{item.label}</span>
                          <strong>{item.value}</strong>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
                {isOperations && charts.chartLegend.length === 0 && <p className="chart-hint" role="status">{charts.chartCenter === "0" ? `No ${operationsScope} records in this snapshot.` : `Classification data unavailable for ${operationsScope}.`}</p>}
              </article>

              <article className="panel chart-panel">
                <div className="compact-panel-header">
                  <div>
                    <p className="eyebrow">CURRENT SNAPSHOT</p>
                    <h2>{charts.barsTitle}</h2>
                    {isOperations && <small>{operationsScope}</small>}
                  </div>
                  <span className="count-badge">Snapshot</span>
                </div>
                <div className="bar-chart">
                  {charts.bars.map((bar) => (
                    <button
                      className="bar-column bar-column--interactive"
                      key={bar.label}
                      type="button"
                      aria-label={`Filter ${charts.barsTitle}: ${bar.label}`}
                      aria-pressed={selection.label === bar.action?.label}
                      disabled={loading || !bar.action}
                      onClick={() => bar.action && choose(bar.action)}
                    >
                      <span className="bar-value">{bar.display}</span>
                      <div className="bar-track">
                        <i
                          className={`bar-fill bar-fill--${bar.tone}`}
                          style={{ height: `${bar.value}%` }}
                        />
                      </div>
                      <small>{bar.label}</small>
                    </button>
                  ))}
                </div>
                {isOperations && charts.bars.length === 0 && <p className="chart-hint" role="status">{charts.chartCenter === "0" ? `No ${operationsScope} records in this snapshot.` : `Status data unavailable for ${operationsScope}.`}</p>}
              </article>
            </section>
            <p className="chart-hint">
              {isOperations && operationsScope === "Location"
                ? "These charts summarize SolarWinds groups. Use the filters below to explore site scores."
                : "Select a card, classification or status to view matching current records."}
            </p>
          </div>

          <div
            ref={detailRef}
            tabIndex={-1}
            className="drilldown-target"
            aria-label="Filtered data"
          >
            {selection.target === "groups" ? (
              <LocationScores groups={sourceGroups} available={snapshot.groups?.data_available === true} loading={loading} freshness={snapshot.freshness?.sources?.SOLARWINDS} />
            ) : (
              <InventoryPanel
                key={`${config.endpoint}-${selectionId}`}
                config={config}
                revision={revision}
                globalSearch={globalSearch}
                groupId={selection.groupId}
                initialFilters={selection.filters}
                selectionLabel={selection.label}
                groupName={
                  selection.groupId
                    ? (sourceGroups.find(
                        (group) => group.id === selection.groupId,
                      )?.name ?? selection.label)
                    : undefined
                }
                onReset={() =>
                  choose({ label: "All current inventory", filters: {} })
                }
                locations={locations}
              />
            )}
          </div>
        </>
      )}
    </>
  );
}

function LocationMatches({ report, loading }: { report?: Snapshot["locationMatches"]; loading: boolean }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState(false);
  const available = !!report?.data_available;
  const rows = (report?.items ?? []).filter((item) =>
    item.location_name.toLowerCase().includes(query.toLowerCase()) && (!status || item.status === status),
  );
  return (
    <details className="location-matches" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>
        <h2>Intune and SolarWinds location matches</h2>
        <span>{available ? `${report.matched_locations} / ${report.named_intune_locations} matched` : loading ? "Loading matches" : "Unavailable"}</span>
      </summary>
      {open && <><div className="panel__header">
        <div className="table-tools">
          <label className="table-search">
            <Icon name="search" size={15} />
            <input type="search" aria-label="Search cross-source locations" placeholder="Search locations" value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
          <select className="button button--secondary" aria-label="Location match status" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">All matches</option>
            <option value="matched">Matched</option>
            <option value="unmatched">Unmatched</option>
          </select>
          <button type="button" className="button button--secondary" disabled={!available} onClick={() => downloadCsv(
            "itom-location-matches.csv",
            ["Intune location", "Intune endpoints", "Match status", "Geographic level", "SolarWinds nodes", "Source evidence"],
            rows.map((item) => [item.location_name, String(item.intune_endpoints), item.status, item.match_level ?? "", String(item.solarwinds_nodes), item.evidence.map((entry) => `${entry.source_label} (${entry.nodes})`).join("; ")]),
          )}>
            <Icon name="external" size={15} /> Export location matches
          </button>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Intune location</th><th>Endpoints</th><th>Geographic match</th><th>SolarWinds nodes</th><th>Source location evidence</th></tr></thead>
          <tbody>{available && rows.map((item) => (
            <tr key={item.location_id}>
              <td><strong>{item.location_name}</strong></td>
              <td>{number(item.intune_endpoints)}</td>
              <td title={item.reason ?? undefined}>{item.match_level ? item.match_level[0].toUpperCase() + item.match_level.slice(1) : "Unmatched"}</td>
              <td>{number(item.solarwinds_nodes)}</td>
              <td className="match-evidence">{item.evidence.length ? item.evidence.map((entry) => `${entry.source_label} (${entry.nodes})`).join("; ") : item.reason}</td>
            </tr>
          ))}</tbody>
        </table>
        {(!available || rows.length === 0) && <div className="empty-state">{loading ? "Loading location matches" : !available ? "Source location evidence unavailable." : "No locations match these filters."}</div>}
      </div>
      <div className="table-footer">
        <span>{available ? `${report.matched_locations} matched / ${report.named_intune_locations} named Intune locations` : "Matching data unavailable"}</span>
        {available && <span>{number(report.unassigned_intune_endpoints)} unassigned endpoints | {number(report.conflicting_solarwinds_nodes)} conflicting nodes excluded | {report.freshness?.sources?.SOLARWINDS?.status ?? "UNKNOWN"}</span>}
      </div></>}
    </details>
  );
}

function App() {
  const [activeNav, setActiveNav] = useState("Home Page");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const refreshVisibleSnapshot = () => {
      if (!document.hidden) setRevision((value) => value + 1);
    };
    const timer = window.setInterval(refreshVisibleSnapshot, 600_000);
    return () => {
      window.clearInterval(timer);
    };
  }, []);
  const { snapshot, pending, errors } = usePortalSnapshot(revision);
  const loading = pending.includes("freshness");
  const sourceLoading = (key: string) => pending.includes(key);
  const sourceDescription = (source: "INTUNE" | "SOLARWINDS") => {
    if (sourceLoading("freshness")) return "Checking source freshness…";
    if (errors.includes("freshness")) return "Source freshness unavailable";
    const state = snapshot.freshness?.sources?.[source];
    if (!state) return "Source freshness unavailable";
    const freshness = state.last_synchronized_at ? (state.status ?? "UNKNOWN") : "NEVER SYNCED";
    const attempt = state.last_attempt_status && state.last_attempt_status !== "SUCCESS"
      ? ` · Latest attempt: ${state.last_attempt_status}${state.last_attempt_at ? ` (${time(state.last_attempt_at)})` : ""}` : "";
    return `${freshness} · Last successful ingestion: ${time(state.last_synchronized_at ?? undefined)}${attempt}`;
  };
  const {
    locations,
    locationScores,
    geographicScores,
    kpis,
    workspaceConfigs,
    freshness,
  } = useMemo(() => buildPortalModel(snapshot), [snapshot]);
  const [globalQuery, setGlobalQuery] = useState("");
  const [groupId, setGroupId] = useState<number | undefined>();
  const [initialStatus, setInitialStatus] = useState("");
  const [initialHealth, setInitialHealth] = useState("");
  const [initialPressure, setInitialPressure] = useState(false);
  const [showSync, setShowSync] = useState(false);
  const lastRefresh = loading
    ? "Loading snapshot…"
    : `${freshness} · ${ageLabel(snapshot.freshness?.oldest_age_seconds)}`;
  const workspaceSource =
    activeNav === "Operations Analytics"
      ? "SOLARWINDS"
      : activeNav === "Digital Workspace"
        ? "INTUNE"
        : undefined;
  const workspaceLastRefresh = workspaceSource ? sourceDescription(workspaceSource) : lastRefresh;
  const workspaceLoading = sourceLoading(activeNav === "Operations Analytics" ? "solarwinds" : activeNav === "Digital Workspace" ? "intune" : "cmdb");
  const sm = snapshot.solarwinds?.metrics,
    im = snapshot.intune?.metrics;
  const attention = [
    {
      title: `${number(sm?.low_critical_nodes)} nodes in low health tier`,
      detail: "SolarWinds · persisted health classification",
      nav: "Operations Analytics",
      status: "",
      health: "Low",
      pressure: false,
      tone: "critical",
      icon: "alert" as IconName,
    },
    {
      title: `${number(snapshot.solarwinds?.decision_metrics?.resource_pressure?.numerator)} nodes above resource thresholds`,
      detail:
        snapshot.solarwinds?.decision_metrics?.resource_pressure?.definition ??
        "Resource evidence unavailable",
      nav: "Operations Analytics",
      status: "",
      health: "",
      pressure: true,
      tone: "warning",
      icon: "activity" as IconName,
    },
    {
      title: `${number(im?.noncompliant_devices)} devices noncompliant`,
      detail: "Microsoft Intune · confirmed noncompliance",
      nav: "Digital Workspace",
      status: "NonCompliant",
      health: "",
      pressure: false,
      tone: "info",
      icon: "clock" as IconName,
    },
  ];
  function navigate(
    item: string,
    status = "",
    selectedGroup?: number,
    health = "",
    pressure = false,
  ) {
    setActiveNav(item);
    setInitialStatus(status);
    setGroupId(selectedGroup);
    setInitialHealth(health);
    setInitialPressure(pressure);
    setShowSync(false);
  }
  function refreshSnapshot() {
    setRevision((value) => value + 1);
  }

  return (
    <div
      className={
        sidebarCollapsed ? "app-shell app-shell--collapsed" : "app-shell"
      }
    >
      <header className="topbar">
        <div
          className="product-context"
          aria-label="ITOM Operations Intelligence"
        >
          <span className="product-name">ITOM</span>
          <span className="product-context__label">
            Operations Intelligence
          </span>
        </div>

        <label className="global-search">
          <Icon name="search" size={16} />
          <input
            aria-label="Search configuration items, devices, or sites"
            onChange={(event) => setGlobalQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") navigate("Assets Analytics");
            }}
            placeholder="Search CIs, devices, sites"
            type="search"
            value={globalQuery}
          />
          <kbd>/</kbd>
        </label>
      </header>

      <nav className="navigation" aria-label="Primary navigation">
        <div className="navigation__inner">
          <div className="sidebar-brand">
            <img
              className="coforge-logo"
              src="/coforge-logo.png"
              alt="Coforge"
            />
            <span className="sidebar-monogram" aria-hidden="true">
              C
            </span>
          </div>
          <p className="sidebar-section-label">WORKSPACES</p>
          {navigation.map((item) => (
              <button
                className={
                  activeNav === item ? "nav-item nav-item--active" : "nav-item"
                }
                key={item}
                aria-current={
                  activeNav === item && !showSync ? "page" : undefined
                }
                onClick={() => navigate(item)}
                type="button"
              >
                <span className="nav-item__icon">
                  <Icon name={navigationIcons[item]} size={17} />
                </span>
                <span className="nav-item__label">{item}</span>
              </button>
          ))}
          <div className="sidebar-status" data-status={freshness}>
            <span className="sidebar-status__dot" />
            <span>
              <strong>
                {loading
                  ? "Checking sources"
                  : `Sources ${freshness.toLowerCase()}`}
              </strong>
              <small>
                {errors.length
                  ? `${errors.length} reads unavailable`
                  : "Persisted telemetry snapshots"}
              </small>
            </span>
          </div>
          <div className="sidebar-user">
            <span className="sidebar-user__avatar">OP</span>
            <span className="sidebar-user__copy">
              <strong>ITOM Operator</strong>
              <small>Operations</small>
            </span>
            <button
              aria-label="Open Knowledge Center"
              className="sidebar-logout"
              title="Knowledge Center"
              onClick={() => navigate("Knowledge Center")}
              type="button"
            >
              <Icon name="external" size={15} />
            </button>
          </div>
        </div>
        <button
          aria-expanded={!sidebarCollapsed}
          aria-label={
            sidebarCollapsed ? "Expand navigation" : "Collapse navigation"
          }
          className="sidebar-toggle"
          onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
          title={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
          type="button"
        >
          <Icon name="chevron" size={16} />
        </button>
      </nav>

      <main aria-busy={loading} className={activeNav === "Operations Analytics" && !showSync ? "operations-analytics" : undefined}>
        {errors.length > 0 && (
          <div className="data-notice" role="alert">
            Some data reads are unavailable: {errors.join(", ")}.{" "}
            <button
              className="text-button"
              disabled={loading}
              onClick={refreshSnapshot}
            >
              Retry
            </button>
          </div>
        )}
        {showSync ? (
          <>
            <section className="workspace-hero">
              <div>
                <p className="eyebrow">OPERATIONS</p>
                <h1>Source synchronization</h1>
              </div>
              <button
                className="button button--secondary"
                onClick={refreshSnapshot}
              >
                Reload snapshot
              </button>
            </section>
            <SyncHistory revision={revision} />
          </>
        ) : activeNav === "Home Page" ? (
          <>
            <section className="hero">
              <div>
                <p className="eyebrow">OPERATIONS OVERVIEW</p>
                <h1>
                  {activeNav === "Home Page"
                    ? "Operations overview"
                    : activeNav}
                </h1>
              </div>
              <div className="hero__actions">
                <span className="freshness" data-status={freshness}>
                  <span className="freshness__dot" />
                  {lastRefresh}
                </span>
                <button
                  className="button button--secondary"
                  onClick={refreshSnapshot}
                  disabled={loading}
                  type="button"
                >
                  <Icon name="refresh" size={16} /> Reload snapshot
                </button>
              </div>
            </section>

            <section className="kpi-grid" aria-label="Operational summary">
              {kpis.slice(0, 3).map((kpi, index) => (
                <button
                  className="kpi-card kpi-card--interactive"
                  key={kpi.label}
                  type="button"
                  aria-label={`View ${kpi.label}`}
                  onClick={() => { setGlobalQuery(""); navigate(["Digital Workspace", "Operations Analytics", "Assets Analytics"][index]); }}
                >
                  <div className={`icon-box icon-box--${kpi.tone}`}>
                    <Icon name={kpi.icon} size={18} />
                  </div>
                  <div className="kpi-card__content">
                    <p>{kpi.label}</p>
                    <div className="kpi-card__value-row">
                      <strong>{kpi.value}</strong>
                      <span>{kpi.trend}</span>
                    </div>
                    <small>{sourceLoading(["intune", "solarwinds", "cmdb", "groups"][index]) ? "Loading…" : kpi.value === "—" ? "Unavailable" : kpi.meta}</small>
                  </div>
                </button>
              ))}
              <button className="kpi-card kpi-card--interactive" type="button" aria-label="View Knowledge Center" onClick={() => { setGlobalQuery(""); navigate("Knowledge Center"); }}>
                <div className="icon-box icon-box--orange"><Icon name="check" size={18} /></div>
                <div className="kpi-card__content"><p>Knowledge Center</p><small>Help and resources</small></div>
              </button>
            </section>

              <aside className="panel attention-panel">
                <div className="panel__header">
                  <div>
                    <p className="eyebrow">OPERATOR QUEUE</p>
                    <h2>Needs attention</h2>
                  </div>
                  <span className="count-badge">Snapshot exceptions</span>
                </div>
                <div className="attention-list">
                  {attention.map((item) => (
                    <button
                      type="button"
                      key={item.nav + item.title}
                      onClick={() =>
                        navigate(
                          item.nav,
                          item.status,
                          undefined,
                          item.health,
                          item.pressure,
                        )
                      }
                    >
                      <span className={`severity severity--${item.tone}`}>
                        <Icon name={item.icon} size={16} />
                      </span>
                      <span>
                        <strong>{item.title}</strong>
                        <small title={item.detail}>{item.detail}</small>
                      </span>
                      <Icon name="chevron" size={16} />
                    </button>
                  ))}
                </div>
                <button
                  className="text-button"
                  type="button"
                  onClick={() => navigate("Assets Analytics")}
                >
                  View all inventory <span>→</span>
                </button>
              </aside>

          </>
        ) : activeNav === "Assets Analytics" ? (
          <ModuleAccess><AssetsAnalytics
            onRefresh={refreshSnapshot}
            revision={revision}
          /></ModuleAccess>
        ) : activeNav === "Vendor Management" ? (
          <ModuleAccess><VendorManagement /></ModuleAccess>
        ) : activeNav === "Knowledge Center" ? (
          <ModuleAccess><KnowledgeCentre /></ModuleAccess>
        ) : (
          <>
          <WorkspacePage
            key={activeNav}
            config={workspaceConfigs[activeNav]}
            snapshot={snapshot}
            revision={revision}
            globalSearch={globalQuery}
            groupId={groupId}
            initialStatus={initialStatus}
            initialHealth={initialHealth}
            initialPressure={initialPressure}
            groupName={
              locations.find((location) => location.id === groupId)?.name
            }
            locations={snapshot.locations?.items ?? []}
            loading={workspaceLoading}
            lastRefresh={workspaceLastRefresh}
            onRefresh={refreshSnapshot}
            sourceGroups={locations}
            locationScores={locationScores}
            geographicScores={geographicScores}
            geographicScoresAvailable={!!snapshot.geographicScores}
            geographicScoresLoading={sourceLoading("geographicScores")}
            locationScoresAvailable={!!snapshot.locations}
            locationScoresLoading={sourceLoading("locations")}
            onClearSearch={() => setGlobalQuery("")}
          />
          {activeNav === "Operations Analytics" && <LocationMatches report={snapshot.locationMatches} loading={sourceLoading("locationMatches")} />}
          </>
        )}
      </main>

      <footer>
        <span>
          Coforge IT Operations Intelligence © {new Date().getFullYear()}
        </span>
        <div>
          <button
            type="button"
            onClick={() => navigate("Operations Analytics")}
          >
            Operations
          </button>
          <button type="button" onClick={() => setShowSync(true)}>
            Sync runs
          </button>
          <button type="button" onClick={() => navigate("Knowledge Center")}>
            Help &amp; support
          </button>
        </div>
      </footer>
    </div>
  );
}

export default App;
