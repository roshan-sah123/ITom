import { useState } from "react";
import { downloadCsv, number, time } from "./data";
import type { buildPortalModel, Snapshot } from "./data";

type Groups = ReturnType<typeof buildPortalModel>["locations"];
export function LocationScores({ groups, available, loading, freshness }: { groups: Groups; available: boolean; loading: boolean; freshness?: NonNullable<NonNullable<Snapshot["freshness"]>["sources"]>[string] }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const rows = groups.filter((group) => group.name.toLowerCase().includes(search.toLowerCase()) && (!status || group.scoreStatus === status));
  const exportRows = () => downloadCsv("location-site-scores.csv", ["Location", "Total nodes", "Servers", "Network devices", "Monitored nodes", "Nodes up", "Score", "Status", "Reason", "SolarWinds freshness", "Last sync"], rows.map((row) => [row.name, String(row.total), String(row.servers), String(row.network), row.monitored == null ? "" : String(row.monitored), row.availability, row.score == null ? "" : String(row.score), row.scoreStatus, row.scoreReason, freshness?.status ?? "", freshness?.last_synchronized_at ?? ""]));
  return <section className="panel inventory-panel location-scores-panel" aria-busy={loading}>
    <div className="panel__header overview-header"><div><p className="eyebrow">LOCATION HEALTH</p><h2>SolarWinds site scores</h2><small>SolarWinds groups scored by monitored nodes up. Review the evidence and business impact before taking action.</small></div>
      <div className="table-tools"><label className="table-search"><input type="search" aria-label="Search locations" placeholder="Search locations" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <select className="button button--secondary" aria-label="Score status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option><option>Critical</option><option>Warning</option><option>Healthy</option><option>Unavailable</option></select>
        <button type="button" className="button button--secondary" disabled={!available || !rows.length} onClick={exportRows}>Export filtered CSV</button></div></div>
    <div className="location-score-context"><p>SolarWinds: {freshness?.status ?? "Unavailable"} · {time(freshness?.last_synchronized_at)}{freshness?.last_attempt_status && freshness.last_attempt_status !== "SUCCESS" ? ` · latest refresh ${freshness.last_attempt_status}` : ""}</p><p>Scores require fresh data and sufficient status coverage. Groups can overlap; node counts across groups may include duplicates.</p></div>
    <div className="table-wrap"><table><thead><tr><th>Location</th><th>Total nodes</th><th>Servers</th><th>Network devices</th><th>Monitored nodes</th><th>Nodes up</th><th>Score</th><th>Status / reason</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td><strong>{row.name}</strong></td><td>{number(row.total)}</td><td>{number(row.servers)}</td><td>{number(row.network)}</td><td>{number(row.monitored)}</td><td>{row.availability}</td><td>{row.score ?? "Unavailable"}</td><td><strong>{row.scoreStatus}</strong><div>{row.scoreReason}</div></td></tr>)}</tbody></table>
      {!rows.length && <div className="empty-state" role="status">{loading ? "Loading location scores…" : !available ? "Location scores unavailable. Reload snapshot to retry." : "No locations match these filters."}</div>}</div><div className="table-footer">Showing {rows.length} of {groups.length} SolarWinds groups</div></section>;
}
