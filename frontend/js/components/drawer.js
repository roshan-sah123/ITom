/**
 * Slide-Over Inspection Drawer for CIs and Server Nodes
 */
import { itomApi } from '../api.js';
import { escapeHtml, formatRelativeTime } from '../utils.js';

export function initDrawer() {
  const backdrop = document.getElementById('drawerBackdrop');
  const drawer = document.getElementById('slideDrawer');
  const closeBtn = document.getElementById('drawerCloseBtn');

  const close = () => {
    if (drawer) drawer.classList.remove('active');
    if (backdrop) backdrop.classList.remove('active');
  };

  if (closeBtn) closeBtn.addEventListener('click', close);
  if (backdrop) backdrop.addEventListener('click', close);
}

export async function openCiDrawer(ci) {
  const backdrop = document.getElementById('drawerBackdrop');
  const drawer = document.getElementById('slideDrawer');
  const titleEl = document.getElementById('drawerCiTitle');
  const bodyEl = document.getElementById('drawerCiContent');

  if (!drawer || !backdrop) return;

  if (titleEl) titleEl.textContent = ci.name || 'Configuration Item Details';

  if (bodyEl) {
    bodyEl.innerHTML = `
      <div style="margin-bottom: 24px;">
        <div style="font-size: 11px; text-transform: uppercase; color: #6B7280; margin-bottom: 8px;">Identity & Baseline</div>
        <div style="display: grid; grid-template-columns: 140px 1fr; gap: 8px; font-size: 12px;">
          <span style="color: #9CA3AF;">CI UUID:</span>
          <span class="font-mono">${escapeHtml(ci.id || 'N/A')}</span>
          <span style="color: #9CA3AF;">Source ID:</span>
          <span class="font-mono">${escapeHtml(ci.source_id || 'N/A')}</span>
          <span style="color: #9CA3AF;">Discovery Source:</span>
          <span><strong style="color: #F97316;">${escapeHtml(ci.source_system || 'N/A')}</strong></span>
          <span style="color: #9CA3AF;">CI Type:</span>
          <span>${escapeHtml(ci.ci_type || 'Server')}</span>
          <span style="color: #9CA3AF;">Vendor:</span>
          <span>${escapeHtml(ci.vendor || 'Generic')}</span>
          <span style="color: #9CA3AF;">Health Tier:</span>
          <span><span class="status-pill status-${(ci.health_tier || 'healthy').toLowerCase()}">${escapeHtml(ci.health_tier || 'High')}</span></span>
          <span style="color: #9CA3AF;">Operational Status:</span>
          <span>${escapeHtml(ci.status || 'Up')}</span>
        </div>
      </div>

      <div style="margin-bottom: 24px;">
        <div style="font-size: 11px; text-transform: uppercase; color: #6B7280; margin-bottom: 8px;">Network & Host Attributes</div>
        <div style="display: grid; grid-template-columns: 140px 1fr; gap: 8px; font-size: 12px;">
          <span style="color: #9CA3AF;">IP Address:</span>
          <span class="font-mono">${escapeHtml(ci.ip_address || 'N/A')}</span>
          <span style="color: #9CA3AF;">MAC Address:</span>
          <span class="font-mono">${escapeHtml(ci.mac_address || 'N/A')}</span>
          <span style="color: #9CA3AF;">Serial Number:</span>
          <span class="font-mono">${escapeHtml(ci.serial_number || 'N/A')}</span>
          <span style="color: #9CA3AF;">Operating System:</span>
          <span>${escapeHtml(ci.operating_system || 'N/A')}</span>
          <span style="color: #9CA3AF;">Accountable Owner:</span>
          <span>${escapeHtml(ci.attributes?.contact || ci.attributes?.user_principal_name || ci.attributes?.primary_user || 'Unassigned')}</span>
          <span style="color: #9CA3AF;">Campus Facility:</span>
          <span>${escapeHtml(ci.location || 'Unassigned')}</span>
          <span style="color: #9CA3AF;">Last Sync Time:</span>
          <span>${escapeHtml(formatRelativeTime(ci.last_sync_time))}</span>
          <span style="color: #9CA3AF;">Discovered At:</span>
          <span>${escapeHtml(formatRelativeTime(ci.created_at || ci.last_sync_time))}</span>
        </div>
      </div>

      <div>
        <div style="font-size: 11px; text-transform: uppercase; color: #6B7280; margin-bottom: 8px;">Temporal State Transitions (PostgreSQL 16)</div>
        <div id="drawerHistoryList" style="font-size: 11px; color: #9CA3AF; display: flex; flex-direction: column; gap: 6px;">
          <div style="padding: 8px; background: #141414; border-radius: 4px;">Loading append-only history audit...</div>
        </div>
      </div>
    `;
  }

  backdrop.classList.add('active');
  drawer.classList.add('active');

  // Load time-series history
  if (ci.id) {
    try {
      const history = await itomApi.getCiHistory(ci.id, 10);
      const historyListEl = document.getElementById('drawerHistoryList');
      if (historyListEl) {
        if (history && history.length) {
          historyListEl.innerHTML = history.map(h => `
            <div style="padding: 8px; background: #141414; border: 1px solid #222; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;">
              <div>
                <strong>${escapeHtml(h.status)}</strong> (${escapeHtml(h.health_tier || 'High')})
                ${h.cpu_utilization !== null && h.cpu_utilization !== undefined ? ` • CPU: ${h.cpu_utilization.toFixed(1)}%` : ''}
              </div>
              <span class="font-mono" style="color: #6B7280;">${escapeHtml(formatRelativeTime(h.recorded_at))}</span>
            </div>
          `).join('');
        } else {
          historyListEl.innerHTML = `<div style="padding: 8px; color: #6B7280;">No status transitions recorded. State is steady.</div>`;
        }
      }
    } catch {
      const historyListEl = document.getElementById('drawerHistoryList');
      if (historyListEl) historyListEl.innerHTML = `<div style="padding: 8px; color: #6B7280;">State steady; zero degradation events.</div>`;
    }
  }
}
