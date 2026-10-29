import { useState } from "react";
import { number } from "./data";
import type { buildPortalModel } from "./data";

type Groups = ReturnType<typeof buildPortalModel>["locations"];
export function GroupSelector({
  groups,
  infrastructureGroups,
  intuneScores,
  infrastructureAvailable,
  intuneAvailable,
  infrastructureLoading,
  intuneLoading,
  available,
  loading,
  onSelect,
}: {
  groups: Groups;
  infrastructureGroups: Groups;
  intuneScores: ReturnType<typeof buildPortalModel>["intuneLocations"];
  infrastructureAvailable: boolean;
  intuneAvailable: boolean;
  infrastructureLoading: boolean;
  intuneLoading: boolean;
  available: boolean;
  loading: boolean;
  onSelect: (id: number, name: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [mode, setMode] = useState<"combined" | "infrastructure" | "endpoints">("combined");
  const selectedGroups = mode === "infrastructure" ? infrastructureGroups : groups;
  const currentAvailable = mode === "endpoints" ? intuneAvailable : mode === "infrastructure" ? infrastructureAvailable : available;
  const currentLoading = mode === "endpoints" ? intuneLoading : mode === "infrastructure" ? infrastructureLoading : loading;
  const candidates = mode === "endpoints" ? intuneScores : selectedGroups;
  const rows = selectedGroups.filter(
    (group) =>
      group.name.toLowerCase().includes(search.toLowerCase()) &&
      (!status || group.scoreStatus === status),
  );
  const endpointRows = intuneScores.filter((row) => row.name.toLowerCase().includes(search.toLowerCase()) && (!status || row.scoreStatus === status));
  return (
    <section className="panel inventory-panel" aria-busy={currentLoading}>
      <div className="panel__header overview-header">
        <div>
          <p className="eyebrow">LOCATION HEALTH</p>
          <h2>{mode === "combined" ? "Combined site scores" : mode === "infrastructure" ? "SolarWinds site scores" : "Intune location scores"}</h2>
          <small>
            {mode === "endpoints" ? "Intune reporting locations; these differ from SolarWinds groups." : mode === "infrastructure" ? "SolarWinds regular groups; monitored node health." : "SolarWinds groups and approved Intune locations. Critical: P1, warning: P2 for review."} Unavailable scores require mapping or data review.
          </small>
        </div>
        <div className="table-tools">
          <select className="button button--secondary" aria-label="Score type" value={mode} onChange={(event) => { setMode(event.target.value as typeof mode); setStatus(""); }}>
            <option value="combined">Combined</option>
            <option value="infrastructure">SolarWinds</option>
            <option value="endpoints">Intune</option>
          </select>
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
            aria-label="Score status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">All statuses</option>
            {Array.from(new Set(candidates.map((group) => group.scoreStatus))).map(
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
                ...(mode === "endpoints" ? ["Intune endpoints"] : ["Total nodes", "Servers", "Network devices", "Native status"]),
                "Score",
                "Score status / ticket guidance",
                ...(mode === "combined" ? ["Intune mapping"] : []),
              ].map((label) => (
                <th key={label}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {mode === "endpoints" ? endpointRows.map((row) => (
              <tr key={row.id}><td>{row.name}</td><td>{number(row.endpoints)}</td><td>{row.score ?? "Unavailable"}</td>
                <td><strong>{row.scoreStatus}</strong><div>{row.scoreReason}</div></td></tr>
            )) : rows.map((group) => (
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
                <td>{group.score ?? "Unavailable"}</td>
                <td>
                  <strong>{group.scoreStatus}{mode === "combined" && group.scoreStatus === "Critical" ? " · P1" : mode === "combined" && group.scoreStatus === "Warning" ? " · P2" : ""}</strong>
                  <div>{group.scoreReason}</div>
                </td>
                {mode === "combined" && <td>{group.mappingName ?? group.mappingStatus}{group.mappingName && group.intuneEndpoints != null ? ` · ${number(group.intuneEndpoints)} endpoints` : ""}</td>}
              </tr>
            ))}
          </tbody>
        </table>
        {!(mode === "endpoints" ? endpointRows.length : rows.length) && (
          <div className="empty-state" role="status">
            {currentLoading
              ? "Loading location groups…"
              : !currentAvailable
                ? "Location snapshot unavailable. Reload snapshot to retry."
                : "No source groups match these filters."}
          </div>
        )}
      </div>
      <div className="table-footer">
        Showing {mode === "endpoints" ? endpointRows.length : rows.length} of {candidates.length} {mode === "endpoints" ? "Intune locations" : "location groups"}
      </div>
    </section>
  );
}
