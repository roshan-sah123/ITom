import { itomApi } from '../api.js?v=4';

let pollStarted = false;
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));
const dateText = (value) => value ? new Date(value).toLocaleString() : 'Not recorded';

export async function renderSyncSchedule() {
  const facts = document.getElementById('syncScheduleFacts');
  const sources = document.getElementById('syncScheduleSources');
  if (!facts || !sources) return;
  if (!pollStarted) {
    pollStarted = true;
    window.setInterval(() => {
      if (document.getElementById('view-automation')?.classList.contains('active')) renderSyncSchedule();
    }, 30000);
  }
  const button = document.getElementById('runSyncNow');
  const message = document.getElementById('syncActionMessage');
  if (button && !button.dataset.bound) {
    button.dataset.bound = 'true';
    button.addEventListener('click', async () => {
      button.disabled = true;
      if (message) message.textContent = 'Requesting an all-source sync…';
      try {
        const result = await itomApi.triggerSync();
        if (message) message.textContent = result.message || 'Sync request accepted. Refresh this view to see recorded results.';
      } catch {
        if (message) message.textContent = 'Sync request failed. Check that the local API is running, then retry.';
      } finally {
        button.disabled = false;
      }
    });
  }
  try {
    const [scheduler, sync] = await Promise.all([itomApi.getSyncScheduler(), itomApi.getSyncStatus()]);
    const interval = Number(scheduler.interval_seconds);
    const cadence = Number.isFinite(interval) && interval > 0 ? `${Math.round(interval / 60)} minutes` : 'Unavailable';
    const runState = scheduler.running ? 'Running' : scheduler.enabled ? 'Enabled, process not running' : 'Disabled';
    const state = sync.sync_state || 'UNKNOWN';
    facts.innerHTML = `
      <article class="sync-fact"><span>Scheduler</span><strong data-status="${scheduler.running ? 'healthy' : 'warning'}">${escapeHtml(runState)}</strong></article>
      <article class="sync-fact"><span>Configured cadence</span><strong>${escapeHtml(cadence)}</strong></article>
      <article class="sync-fact"><span>Next scheduled run</span><strong>${escapeHtml(dateText(scheduler.next_run))}</strong></article>
      <article class="sync-fact"><span>Latest source state</span><strong data-status="${state.toLowerCase()}">${escapeHtml(state)}</strong><small>${escapeHtml(sync.state_reason || '')}</small></article>
      <article class="sync-fact"><span>Latest recorded sync</span><strong>${escapeHtml(dateText(sync.last_sync))}</strong><small>${sync.age_seconds == null ? 'No successful run recorded' : `Recorded ${Math.floor(sync.age_seconds / 60)} minutes ago`}</small></article>`;
    sources.innerHTML = ['solarwinds', 'intune'].map((key) => {
      const item = sync[key] || {};
      const label = key === 'solarwinds' ? 'SolarWinds Orion' : 'Microsoft Intune';
      const status = item.status || 'UNKNOWN';
      return `<article class="sync-source"><div><h2>${label}</h2><span data-status="${status.toLowerCase()}">${escapeHtml(status)}</span></div><p>Last completed: ${escapeHtml(dateText(item.last_completed))}</p><p>Records reported: ${Number(item.records_processed || 0).toLocaleString()}</p></article>`;
    }).join('');
  } catch {
    facts.innerHTML = '<p class="inline-error">Cannot read scheduler or sync state. The local API may be stopped or unavailable.</p>';
    sources.innerHTML = '';
  }
}
