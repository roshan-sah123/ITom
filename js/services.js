/**
 * ITOM Portal & Operations Analytics - Telemetry Services & API Layer
 * 
 * Provides unified HTTP fetch wrappers, fallback handling, data loaders,
 * and RFC 4180 CSV export engines with zero-build browser compatibility.
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
    INTUNE_SUMMARY: 'data/intune_summary.json',
    SOLARWINDS_SUMMARY: 'data/solarwinds_summary.json',
    CMDB_SUMMARY: 'data/cmdb_summary.json',
    EXECUTIVE_DIGEST: 'data/executive_digest.json',
    API_CMDB_SUMMARY: '/api/cmdb/summary',
  };

  /**
   * Fetch JSON resource with fallback URL handling.
   * 
   * @param {string} url
   * @param {string} [fallbackUrl]
   * @returns {Promise<any>}
   */
  async function fetchJson(url, fallbackUrl = null) {
    try {
      const resp = await fetch(url);
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status} ${resp.statusText}`);
      }
      return await resp.json();
    } catch (err) {
      if (fallbackUrl) {
        const fallbackResp = await fetch(fallbackUrl);
        if (!fallbackResp.ok) {
          throw new Error(`Fallback HTTP ${fallbackResp.status}`);
        }
        return await fallbackResp.json();
      }
      throw err;
    }
  }

  /**
   * Load Microsoft Intune telemetry payload.
   * @returns {Promise<any>}
   */
  async function loadIntuneTelemetry() {
    return fetchJson(ENDPOINTS.INTUNE_SUMMARY, '/data/intune_summary.json');
  }

  /**
   * Load SolarWinds Orion telemetry payload.
   * @returns {Promise<any>}
   */
  async function loadSolarWindsTelemetry() {
    return fetchJson(ENDPOINTS.SOLARWINDS_SUMMARY, '/data/solarwinds_summary.json');
  }

  /**
   * Load Network CMDB telemetry payload.
   * @returns {Promise<any>}
   */
  async function loadCmdbTelemetry() {
    try {
      return await fetchJson(ENDPOINTS.API_CMDB_SUMMARY);
    } catch {
      return fetchJson(ENDPOINTS.CMDB_SUMMARY, '/data/cmdb_summary.json');
    }
  }

  /**
   * Load unified Executive Operational Digest.
   * @returns {Promise<any>}
   */
  async function loadExecutiveDigest() {
    return fetchJson(ENDPOINTS.EXECUTIVE_DIGEST, '/data/executive_digest.json');
  }

  /**
   * Load all telemetry datasets concurrently.
   * @returns {Promise<{intune: any, solarwinds: any, cmdb: any, digest: any}>}
   */
  async function loadAllTelemetry() {
    const results = await Promise.allSettled([
      loadIntuneTelemetry(),
      loadSolarWindsTelemetry(),
      loadCmdbTelemetry(),
      loadExecutiveDigest(),
    ]);

    return {
      intune: results[0].status === 'fulfilled' ? results[0].value : null,
      solarwinds: results[1].status === 'fulfilled' ? results[1].value : null,
      cmdb: results[2].status === 'fulfilled' ? results[2].value : null,
      digest: results[3].status === 'fulfilled' ? results[3].value : null,
    };
  }

  /**
   * Export tabular data as an RFC 4180 compliant CSV file download.
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
      if (/^[=+\-@]/.test(str)) {
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
    loadIntuneTelemetry,
    loadSolarWindsTelemetry,
    loadCmdbTelemetry,
    loadExecutiveDigest,
    loadAllTelemetry,
    exportToCsv,
  };
});
