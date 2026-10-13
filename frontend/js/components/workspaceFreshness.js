/** Source synchronization evidence, independently of inventory/analytics loading. */
import { itomApi } from '../api.js';
import { escapeHtml } from '../utils.js';

const sourcesByView = { infrastructure: ['SOLARWINDS'], endpoints: ['INTUNE'], cmdb: ['INTUNE', 'SOLARWINDS'] };
const names = { SOLARWINDS: 'SolarWinds Orion', INTUNE: 'Microsoft Intune' };
let requestVersion = 0;

function age(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return 'Age unavailable';
  if (seconds < 60) return 'Less than a minute old';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m old`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h old`;
  return `${Math.floor(seconds / 86400)}d old`;
}

function timestamp(value) {
  if (!value) return null;
  const normalized = typeof value === 'string' && /T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value) ? `${value}Z` : value;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleString();
}

function sourceRow(source, freshness, sync) {
  const evidence = freshness?.sources?.[source];
  const state = ['FRESH', 'STALE', 'UNKNOWN'].includes(evidence?.status) ? evidence.status : 'UNAVAILABLE';
  const label = { FRESH: 'Fresh', STALE: 'Stale', UNKNOWN: 'Unknown', UNAVAILABLE: 'Freshness unavailable' }[state];
  const observed = timestamp(evidence?.last_synchronized_at);
  const snapshot = observed ? `Snapshot updated ${observed} · ${age(evidence.age_seconds)}`
    : state === 'UNKNOWN' ? 'No successful sync recorded' : 'Snapshot time unavailable';
  const attempt = sync?.[source.toLowerCase()]?.status;
  const outcome = typeof attempt === 'string' ? attempt.toUpperCase() : 'UNAVAILABLE';
  const warning = ['FAILED', 'PARTIAL'].includes(outcome);
  const outcomeText = outcome === 'UNAVAILABLE' ? 'Latest sync outcome unavailable'
    : outcome === 'UNKNOWN' ? 'Latest sync: no attempt recorded'
    : `Latest sync: ${outcome.toLowerCase()}`;
  const note = warning ? observed ? 'Showing last successful snapshot.' : 'No successful snapshot confirmed.' : '';
  return `<div class="workspace-source-evidence" data-source="${source}" data-status="${state.toLowerCase()}" data-attempt="${warning ? 'warning' : 'normal'}">
    <div class="workspace-source-title"><strong>${names[source]}</strong><span class="evidence-state">${label}</span></div>
    <p>${escapeHtml(snapshot)}</p><p class="sync-attempt">${escapeHtml(outcomeText)}${note ? ` · ${note}` : ''}</p></div>`;
}

export function initWorkspaceFreshness(reload) {
  document.querySelectorAll('.workspace-freshness-reload').forEach(button => {
    button.addEventListener('click', reload);
  });
}

export async function renderWorkspaceFreshness(view) {
  // Increment even on unrelated navigation, invalidating pending evidence.
  const version = ++requestVersion;
  const sources = sourcesByView[view];
  if (!sources) return;
  const panel = document.getElementById(`workspaceFreshness-${view}`);
  const rows = panel?.querySelector('.workspace-freshness-rows');
  const compact = document.getElementById(`inventoryFreshness-${view}`);
  if (!rows) return;
  const button = panel.querySelector('button');
  button.disabled = true;
  rows.textContent = 'Checking source evidence…';
  if (compact) compact.textContent = 'Checking source evidence…';
  const results = await Promise.allSettled([itomApi.getFreshness(), itomApi.getSyncStatus()]);
  if (version !== requestVersion) return;
  const [freshness, sync] = results.map(result => result.status === 'fulfilled' ? result.value : null);
  const content = sources.map(source => sourceRow(source, freshness, sync)).join('');
  rows.innerHTML = content;
  if (compact) compact.innerHTML = content;
  button.disabled = false;
}
