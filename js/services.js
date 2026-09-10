/**
 * ITOM Portal & Operations Analytics - Telemetry Services & API Layer
 * 
 * Provides unified HTTP fetch wrappers, backend REST API integration,
 * timeout/fallback handling, data loaders, and RFC 4180 CSV export engines
 * with zero-build browser compatibility.
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define(['./constants', './utils'], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('./constants'), require('./utils'));
  } else {
    const exports = factory(root.ITOM_CONSTANTS || {}, root.ITOM_UTILS || {});
    root.ITOM_SERVICES = exports;
    Object.assign(root, exports);
  }
})(typeof self !== 'undefined' ? self : this, function (CONSTANTS, UTILS) {
  'use strict';

  const ENDPOINTS = CONSTANTS.ENDPOINTS || {
    API_BASE: '/api/v1',
    API_INTUNE_SUMMARY: '/api/v1/intune/summary',
    API_INTUNE_DEVICES: '/api/v1/intune/devices',
    API_SOLARWINDS_SUMMARY: '/api/v1/solarwinds/summary',
    API_SOLARWINDS_NODES: '/api/v1/solarwinds/nodes',
    API_CMDB_SUMMARY: '/api/v1/cmdb/summary',
    API_CMDB_CIS: '/api/v1/cmdb/cis',
    API_SYNC_LATEST: '/api/v1/sync/runs/latest',
    INTUNE_SUMMARY: 'data/intune_summary.json',
    SOLARWINDS_SUMMARY: 'data/solarwinds_summary.json',
    CMDB_SUMMARY: 'data/cmdb_summary.json',
    EXECUTIVE_DIGEST: 'data/executive_digest.json',
  };

  /**
   * Fetch JSON resource with timeout and fallback URL handling.
   * 
   * @param {string} url
   * @param {string} [fallbackUrl]
   * @param {number} [timeoutMs=10000]
   * @returns {Promise<any>}
   */
  async function fetchJson(url, fallbackUrl = null, timeoutMs = 10000) {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;

    try {
      const resp = await fetch(url, {
        headers: { 'Accept': 'application/json' },
        signal: controller ? controller.signal : undefined,
      });
      if (timer) clearTimeout(timer);
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status} ${resp.statusText}`);
      }
      return await resp.json();
    } catch (err) {
      if (timer) clearTimeout(timer);
      if (fallbackUrl) {
        try {
          const fallbackResp = await fetch(fallbackUrl, {
            headers: { 'Accept': 'application/json' },
          });
          if (!fallbackResp.ok) {
            throw new Error(`Fallback HTTP ${fallbackResp.status}`);
          }
          return await fallbackResp.json();
        } catch (fallbackErr) {
          throw new Error(`API fetch failed (${err.message}); fallback failed (${fallbackErr.message})`);
        }
      }
      throw err;
    }
  }

  /**
   * Helper to construct query string from parameter map.
   */
  function buildQueryString(params = {}) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== '') {
        q.append(key, String(val));
      }
    });
    const qs = q.toString();
    return qs ? `?${qs}` : '';
  }

  /**
   * Fetch live Microsoft Intune fleet telemetry and compliance summary.
   * @returns {Promise<any>}
   */
  async function fetchIntuneSummary() {
    return fetchJson(ENDPOINTS.API_INTUNE_SUMMARY, ENDPOINTS.INTUNE_SUMMARY);
  }

  /**
   * Fetch paginated Microsoft Intune managed devices from backend API.
   */
  async function fetchIntuneDevices(opts = {}) {
    const validSizes = [10, 25, 50, 100];
    const pageSize = validSizes.includes(Number(opts.pageSize)) ? Number(opts.pageSize) : 25;
    const params = {
      page: opts.page || 1,
      page_size: pageSize,
      search: opts.search || undefined,
      status: opts.status || opts.complianceState || undefined,
      vendor: opts.vendor || undefined,
      sort_by: opts.sortBy || 'name',
      sort_order: opts.sortOrder || 'asc',
    };
    const url = `${ENDPOINTS.API_INTUNE_DEVICES}${buildQueryString(params)}`;
    return fetchJson(url);
  }

  /**
   * Fetch live SolarWinds Orion server node telemetry and health summary.
   * @returns {Promise<any>}
   */
  async function fetchSolarWindsSummary() {
    return fetchJson(ENDPOINTS.API_SOLARWINDS_SUMMARY, ENDPOINTS.SOLARWINDS_SUMMARY);
  }

  /**
   * Fetch paginated SolarWinds Orion server nodes from backend API.
   */
  async function fetchSolarWindsNodes(opts = {}) {
    const validSizes = [10, 25, 50, 100];
    const pageSize = validSizes.includes(Number(opts.pageSize)) ? Number(opts.pageSize) : 25;
    const params = {
      page: opts.page || 1,
      page_size: pageSize,
      search: opts.search || undefined,
      health_tier: opts.healthTier || undefined,
      status: opts.status || undefined,
      vendor: opts.vendor || undefined,
      sort_by: opts.sortBy || 'name',
      sort_order: opts.sortOrder || 'asc',
    };
    const url = `${ENDPOINTS.API_SOLARWINDS_NODES}${buildQueryString(params)}`;
    return fetchJson(url);
  }

  /**
   * Fetch 60+ enterprise campus site telemetry and 24h sparklines from backend API.
   */
  async function fetchSolarWindsSites() {
    return fetchJson('/api/v1/solarwinds/sites');
  }

  /**
   * Fetch 24-hour time-series availability and latency trend history for a specific campus site.
   */
  async function fetchSolarWindsSiteTrend(siteId, hours = 24) {
    return fetchJson(`/api/v1/solarwinds/sites/${encodeURIComponent(siteId)}/trend?hours=${hours}`);
  }

  /**
   * Fetch real-time telemetry engine sync status and freshness.
   */
  async function fetchSyncStatus() {
    return fetchJson('/api/v1/sync/status');
  }

  /**
   * Fetch live Enterprise CMDB aggregated fleet summary.
   * @returns {Promise<any>}
   */
  async function fetchCmdbSummary() {
    return fetchJson(ENDPOINTS.API_CMDB_SUMMARY, ENDPOINTS.CMDB_SUMMARY);
  }

  /**
   * Fetch paginated Enterprise CMDB Configuration Items from backend API.
   */
  async function fetchCmdbCis(opts = {}) {
    const validSizes = [10, 25, 50, 100];
    const pageSize = validSizes.includes(Number(opts.pageSize)) ? Number(opts.pageSize) : 25;
    const params = {
      page: opts.page || 1,
      page_size: pageSize,
      search: opts.search || undefined,
      source_system: opts.sourceSystem || undefined,
      ci_type: opts.ciType || undefined,
      vendor: opts.vendor || undefined,
      health_tier: opts.healthTier || undefined,
      status: opts.status || undefined,
      sort_by: opts.sortBy || 'name',
      sort_order: opts.sortOrder || 'asc',
    };
    const url = `${ENDPOINTS.API_CMDB_CIS}${buildQueryString(params)}`;
    return fetchJson(url);
  }

  /**
   * Fetch latest telemetry synchronization status and timestamps.
   * @returns {Promise<any>}
   */
  async function fetchLatestSyncRun() {
    return fetchJson(ENDPOINTS.API_SYNC_LATEST, null, 5000);
  }

  /**
   * Backward-compatible telemetry loaders (calls live API first, fallback to static snapshots)
   */
  async function loadIntuneTelemetry() {
    return fetchIntuneSummary();
  }

  async function loadSolarWindsTelemetry() {
    return fetchSolarWindsSummary();
  }

  async function loadCmdbTelemetry() {
    return fetchCmdbSummary();
  }

  async function loadExecutiveDigest() {
    return fetchJson(ENDPOINTS.EXECUTIVE_DIGEST, '/data/executive_digest.json');
  }

  async function loadAllTelemetry() {
    const results = await Promise.allSettled([
      fetchIntuneSummary(),
      fetchSolarWindsSummary(),
      fetchCmdbSummary(),
      fetchLatestSyncRun(),
    ]);

    return {
      intune: results[0].status === 'fulfilled' ? results[0].value : null,
      solarwinds: results[1].status === 'fulfilled' ? results[1].value : null,
      cmdb: results[2].status === 'fulfilled' ? results[2].value : null,
      sync: results[3].status === 'fulfilled' ? results[3].value : null,
    };
  }

  /**
   * Export tabular data as an RFC 4180 compliant CSV file download.
   * Neutralizes formula injection vulnerabilities and emits standard UTF-8 BOM.
   * 
   * @param {string} filename
   * @param {string[]} headers
   * @param {Array<Array<any>>} rows
   */
  function exportToCsv(filename, headers, rows) {
    function escapeCsvCell(val) {
      if (val === null || val === undefined) return '""';
      let str = String(val);
      // Neutralize potential CSV injection / formula execution in spreadsheet tools
      if (/^[=+\-@\t\r]/.test(str)) {
        str = "'" + str;
      }
      return `"${str.replace(/"/g, '""')}"`;
    }

    const headerLine = headers.map(escapeCsvCell).join(',');
    const dataLines = rows.map(row => row.map(escapeCsvCell).join(','));
    const csvContent = '\uFEFF' + [headerLine, ...dataLines].join('\r\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  return {
    fetchJson,
    fetchIntuneSummary,
    fetchIntuneDevices,
    fetchSolarWindsSummary,
    fetchSolarWindsNodes,
    fetchSolarWindsSites,
    fetchSolarWindsSiteTrend,
    fetchSyncStatus,
    fetchCmdbSummary,
    fetchCmdbCis,
    fetchLatestSyncRun,
    loadIntuneTelemetry,
    loadSolarWindsTelemetry,
    loadCmdbTelemetry,
    loadExecutiveDigest,
    loadAllTelemetry,
    exportToCsv,
  };
});
