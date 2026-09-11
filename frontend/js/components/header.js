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
      const lastSync = status.last_sync ? new Date(status.last_sync) : new Date();
      const ageSeconds = status.age_seconds !== null ? status.age_seconds : Math.floor((Date.now() - lastSync) / 1000);
      syncCountdown = Math.max(0, 600 - (ageSeconds % 600));

      if (syncText) {
        const stateBadge = status.sync_state === 'HEALTHY' ? 'FRESH' : 'STALE';
        syncText.textContent = `Sync: ${formatRelativeTime(status.last_sync)} (${stateBadge}) | Next in: ${syncCountdown}s`;
      }
    } catch {
      if (syncText) {
        syncText.textContent = `Sync: Live Mirror (Connecting...)`;
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
      syncBtn.innerHTML = `<span>⏳</span> Syncing...`;
      try {
        await itomApi.triggerManualSync('ALL');
        setTimeout(async () => {
          await updateSyncStatus();
          syncBtn.disabled = false;
          syncBtn.innerHTML = `<span>⚡</span> Sync Now`;
          if (typeof onSyncTriggered === 'function') onSyncTriggered();
        }, 1500);
      } catch {
        syncBtn.disabled = false;
        syncBtn.innerHTML = `<span>⚡</span> Sync Now`;
      }
    });
  }
}
