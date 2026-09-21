/**
 * Coforge ITOM Portal - Central REST API Client
 * Connects to live FastAPI backend at http://localhost:8000/api/v1
 * Enforces Zero-Hallucination telemetry contracts with graceful degradation
 */

// Use the local API when the static frontend runs on another localhost port.
// Deployed environments continue to use the same-origin reverse proxy.
const isLocalStaticHost =
  ['localhost', '127.0.0.1'].includes(window.location.hostname) &&
  window.location.port !== '8000';
const defaultApiBase = isLocalStaticHost
  ? 'http://127.0.0.1:8000/api/v1'
  : '/api/v1';
const API_BASE = (window.ITOM_API_BASE || defaultApiBase).replace(/\/$/, '');

export class TelemetryApiError extends Error {
  constructor(message, { status, payload, url } = {}) {
    super(message);
    this.name = 'TelemetryApiError';
    this.status = status;
    this.payload = payload;
    this.url = url;
  }
}

export class TelemetryDataUnavailableError extends TelemetryApiError {
  constructor(payload, url) {
    super(payload?.detail || 'Telemetry data has not been ingested for this domain.', {
      status: 503,
      payload,
      url,
    });
    this.name = 'TelemetryDataUnavailableError';
  }
}

export async function fetchJson(endpoint, options = {}) {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.headers || {}),
    },
  });

  let payload = null;
  try {
    payload = await res.json();
  } catch {
    // The backend normally sends JSON. Preserve a useful status error if a proxy does not.
  }

  if (res.status === 503) throw new TelemetryDataUnavailableError(payload, url);
  if (!res.ok) {
    throw new TelemetryApiError(`Telemetry API returned ${res.status}.`, {
      status: res.status,
      payload,
      url,
    });
  }
  return payload;
}

export const itomApi = {
  // SolarWinds Orion (Hybrid Servers & Campus Sites)
  getSolarWindsSummary: () => fetchJson('/solarwinds/summary'),
  getSolarWindsNodes: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchJson(`/solarwinds/nodes?${query}`);
  },
  getSolarWindsSites: () => fetchJson('/solarwinds/sites'),
  getSolarWindsSiteTrend: (siteId, hours = 24) => fetchJson(`/solarwinds/sites/${encodeURIComponent(siteId)}/trend?hours=${hours}`),

  // Microsoft Intune (Digital Workplace Endpoints)
  getIntuneSummary: () => fetchJson('/intune/summary'),
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
  getSyncRuns: (page = 1, pageSize = 25) => fetchJson(`/sync/runs?page=${page}&page_size=${pageSize}`),
};
