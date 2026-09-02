/**
 * ITOM Portal & Operations Analytics - Constants & Design Tokens
 * 
 * Provides centralized tokens, theme colors, tab definitions, API endpoints,
 * and mathematical invariant definitions with zero-build browser compatibility.
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    const exports = factory();
    root.ITOM_CONSTANTS = exports;
    Object.assign(root, exports);
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // Visual Design Tokens
  const THEME = Object.freeze({
    BG_DARK: '#0B0B0B',
    CARD_BG: '#141414',
    CARD_BORDER: '#222222',
    TEXT_LIGHT: '#E5E7EB',
    TEXT_MUTED: '#9CA3AF',
    ACCENT_ORANGE: '#F97316',
    ACCENT_GREEN: '#10B981',
    ACCENT_WARNING: '#F59E0B',
    ACCENT_CRITICAL: '#EF4444',
    ACCENT_BLUE: '#3B82F6',
    ACCENT_PURPLE: '#8B5CF6',
  });

  // Chart Palette Mapping
  const CHART_PALETTES = Object.freeze({
    COMPLIANCE: {
      compliant: '#10B981',
      noncompliant: '#EF4444',
      configManager: '#3B82F6',
      unknown: '#6B7280',
      inGracePeriod: '#F59E0B',
    },
    HEALTH_TIERS: {
      High: '#10B981',
      Medium: '#F59E0B',
      Low: '#EF4444',
    },
    STATUS_TIERS: {
      Up: '#10B981',
      Down: '#EF4444',
      Warning: '#F59E0B',
      Critical: '#DC2626',
      Unmanaged: '#6B7280',
    },
    MANUFACTURERS: {
      Dell: '#0284C7',
      HP: '#0D9488',
      Lenovo: '#E11D48',
      Apple: '#A855F7',
      Other: '#64748B',
    }
  });

  // Telemetry Invariant Target Figures
  const INVARIANTS = Object.freeze({
    INTUNE_TOTAL_DEVICES: 25987,
    SOLARWINDS_TOTAL_NODES: 1548,
    CMDB_TOTAL_CIS: 1548,
    CMDB_NETWORK_CIS: 364,
  });

  // Tab & Router Definitions
  const VALID_TABS = Object.freeze(['overview', 'intune', 'solarwinds', 'cmdb', 'network', 'dex']);
  const DEFAULT_TAB = 'overview';

  // API Endpoints and Static Fallbacks
  const ENDPOINTS = Object.freeze({
    INTUNE_SUMMARY: 'data/intune_summary.json',
    SOLARWINDS_SUMMARY: 'data/solarwinds_summary.json',
    CMDB_SUMMARY: 'data/cmdb_summary.json',
    EXECUTIVE_DIGEST: 'data/executive_digest.json',
    API_CMDB_SUMMARY: '/api/cmdb/summary',
    API_CMDB_CIS: '/api/cmdb/cis',
  });

  // Pagination Configuration
  const PAGINATION = Object.freeze({
    DEFAULT_PAGE_SIZE: 25,
    PAGE_SIZE_OPTIONS: [10, 25, 50, 100],
  });

  // Storage Math Constants
  const STORAGE = Object.freeze({
    BYTES_PER_KB: 1024,
    BYTES_PER_MB: 1024 * 1024,
    BYTES_PER_GB: 1024 * 1024 * 1024,
    BYTES_PER_TB: 1024 * 1024 * 1024 * 1024,
  });

  return {
    THEME,
    CHART_PALETTES,
    INVARIANTS,
    VALID_TABS,
    DEFAULT_TAB,
    ENDPOINTS,
    PAGINATION,
    STORAGE,
  };
});
