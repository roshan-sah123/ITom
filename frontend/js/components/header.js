/**
 * Header Component: 64px sticky bar, real-time sync countdown, live status heartbeat
 */
import { itomApi } from '../api.js';
import { formatRelativeTime } from '../utils.js';

export function initHeader({ onSyncTriggered }) {
  const syncPill = document.getElementById('headerSyncPill');
  const syncBtn = document.getElementById('btnTriggerSync');
  const syncText = document.getElementById('headerSyncText');

  let syncCountdown = 600;

  async function updateSyncStatus() {
    try {
      const status = await itomApi.getSyncStatus();
      const ageSeconds = Number.isFinite(Number(status.age_seconds)) ? Number(status.age_seconds) : null;
      syncCountdown = ageSeconds === null ? 0 : Math.max(0, 600 - (ageSeconds % 600));

      if (syncText) {
        const stateBadge = status.sync_state || 'UNKNOWN';
        const lastSyncLabel = status.last_sync ? formatRelativeTime(status.last_sync) : 'not reported';
        syncText.textContent = `Data status: ${stateBadge} | Last sync: ${lastSyncLabel}`;
      }
    } catch {
      if (syncText) {
        syncText.textContent = 'Data status: unavailable';
      }
    }
  }

  // Initial fetch and 10s polling interval
  updateSyncStatus();
  setInterval(updateSyncStatus, 10000);

  // Countdown timer ticker every second
  setInterval(() => {
    if (syncCountdown > 0) syncCountdown--;
  }, 1000);

  if (syncBtn) {
    syncBtn.addEventListener('click', async () => {
      syncBtn.disabled = true;
      syncBtn.innerHTML = `<span>⏳</span> Refreshing...`;
      try {
        await updateSyncStatus();
        if (typeof onSyncTriggered === 'function') onSyncTriggered();
      } finally {
        syncBtn.disabled = false;
        syncBtn.innerHTML = `<span>↻</span> Refresh data`;
      }
    });
  }
}
