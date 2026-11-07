import { useState } from "react";
import { time } from "./data";
import type { Snapshot, WorkspaceConfig } from "./data";
import { InventoryPanel } from "./Inventory";
import { LocationTree } from "./LocationTree";

export function LocationScores({ freshness, config, revision, globalSearch }: {
  freshness?: NonNullable<NonNullable<Snapshot["freshness"]>["sources"]>[string];
  config: WorkspaceConfig;
  revision: number;
  globalSearch: string;
}) {
  const [selected, setSelected] = useState<{ id: number; name: string; device?: string } | null>(null);
  return <>
    {selected && <div>
      <button type="button" className="button button--secondary" onClick={() => setSelected(null)}>Back to hierarchy</button>
      <InventoryPanel key={`${selected.id}-${selected.device ?? ""}`} config={config} revision={revision} globalSearch={selected.device ?? globalSearch} groupId={selected.id} groupName={selected.name} selectionLabel={selected.name} />
    </div>}
    <section className={`panel${selected ? "" : " inventory-panel"}`} hidden={!!selected}>
      <div className="location-score-context"><p>SolarWinds: {freshness?.status ?? "Unavailable"} · {time(freshness?.last_synchronized_at)}{freshness?.last_attempt_status && freshness.last_attempt_status !== "SUCCESS" ? ` · latest refresh ${freshness.last_attempt_status}` : ""}</p></div>
      <LocationTree key={revision} revision={revision} onOpen={(id, name, device) => setSelected({ id, name, device })} />
    </section>
  </>;
}
