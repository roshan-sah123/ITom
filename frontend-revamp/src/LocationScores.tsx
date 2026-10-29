import { useState } from "react";
import { downloadCsv, number, time } from "./data";
import type { buildPortalModel } from "./data";
import { componentEvidence, scorePriority } from "./locationScoreData";
import type { ScoreMode } from "./locationScoreData";

type Rows = ReturnType<typeof buildPortalModel>["locationScores"];
export function LocationScores({ locations: assignedLocations, geographicLocations, available: assignedAvailable, loading: assignedLoading, geographicAvailable, geographicLoading }: { locations: Rows; geographicLocations: Rows; available: boolean; loading: boolean; geographicAvailable: boolean; geographicLoading: boolean }) {
  const [mode, setMode] = useState<ScoreMode>("combined");
  const [scope, setScope] = useState<"geographic" | "assigned">("geographic");
  const locations = scope === "geographic" ? geographicLocations : assignedLocations;
  const available = scope === "geographic" ? geographicAvailable : assignedAvailable;
  const loading = scope === "geographic" ? geographicLoading : assignedLoading;
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [level, setLevel] = useState("");
  const rows = locations.filter((row) => row.name.toLowerCase().includes(search.toLowerCase()) && (!status || (row.scores[mode]?.status ?? "unavailable") === status) && (!level || row.level === level)).sort((a, b) => {
    const rank = (row: Rows[number]) => row.scores[mode]?.value == null ? 3 : ({ critical: 0, warning: 1, healthy: 2 } as Record<string, number>)[row.scores[mode]?.status ?? ""] ?? 3;
    return rank(a) - rank(b) || a.name.localeCompare(b.name);
  });
  const count = (state: string) => rows.filter((row) => row.scores[mode]?.value == null ? state === "unavailable" : row.scores[mode]?.status === state).length;
  const sources = locations[0]?.freshness;
  const sourceText = (name: "INTUNE" | "SOLARWINDS") => {
    const source = sources?.[name];
    if (!source) return "Unavailable";
    const attempt = source.last_attempt_status && source.last_attempt_status !== "SUCCESS" ? ` · latest refresh ${source.last_attempt_status}` : "";
    return `${source.status ?? "UNKNOWN"} · ${time(source.last_synchronized_at)}${attempt}`;
  };
  const exportRows = () => downloadCsv("location-site-scores.csv", ["Location ID", "Location", "Level", "Mapping scope", "Geographic match level", "Score mode", "Score", "Status", "Suggested priority", "Score reason", "Intune endpoints", "SolarWinds nodes", "Compliance evidence", "Node health evidence", "Check-in evidence", "Intune freshness", "Intune last sync", "SolarWinds freshness", "SolarWinds last sync", "Assessment time", "Policy version"], rows.map((row) => {
    const score = row.scores[mode];
    return [row.id, row.name, row.level ?? "", scope, row.match_level ?? "", mode, score?.value == null ? "" : String(score.value), score?.value == null ? "unavailable" : score.status ?? "unknown", scorePriority(mode, score), score?.reason ?? "", String(row.endpoints), row.nodes == null ? "" : String(row.nodes), componentEvidence(row.components?.compliance), componentEvidence(row.components?.node_status), componentEvidence(row.components?.recent_checkins), row.freshness?.INTUNE?.status ?? "", row.freshness?.INTUNE?.last_synchronized_at ?? "", row.freshness?.SOLARWINDS?.status ?? "", row.freshness?.SOLARWINDS?.last_synchronized_at ?? "", row.as_of ?? "", row.policy_version ?? ""];
  }));
  return <section className="panel inventory-panel" aria-busy={loading}>
    <div className="panel__header overview-header"><div><p className="eyebrow">LOCATION HEALTH</p><h2>Location site scores</h2>
      <small>Combined critical: suggested P1, warning: suggested P2. Review evidence and business impact before raising a ticket.</small></div>
      <div className="table-tools">
        <select className="button button--secondary" aria-label="Mapping scope" value={scope} onChange={(event) => setScope(event.target.value as "geographic" | "assigned")}><option value="geographic">Geographic matches</option><option value="assigned">Assigned locations</option></select>
        <select className="button button--secondary" aria-label="Score type" value={mode} onChange={(event) => setMode(event.target.value as ScoreMode)}><option value="combined">Combined</option><option value="infrastructure">SolarWinds</option><option value="endpoints">Intune</option></select>
        <label className="table-search"><input type="search" aria-label="Search locations" placeholder="Search locations" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <select className="button button--secondary" aria-label="Score status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option><option value="critical">Critical</option><option value="warning">Warning</option><option value="healthy">Healthy</option><option value="unavailable">Unavailable</option></select>
        <select className="button button--secondary" aria-label="Location level" value={level} onChange={(event) => setLevel(event.target.value)}><option value="">All location levels</option>{Array.from(new Set(locations.map((row) => row.level).filter((value): value is string => !!value))).sort().map((value) => <option key={value} value={value}>{value}</option>)}</select>
        <button type="button" className="button button--secondary" disabled={!available || !rows.length} onClick={exportRows}>Export filtered CSV</button>
      </div></div>
    <div className="location-score-context" aria-live="polite"><div className="location-score-summary"><span><strong>{count("critical")}</strong> Critical</span><span><strong>{count("warning")}</strong> Warning</span><span><strong>{count("healthy")}</strong> Healthy</span><span><strong>{count("unavailable")}</strong> Unavailable</span></div><p>{scope === "geographic" ? "Geographic matches use city, country or region evidence; nodes can appear in multiple rows and a match does not confirm the same office." : "Assigned locations use existing device location assignments."}</p><p>Intune: {sourceText("INTUNE")} &nbsp;·&nbsp; SolarWinds: {sourceText("SOLARWINDS")}</p><p>Combined = 40% compliance + 35% monitored nodes up + 25% recent check-ins. Source snapshots must be fresh with sufficient field coverage; compare the same location level.</p></div>
    <div className="table-wrap"><table><thead><tr><th>Location</th><th>Level</th><th>Match basis</th><th>Intune endpoints</th><th>SolarWinds nodes</th><th>Intune compliance</th><th>Nodes up</th><th>Recent check-ins</th><th>Score</th><th>Status / reason</th></tr></thead>
      <tbody>{rows.map((row) => { const score = row.scores[mode]; const state = score?.value == null ? "unavailable" : score.status ?? "unknown"; return <tr key={row.id}>
        <td><strong>{row.name}</strong></td><td>{row.level ?? "—"}</td><td>{scope === "geographic" ? `Geographic ${row.match_level ?? "unknown"}` : "Assigned"}</td><td>{number(row.endpoints)}</td><td>{number(row.nodes)}</td><td>{componentEvidence(row.components?.compliance)}</td><td>{componentEvidence(row.components?.node_status)}</td><td>{componentEvidence(row.components?.recent_checkins)}</td><td>{score?.value ?? "Unavailable"}</td>
        <td><span className={`status status--${state}`}><span className="status__dot" />{state}</span>{scorePriority(mode, score) !== "—" && <strong> · Suggested {scorePriority(mode, score)}</strong>}{score?.reason && <div>{score.reason}</div>}</td>
      </tr>; })}</tbody></table>
      {!rows.length && <div className="empty-state" role="status">{loading ? "Loading location scores…" : !available ? "Location scores unavailable. Reload snapshot to retry." : "No locations match these filters."}</div>}</div>
    <div className="table-footer">Showing {rows.length} of {locations.length} reporting locations · location levels can differ</div>
  </section>;
}
