import { useState } from "react";
import { number } from "./data";
import type { buildPortalModel } from "./data";

type Groups = ReturnType<typeof buildPortalModel>["locations"];
export function GroupSelector({
  groups,
  available,
  loading,
  onSelect,
}: {
  groups: Groups;
  available: boolean;
  loading: boolean;
  onSelect: (id: number, name: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const rows = groups.filter(
    (group) =>
      group.name.toLowerCase().includes(search.toLowerCase()) &&
      (!status || group.status === status),
  );
  return (
    <section className="panel inventory-panel" aria-busy={loading}>
      <div className="panel__header overview-header">
        <div>
          <p className="eyebrow">LOCATION HEALTH</p>
          <h2>SolarWinds location groups</h2>
          <small>
            Current regular groups · select a location to view its unique
            devices
          </small>
        </div>
        <div className="table-tools">
          <label className="table-search">
            <input
              aria-label="Filter source groups"
              type="search"
              placeholder="Search location names"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <select
            className="button button--secondary"
            aria-label="Group health"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">All statuses</option>
            {Array.from(new Set(groups.map((group) => group.status))).map(
              (value) => (
                <option key={value}>{value}</option>
              ),
            )}
          </select>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {[
                "Location",
                "Total nodes",
                "Servers",
                "Network devices",
                "Native status",
                "Site Score",
              ].map((label) => (
                <th key={label}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((group) => (
              <tr key={group.id}>
                <td>
                  <button
                    className="site-link"
                    type="button"
                    aria-label={`View group ${group.name}`}
                    onClick={() => onSelect(group.id, group.name)}
                  >
                    {group.name}
                  </button>
                </td>
                <td>{number(group.total)}</td>
                <td>{number(group.servers)}</td>
                <td>{number(group.network)}</td>
                <td>{group.status}</td>
                <td title={group.scoreReason}>{group.score ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <div className="empty-state" role="status">
            {loading
              ? "Loading location groups…"
              : !available
                ? "Location snapshot unavailable. Reload snapshot to retry."
                : "No source groups match these filters."}
          </div>
        )}
      </div>
      <div className="table-footer">
        Showing {rows.length} of {groups.length} location groups
      </div>
    </section>
  );
}
