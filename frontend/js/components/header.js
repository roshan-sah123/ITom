/** Compact, source-backed freshness and sync controls. */
import { itomApi } from '../api.js?v=4';

const formatTimestamp = (value) => value
  ? new Intl.DateTimeFormat(undefined, { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
  : 'Unavailable';

export function initHeader() {
  const syncText = document.getElementById('headerSyncText');
  const solarwindsText = document.getElementById('freshnessSolarWinds');
  const intuneText = document.getElementById('freshnessIntune');

  async function updateFreshness() {
    try {
      const [freshness, sync] = await Promise.all([
        itomApi.getFreshness(),
        itomApi.getSyncStatus().catch(() => ({}))
      ]);
      const sources = freshness.sources || {};
      setSource(solarwindsText, 'SolarWinds', sources.SOLARWINDS);
      setSource(intuneText, 'Intune', sources.INTUNE);

      const state = sync.sync_state || freshness.overall_status || 'UNKNOWN';
      const label = state === 'HEALTHY' || state === 'FRESH'
        ? 'Success'
        : state === 'FAILED' ? 'Failed' : 'Warning';
      if (syncText) {
        syncText.textContent = `Last Sync Status: ${label}`;
        syncText.dataset.status = label.toLowerCase();
      }
    } catch {
      setSource(solarwindsText, 'SolarWinds');
      setSource(intuneText, 'Intune');
      if (syncText) {
        syncText.textContent = 'Last Sync Status: Failed';
        syncText.dataset.status = 'failed';
      }
    }
  }

  updateFreshness();
  setInterval(updateFreshness, 10000);

}

function setSource(element, label, source = {}) {
  if (!element) return;
  element.textContent = `${label}: ${formatTimestamp(source.last_synchronized_at)}`;
  element.dataset.status = (source.status || 'UNKNOWN').toLowerCase();
  element.title = source.age_seconds == null ? 'No successful synchronization recorded' : `${source.status} · ${source.age_seconds}s old`;
}
