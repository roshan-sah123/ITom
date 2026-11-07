import { useEffect, useState } from "react";
import { getJson } from "./api";

type Group = { kind: "group"; group_id: number; name: string; status: string; has_members: boolean };
type Device = { kind: "device"; id: string; name: string; status?: string };
type Members = { data_available: boolean; items: Array<Group | Device> };

function SourceStatus({ status }: { status?: string }) {
  const label = status || "Unknown";
  const tone = label.toLowerCase() === "up" ? "up" : ["critical", "down"].includes(label.toLowerCase()) ? "critical" : label.toLowerCase() === "warning" ? "warning" : "unknown";
  return <span className={`location-tree__status location-tree__status--${tone}`}><span aria-hidden="true" />{label}</span>;
}

function GroupBranch({ group, onOpen }: { group: Group; onOpen: (id: number, name: string, device?: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [items, setItems] = useState<Members["items"] | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!expanded || items) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void getJson<{ data: Members }>(`/solarwinds/groups/${group.group_id}/members`, controller.signal)
      .then(({ data }) => { if (!controller.signal.aborted) { setLoading(false); data.data_available ? setItems(data.items) : setError("Group members are unavailable."); } })
      .catch(() => { if (!controller.signal.aborted) setError("Could not load group members."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [expanded, group.group_id, items, retry]);
  return <li>
    <div className="location-tree__row">
      {group.has_members ? <button className="location-tree__toggle" type="button" aria-expanded={expanded} aria-label={`${expanded ? "Collapse" : "Expand"} ${group.name}`} onClick={() => setExpanded(!expanded)}>{expanded ? "▾" : "▸"}</button> : <span className="location-tree__spacer" />}
      <span className="location-tree__folder" aria-hidden="true">▣</span>
      <button type="button" className="inventory-name inventory-link location-tree__name" aria-label={`Open group ${group.name}`} onClick={() => onOpen(group.group_id, group.name)}>{group.name}</button>
      <SourceStatus status={group.status} />
    </div>
    {expanded && <div className="location-tree__children">
      {loading && <p role="status">Loading members…</p>}
      {error && <p role="status">{error} <button type="button" className="text-button" onClick={() => setRetry(retry + 1)}>Retry</button></p>}
      {items && (items.length ? <ul>{items.map(item => item.kind === "group"
        ? <GroupBranch key={`group-${item.group_id}`} group={item} onOpen={onOpen} />
        : <li key={`device-${item.id}`}><div className="location-tree__row"><span className="location-tree__spacer" /><span aria-hidden="true">•</span><button type="button" className="inventory-name inventory-link location-tree__name" onClick={() => onOpen(group.group_id, group.name, item.name)}>{item.name}</button><SourceStatus status={item.status} /></div></li>)}</ul> : <p>No direct members in this group.</p>)}
    </div>}
  </li>;
}

export function LocationTree({ revision, onOpen }: { revision: number; onOpen: (id: number, name: string, device?: string) => void }) {
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setGroups(null); setError("");
    void getJson<{ data: Members }>("/solarwinds/groups", controller.signal)
      .then(({ data }) => { if (!controller.signal.aborted) data.data_available ? setGroups(data.items.filter((item): item is Group => item.kind === "group")) : setError("SolarWinds group hierarchy is unavailable."); })
      .catch(() => { if (!controller.signal.aborted) setError("Could not load the SolarWinds hierarchy."); });
    return () => controller.abort();
  }, [revision, retry]);
  return <div className="location-tree" aria-label="SolarWinds group hierarchy">
    <h3>SolarWinds inventory hierarchy</h3>
    <p>Expand a group to see its direct members. Select a group to view all its devices, including subgroups. Statuses are reported by SolarWinds.</p>
    {error ? <p role="status">{error} <button type="button" className="text-button" onClick={() => setRetry(retry + 1)}>Retry</button></p> : groups ? (groups.length ? <ul>{groups.map(group => <GroupBranch key={group.group_id} group={group} onOpen={onOpen} />)}</ul> : <p>No SolarWinds groups in the snapshot.</p>) : <p role="status">Loading group hierarchy…</p>}
  </div>;
}
