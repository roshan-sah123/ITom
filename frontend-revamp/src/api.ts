import { useEffect, useState } from "react";
import type { Snapshot } from "./data";
import { loadSnapshotRoutes } from "./snapshot";

declare global {
  interface Window {
    ITOM_API_BASE?: string;
  }
}

export async function getJson<T>(
  endpoint: string,
  signal?: AbortSignal,
): Promise<T> {
  const base = (window.ITOM_API_BASE || "/api/v1").replace(/\/$/, "");
  const response = await fetch(`${base}${endpoint}`, {
    headers: { Accept: "application/json" },
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(30000)])
      : AbortSignal.timeout(30000),
  });
  if (!response.ok)
    throw new Error(
      `Data unavailable (HTTP ${response.status}). Retry the snapshot.`,
    );
  return response.json();
}

export function usePortalSnapshot(revision: number) {
  const [snapshot, setSnapshot] = useState<Snapshot>({});
  const [pending, setPending] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    const routes = {
      intune: "/intune/summary", solarwinds: "/solarwinds/summary",
      cmdb: "/cmdb/summary", groups: "/solarwinds/groups/overview",
      freshness: "/system/freshness", locations: "/locations",
      geographicScores: "/locations/geographic-scores",
      locationMatches: "/locations/matches",
    };
    setPending(Object.keys(routes));
    setErrors([]);
    setSnapshot({});
    void loadSnapshotRoutes(routes, (route) => getJson(route, controller.signal), (key, value, failed) => {
      if (controller.signal.aborted) return;
      if (failed) setErrors((previous) => [...previous, key]);
      else {
        const payload = value as { data?: unknown };
        const data = ["groups", "combinedGroups", "locations", "geographicScores", "locationMatches"].includes(key) ? payload.data : value;
        setSnapshot((previous) => ({ ...previous, [key]: data }));
      }
      setPending((previous) => previous.filter((item) => item !== key));
    });
    return () => controller.abort();
  }, [revision]);
  return { snapshot, pending, errors };

}

export type CI = {
  id: string;
  name: string;
  source_system: string;
  ip_address?: string;
  status?: string;
  ci_type?: string;
  vendor?: string;
  health_tier?: string;
  serial_number?: string;
  operating_system?: string;
  location?: string;
  canonical_location?: string;
  last_sync_time?: string;
  attributes?: Record<string, unknown>;
};
export type Inventory = {
  items: CI[];
  total: number;
  page: number;
  total_pages: number;
};
export function inventoryCells(item: CI, endpoint: string): string[] {
  const text = (value: unknown) =>
    value == null || value === "" ? "—" : String(value);
  if (endpoint.startsWith("/intune"))
    return [
      item.name,
      text(
        item.attributes?.user_principal_name ?? item.attributes?.primary_user,
      ),
      text(item.operating_system),
      text(item.vendor),
      text(item.status),
      text(item.canonical_location ?? "Unassigned"),
      text(item.serial_number),
    ];
  if (endpoint.startsWith("/solarwinds"))
    return [
      item.name,
      text(item.ip_address),
      text(item.status),
      text(item.ci_type),
      text(item.vendor),
      text(item.health_tier),
      item.attributes?.cpu_load == null ? "—" : `${item.attributes.cpu_load}%`,
    ];
  return [
    item.name,
    item.source_system,
    text(item.ci_type),
    text(item.vendor),
    text(item.canonical_location ?? item.location),
    text(item.health_tier),
    text(item.serial_number),
  ];
}
