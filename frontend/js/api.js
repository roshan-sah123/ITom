/**
 * Coforge ITOM Portal - Central REST API Client
 * Connects to the same-origin FastAPI backend by default.
 * Enforces Zero-Hallucination telemetry contracts with graceful degradation
 */

const API_BASE = window.ITOM_API_BASE || '/api/v1';

async function fetchJson(endpoint, options = {}) {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        'Accept': 'application/json',
        ...(options.headers || {})
      }
    });
    if (!res.ok) {
      throw new Error(`API error ${res.status}: ${res.statusText} (${url})`);
    }
    return await res.json();
  } catch (err) {
    console.error(`[API Fetch Failure] ${url}:`, err);
    throw err;
  }
}

let pendingLocations = null;
function getLocations() {
  if (!pendingLocations) pendingLocations = fetchJson('/locations').finally(() => { pendingLocations = null; });
  return pendingLocations;
}

export const itomApi = {
  getLocations,
  getLocationDevices: (id, params = {}) => fetchJson(`/locations/${encodeURIComponent(id)}/devices?${new URLSearchParams(params)}`),
  getLocationHistory: id => fetchJson(`/locations/${encodeURIComponent(id)}/history`),
  // SolarWinds Orion (Hybrid Servers & Campus Sites)
  getSolarWindsSummary: () => fetchJson('/solarwinds/summary'),
  getSolarWindsNodes: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchJson(`/solarwinds/nodes?${query}`);
  },
  getSolarWindsNetworkDevices: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchJson(`/solarwinds/network-devices?${query}`);
  },
  getSolarWindsSites: () => fetchJson('/solarwinds/sites'),
  getSolarWindsSiteTrend: (siteId, hours = 24) => fetchJson(`/solarwinds/sites/${encodeURIComponent(siteId)}/trend?hours=${hours}`),

  // Microsoft Intune (Digital Workplace Endpoints)
  getIntuneSummary: () => fetchJson('/intune/summary'),
  getIntuneForecast: () => fetchJson('/intune/forecast'),
  getIntuneDevices: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchJson(`/intune/devices?${query}`);
  },

  // CMDB Configuration Items
  getCmdbSummary: () => fetchJson('/cmdb/summary'),
  getCmdbCis: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchJson(`/cmdb/cis?${query}`);
  },
  getCiById: (ciId) => fetchJson(`/cmdb/cis/${encodeURIComponent(ciId)}`),
  getCiHistory: (ciId, limit = 50) => fetchJson(`/cmdb/cis/${encodeURIComponent(ciId)}/history?limit=${limit}`),

  // Telemetry Sync Engine
  getSyncStatus: () => fetchJson('/sync/status'),
  getSyncScheduler: () => fetchJson('/sync/scheduler'),
  triggerSync: () => fetchJson('/sync/trigger?source_system=ALL', { method: 'POST' }),
  getFreshness: () => fetchJson('/system/freshness'),
  getReadiness: () => fetchJson('/ready'),
  getSyncRuns: (page = 1, pageSize = 25) => fetchJson(`/sync/runs?page=${page}&page_size=${pageSize}`),
};
