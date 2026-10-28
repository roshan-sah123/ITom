import { useEffect, useRef, useState } from "react";
import { getJson, inventoryCells } from "./api";
import type { CI, Inventory } from "./api";
import { downloadCsv, time } from "./data";
import type { WorkspaceConfig, InventoryFilters } from "./data";

export function InventoryPanel({
  config,
  revision,
  globalSearch,
  groupId,
  initialStatus = "",
  initialHealth = "",
  groupName,
  initialFilters = {},
  selectionLabel,
  onReset,
  locations = [],
}: {
  config: WorkspaceConfig;
  revision: number;
  globalSearch: string;
  groupId?: number;
  initialStatus?: string;
  initialHealth?: string;
  groupName?: string;
  initialFilters?: InventoryFilters;
  selectionLabel?: string;
  onReset?: () => void;
  locations?: Array<{ id: string; name: string; endpoints: number }>;
}) {
  const [search, setSearch] = useState(globalSearch);
  const [status, setStatus] = useState(initialFilters.status ?? initialStatus);
  const [location, setLocation] = useState("");
  const [source, setSource] = useState(initialFilters.source_system ?? "");
  const [category, setCategory] = useState(
    initialFilters.category_missing
      ? "__missing"
      : (initialFilters.category ?? ""),
  );
  const [health, setHealth] = useState(
    initialFilters.health_tier ?? initialHealth,
  );
  const [ciType, setCiType] = useState(initialFilters.ci_type ?? "");
  const [resourcePressure, setResourcePressure] = useState(
    initialFilters.resource_pressure ?? false,
  );
  const [retry, setRetry] = useState(0);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(25);
  const [sort, setSort] = useState("name:asc");
  const [data, setData] = useState<Inventory | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [selected, setSelected] = useState<CI | null>(null);
  const requestId = useRef(0);
  useEffect(() => {
    setSearch(globalSearch);
    setPage(1);
  }, [globalSearch]);
  const endpoint = groupId
    ? `/solarwinds/groups/${groupId}/devices`
    : config.endpoint!;
  const isIntune = config.endpoint!.startsWith("/intune"),
    isSolar = config.endpoint!.startsWith("/solarwinds");
  const filters = (requestedPage: number, pageSize = size) =>
    new URLSearchParams({
      page: String(requestedPage),
      page_size: String(pageSize),
      search,
      ...(status ? { status } : {}),
      ...(location ? { location_id: location } : {}),
      ...(source ? { source_system: source } : {}),
      ...(category === "__missing"
        ? { category_missing: "true" }
        : category
          ? { category }
          : {}),
      ...(health ? { health_tier: health } : {}),
      ...(ciType ? { ci_type: ciType } : {}),
      ...(resourcePressure ? { resource_pressure: "true" } : {}),
      ...(!groupId
        ? { sort_by: sort.split(":")[0], sort_order: sort.split(":")[1] }
        : {}),
    }).toString();
  const query = filters(page);
  useEffect(() => {
    const controller = new AbortController();
    const id = ++requestId.current;
    setLoading(true);
    setError("");
    setData(null);
    const timer = setTimeout(() => {
      void getJson<Inventory | { data: Inventory }>(
        `${endpoint}?${query}`,
        controller.signal,
      )
        .then((result) => {
          if (id === requestId.current && !controller.signal.aborted)
            setData("data" in result ? result.data : result);
        })
        .catch((err) => {
          if (!controller.signal.aborted) setError(String(err.message));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [endpoint, query, revision, retry]);
  const change = (setter: (value: string) => void, value: string) => {
    setter(value);
    setPage(1);
  };
  async function exportAll() {
    setExporting(true);
    setError("");
    try {
      const rows: string[][] = [];
      let totalPages = 1;
      for (let p = 1; p <= totalPages; p++) {
        const response = await getJson<Inventory | { data: Inventory }>(
          `${endpoint}?${filters(p, 100)}`,
        );
        const result = "data" in response ? response.data : response;
        totalPages = result.total_pages;
        rows.push(
          ...result.items.map((item) => inventoryCells(item, config.endpoint!)),
        );
      }
      downloadCsv("itom-inventory.csv", config.columns, rows);
    } catch (err) {
      setError(`CSV export failed. ${(err as Error).message}`);
    } finally {
      setExporting(false);
    }
  }
  const statuses =
    config.statuses ??
    (isIntune
      ? [
          "Compliant",
          "NonCompliant",
          "InGracePeriod",
          "ConfigManager",
          "Unknown",
        ]
      : ["Up", "Warning", "Critical", "Down", "Unmanaged", "Unknown"]);
  const filterLabels = [
    groupName ? `Group: ${groupName}` : "",
    category
      ? `Category: ${category === "__missing" ? "Unclassified" : category}`
      : "",
    status ? `Status: ${status}` : "",
    health ? `Health tier: ${health}` : "",
    source ? `Source: ${source}` : "",
    ciType ? `Operating system: ${ciType}` : "",
    resourcePressure ? "Observed resource pressure" : "",
    location
      ? `Reporting location: ${locations.find((item) => item.id === location)?.name ?? location}`
      : "",
    search ? `Search: ${search}` : "",
  ].filter(Boolean);
  function clearFilters() {
    if (onReset) {
      onReset();
      return;
    }
    setStatus("");
    setSource("");
    setCategory("");
    setHealth("");
    setCiType("");
    setResourcePressure(false);
    setLocation("");
    setSearch("");
    setPage(1);
  }
  return (
    <section className="panel inventory-panel" aria-busy={loading}>
      <div className="panel__header overview-header">
        <div>
          <p className="eyebrow">DETAILED VIEW</p>
          <h2>{config.tableTitle}</h2>
          {groupId && <small>{groupName} · unique group descendants</small>}
        </div>
        <div className="table-tools">
          <label className="table-search workspace-search">
            <span aria-hidden="true">⌕</span>
            <input
              aria-label={`Search ${config.tableTitle}`}
              placeholder={config.searchPlaceholder}
              type="search"
              value={search}
              onChange={(e) => change(setSearch, e.target.value)}
            />
          </label>
          <select
            className="button button--secondary"
            aria-label="Filter status"
            value={status}
            onChange={(e) => change(setStatus, e.target.value)}
          >
            <option value="">All statuses</option>
            {statuses.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
          {isIntune && (
            <select
              className="button button--secondary"
              aria-label="Reporting location"
              value={location}
              onChange={(e) => change(setLocation, e.target.value)}
            >
              <option value="">All locations</option>
              <option value="unassigned">Unassigned</option>
              {locations
                .filter((loc) => loc.endpoints > 0)
                .map((loc) => (
                  <option key={loc.id} value={loc.id}>
                    {loc.name}
                  </option>
                ))}
            </select>
          )}
          {isSolar && (
            <select
              className="button button--secondary"
              aria-label="Source category"
              value={category}
              onChange={(e) => change(setCategory, e.target.value)}
            >
              <option value="">All categories</option>
              {config.categories?.map((category) => (
                <option
                  key={category.value ?? "__missing"}
                  value={category.value ?? "__missing"}
                >
                  {category.value ?? "Unclassified"}
                </option>
              ))}
            </select>
          )}
          {!isIntune && !isSolar && (
            <select
              className="button button--secondary"
              aria-label="Source system"
              value={source}
              onChange={(e) => change(setSource, e.target.value)}
            >
              <option value="">All sources</option>
              {config.sources?.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          )}
          {!isIntune && !groupId && (
            <select
              className="button button--secondary"
              aria-label="Health tier"
              value={health}
              onChange={(e) => change(setHealth, e.target.value)}
            >
              <option value="">All health tiers</option>
              {["High", "Medium", "Low"].map((tier) => (
                <option key={tier}>{tier}</option>
              ))}
            </select>
          )}
          <button
            className="button button--secondary export-button"
            type="button"
            disabled={loading || exporting || !data}
            onClick={exportAll}
          >
            {exporting ? "Exporting…" : "Export CSV"}
          </button>
        </div>
      </div>
      {(selectionLabel || filterLabels.length > 0) && (
        <div className="inventory-selection" role="status">
          <span>
            {filterLabels.length
              ? filterLabels.join(" · ")
              : "All current inventory"}
            {loading
              ? " · Loading matching records…"
              : data
                ? ` · ${data.total.toLocaleString("en-US")} matching records`
                : ""}
          </span>
          <button className="text-button" type="button" onClick={clearFilters}>
            Clear filters
          </button>
        </div>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {config.columns.map((column, i) => (
                <th
                  key={column}
                  aria-sort={i === 0 && !groupId ? (sort === "name:asc" ? "ascending" : "descending") : undefined}
                >
                  {i === 0 && !groupId ? (
                    <button
                      className="sort-button"
                      onClick={() => {
                        setSort(sort === "name:asc" ? "name:desc" : "name:asc");
                        setPage(1);
                      }}
                    >
                      {column} {sort === "name:asc" ? "↑" : "↓"}
                    </button>
                  ) : (
                    column
                  )}
                </th>
              ))}
              <th>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((item) => (
              <tr key={item.id}>
                {inventoryCells(item, config.endpoint!).map((cell, i) => (
                  <td key={i}>
                    {i === 0 ? (
                      <button
                        className="inventory-name inventory-link"
                        aria-label={`Inspect ${item.name}`}
                        onClick={() => setSelected(item)}
                      >
                        <strong>{cell}</strong>
                      </button>
                    ) : (
                      cell
                    )}
                  </td>
                ))}
                <td>
                  <button
                    className="row-action"
                    aria-label={`Open ${item.name}`}
                    onClick={() => setSelected(item)}
                  >
                    ···
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && (
          <div className="empty-state" role="status">
            Loading source inventory…
          </div>
        )}
        {error && (
          <div className="empty-state" role="alert">
            {error}{" "}
            <button
              className="text-button"
              onClick={() => setRetry((value) => value + 1)}
            >
              Retry
            </button>
          </div>
        )}
        {!loading && !error && data?.items.length === 0 && (
          <div className="empty-state">No records match these filters.</div>
        )}
      </div>
      <div className="table-footer">
        <span>
          {data
            ? `Showing ${data.items.length} of ${data.total.toLocaleString("en-US")} records`
            : "Inventory unavailable until read completes"}
        </span>
        <div className="pagination">
          <label>
            Rows per page{" "}
            <select
              aria-label="Rows per page"
              value={size}
              onChange={(e) => {
                setSize(Number(e.target.value));
                setPage(1);
              }}
            >
              {[10, 25, 50, 100].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
          <button
            className="button button--secondary"
            disabled={loading || page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </button>
          <span>
            Page {page} of {data?.total_pages ?? "—"}
          </span>
          <button
            className="button button--secondary"
            disabled={loading || !data || page >= data.total_pages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </div>
      </div>
      {selected && (
        <CiDetails item={selected} onClose={() => setSelected(null)} />
      )}
    </section>
  );
}

function CiDetails({ item, onClose }: { item: CI; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [detail, setDetail] = useState<CI | null>(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<Array<{
    status: string;
    health_tier: string;
    recorded_at: string;
  }> | null>(null);
  const [historyError, setHistoryError] = useState(false);
  useEffect(() => {
    const focus = document.activeElement as HTMLElement;
    const controller = new AbortController();
    ref.current?.showModal();
    void getJson<CI>(
      `/cmdb/cis/${encodeURIComponent(item.id)}`,
      controller.signal,
    )
      .then(setDetail)
      .catch(() => {
        if (!controller.signal.aborted)
          setError("Device details unavailable. Close and reopen to retry.");
      });
    void getJson<
      Array<{ status: string; health_tier: string; recorded_at: string }>
    >(
      `/cmdb/cis/${encodeURIComponent(item.id)}/history?limit=10`,
      controller.signal,
    )
      .then(setHistory)
      .catch(() => {
        if (!controller.signal.aborted) setHistoryError(true);
      });
    return () => {
      controller.abort();
      focus?.focus();
    };
  }, [item.id]);
  const fields = detail
    ? {
        "Source system": detail.source_system,
        Status: detail.status,
        "Health tier": detail.health_tier,
        "IP address": detail.ip_address,
        Vendor: detail.vendor,
        "Operating system": detail.operating_system,
        "Serial number": detail.serial_number,
        Location: detail.canonical_location ?? detail.location,
        "Last synchronized": time(detail.last_sync_time),
      }
    : {};
  return (
    <dialog
      className="detail-dialog"
      ref={ref}
      onCancel={onClose}
      aria-labelledby="ci-detail-title"
    >
      <header>
        <h2 id="ci-detail-title">{item.name}</h2>
        <button
          className="button button--secondary"
          onClick={onClose}
          autoFocus
        >
          Close
        </button>
      </header>
      <p>
        Stored source snapshot. Missing measurements do not indicate a healthy
        device.
      </p>
      {error ? (
        <p role="alert">{error}</p>
      ) : !detail ? (
        <p role="status">Loading device evidence…</p>
      ) : (
        <dl>
          {Object.entries(fields).map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{value ?? "Not supplied"}</dd>
            </div>
          ))}
        </dl>
      )}
      <h3>Status history</h3>
      {historyError ? (
        <p>History unavailable.</p>
      ) : history === null ? (
        <p>Loading recorded changes…</p>
      ) : history.length ? (
        history.map((change, i) => (
          <p key={i}>
            {change.status} · {change.health_tier} · {time(change.recorded_at)}
          </p>
        ))
      ) : (
        <p>
          No status changes recorded. This does not establish historical uptime.
        </p>
      )}
    </dialog>
  );
}

export function SyncHistory({ revision }: { revision: number }) {
  const [rows, setRows] = useState<Array<{
    id: string;
    source_system: string;
    status: string;
    started_at: string;
    records_processed: number;
  }> | null>(null);
  const [error, setError] = useState(false);
  const [page, setPage] = useState(1);
  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    setError(false);
    void getJson<NonNullable<typeof rows>>(
      `/sync/runs?page=${page}&page_size=25`,
      controller.signal,
    )
      .then(setRows)
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [revision, page]);
  return (
    <section className="panel inventory-panel">
      <div className="panel__header">
        <h2>Source synchronization history</h2>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Source</th>
              <th>Status</th>
              <th>Started (IST)</th>
              <th>Records processed</th>
              <th>Run ID</th>
            </tr>
          </thead>
          <tbody>
            {rows?.map((row) => (
              <tr key={row.id}>
                <td>{row.source_system}</td>
                <td>{row.status}</td>
                <td>{time(row.started_at)}</td>
                <td>{row.records_processed.toLocaleString("en-US")}</td>
                <td>{row.id}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows && (
          <p className="empty-state" role="status">
            {error
              ? "Sync history unavailable. Reload snapshot to retry."
              : "Loading sync history…"}
          </p>
        )}
        {rows?.length === 0 && (
          <p className="empty-state">No synchronization runs recorded.</p>
        )}
      </div>
      <div className="table-footer">
        <span>Page {page}</span>
        <div className="pagination">
          <button
            className="button button--secondary"
            disabled={page === 1 || !rows}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </button>
          <button
            className="button button--secondary"
            disabled={!rows || rows.length < 25}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
}
