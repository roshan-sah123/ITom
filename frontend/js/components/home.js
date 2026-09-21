/**
 * Module 0: ITOM Portal Master Home Page & Module Launcher
 * Live telemetry reconciliation across all enterprise domains
 */
import { itomApi } from '../api.js';
import { formatNumber, formatPercent } from '../utils.js';

export async function renderHome() {
  await loadHomeTelemetry();
  initHomeCardTriggers();
}

async function loadHomeTelemetry() {
  const results = await Promise.allSettled([
    itomApi.getSolarWindsSummary(),
    itomApi.getIntuneSummary(),
    itomApi.getCmdbSummary(),
    itomApi.getSyncStatus(),
  ]);

  const valueAt = (index) => results[index].status === 'fulfilled' ? results[index].value : null;
  const swSummary = valueAt(0);
  const epSummary = valueAt(1);
  const cmdbSummary = valueAt(2);
  const syncStatus = valueAt(3);

  const swMetrics = swSummary?.metrics || {};
  const epMetrics = epSummary?.metrics || {};
  const cmdbMetrics = cmdbSummary?.metrics || cmdbSummary || {};
  const numeric = (value) => Number.isFinite(Number(value)) ? Number(value) : null;
  const numberText = (value) => value === null ? '—' : formatNumber(value);
  const percentageText = (value) => value === null ? '—' : `${value.toFixed(1)}%`;

  const totalServers = numeric(swMetrics.total_server_nodes);
  const availability = numeric(swMetrics.availability_pct);
  const activeAlerts = ['Warning', 'Critical', 'Down']
    .reduce((count, label) => count + (numeric(swSummary?.status_breakdown?.[label]) || 0), 0);

  const totalEndpoints = numeric(epMetrics.total_managed_devices);
  const epCompRate = numeric(epMetrics.compliance_rate_pct);
  const medianStorage = numeric(epMetrics.median_device_storage_used_pct);
  const totalCis = numeric(cmdbMetrics.total_cis);

  // Update banner stats. Campus locations are not inferred from aggregate endpoints.
  const bEp = document.getElementById('homeStatEndpoints');
  const bSw = document.getElementById('homeStatServers');
  const bSites = document.getElementById('homeStatSites');
  const bCi = document.getElementById('homeStatCis');

  if (bEp) bEp.textContent = numberText(totalEndpoints);
  if (bSw) bSw.textContent = numberText(totalServers);
  if (bSites) bSites.textContent = '—';
  if (bCi) bCi.textContent = numberText(totalCis);

  const cardInfraStat = document.getElementById('homeCardInfraStat');
  const cardDexStat = document.getElementById('homeCardDexStat');
  const cardCmdbStat = document.getElementById('homeCardCmdbStat');
  const cardSyncStat = document.getElementById('homeCardSyncStat');

  if (cardInfraStat) {
    cardInfraStat.innerHTML = `
      <span style="color: var(--text-muted);">Availability: <strong style="color: var(--status-healthy);">${percentageText(availability)}</strong></span>
      <span style="color: var(--text-muted);">Unavailable: <strong style="color: var(--status-warning);">${swSummary ? formatNumber(activeAlerts) : '—'}</strong></span>
    `;
  }

  if (cardDexStat) {
    cardDexStat.innerHTML = `
      <span style="color: var(--text-muted);">Compliance: <strong style="color: var(--status-healthy);">${percentageText(epCompRate)}</strong></span>
      <span style="color: var(--text-muted);">Median storage: <strong style="color: var(--accent-intune);">${percentageText(medianStorage)}</strong></span>
    `;
  }

  if (cardCmdbStat) {
    cardCmdbStat.innerHTML = `
      <span style="color: var(--text-muted);">Inventory: <strong style="color: var(--accent-cmdb);">${numberText(totalCis)} CIs</strong></span>
      <span style="color: var(--text-muted);">Source: <strong style="color: var(--accent-cmdb);">${cmdbSummary?.data_source || 'not reported'}</strong></span>
    `;
  }

  if (cardSyncStat) {
    const state = syncStatus?.sync_state || 'UNAVAILABLE';
    const cadence = numeric(syncStatus?.cadence_seconds);
    const color = state === 'HEALTHY' ? 'var(--status-healthy)' : 'var(--status-warning)';
    cardSyncStat.innerHTML = `
      <span style="color: var(--text-muted);">Engine: <strong style="color: ${color};">${state}</strong></span>
      <span style="color: var(--text-muted);">Cadence: <strong style="color: var(--text-primary);">${cadence === null ? 'not reported' : `${cadence}s`}</strong></span>
    `;
  }
}

function initHomeCardTriggers() {
  document.querySelectorAll('.btn-card-launch[data-target-view]').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetView = btn.dataset.targetView;
      if (targetView && typeof window.navigateToView === 'function') {
        window.navigateToView(targetView);
      }
    });
  });
}
