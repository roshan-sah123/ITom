/** Shared, accessible inspection panel for persisted configuration items. */
import { itomApi } from '../api.js';
import { escapeHtml } from '../utils.js';

let requestVersion = 0;
let returnFocus = null;
let background = [];
let previousOverflow = '';

function closeDrawer() {
  requestVersion++;
  document.getElementById('slideDrawer').hidden = true;
  document.getElementById('drawerBackdrop').hidden = true;
  background.forEach(([element, inert]) => { element.inert = inert; });
  background = [];
  document.body.style.overflow = previousOverflow;
  if (returnFocus?.isConnected) returnFocus.focus();
  returnFocus = null;
}

export function initDrawer() {
  const drawer = document.getElementById('slideDrawer');
  if (!drawer || drawer.dataset.initialized) return;
  drawer.dataset.initialized = 'true';
  document.getElementById('drawerCloseBtn').addEventListener('click', closeDrawer);
  document.getElementById('drawerBackdrop').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', event => {
    if (drawer.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeDrawer();
    } else if (event.key === 'Tab') {
      const controls = [...drawer.querySelectorAll('button, a[href], input, select, textarea, [tabindex="0"]')]
        .filter(element => !element.disabled && element.getClientRects().length);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && (document.activeElement === first || !drawer.contains(document.activeElement))) {
        event.preventDefault(); last?.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !drawer.contains(document.activeElement))) {
        event.preventDefault(); first?.focus();
      }
    }
  });
}

function timestamp(value) {
  if (!value) return 'Not supplied';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not supplied' : date.toLocaleString();
}

const field = (label, value) => `<dt>${label}</dt><dd>${escapeHtml(String(value ?? 'Not supplied'))}</dd>`;

function renderDetails(ci) {
  document.getElementById('drawerCiTitle').textContent = ci.name || 'Device details';
  document.getElementById('drawerCiSource').textContent = ci.source_system || 'Source not supplied';
  const attributes = ci.attributes || {};
  document.getElementById('drawerContent').innerHTML = `
    <p class="drawer-note">Stored source snapshot. Missing fields do not indicate a healthy device.</p>
    <section><h4>Status and evidence</h4><dl class="drawer-fields">
      ${field('Status', ci.status)}${field('Health tier', ci.health_tier)}
      ${field('Last synchronized', timestamp(ci.last_sync_time))}
      ${field('Source ID', ci.source_id)}${field('Configuration item ID', ci.id)}
    </dl></section>
    <section><h4>Device information</h4><dl class="drawer-fields">
      ${field('Device type', ci.ci_type)}${field('Vendor', ci.vendor)}${field('Model', ci.model)}
      ${field('Operating system', ci.operating_system)}${field('Serial number', ci.serial_number)}
      ${field('IP address', ci.ip_address)}${field('MAC address', ci.mac_address)}
      ${field('Owner', attributes.contact || attributes.user_principal_name || attributes.primary_user)}
      ${field('Location', ci.canonical_location || ci.location)}
      ${field('Raw source location', ci.location)}${field('First recorded', timestamp(ci.created_at))}
    </dl></section>
    <section><h4>Status history</h4><div id="drawerHistoryList" role="status">Loading recorded changes…</div></section>`;
}

export async function openCiDrawer(item) {
  initDrawer();
  const drawer = document.getElementById('slideDrawer');
  const backdrop = document.getElementById('drawerBackdrop');
  if (!drawer || !backdrop) return;
  const version = ++requestVersion;
  if (drawer.hidden) {
    returnFocus = document.activeElement;
    previousOverflow = document.body.style.overflow;
    background = [...document.body.children].filter(element => element !== drawer && element !== backdrop)
      .map(element => [element, element.inert]);
    background.forEach(([element]) => { element.inert = true; });
    document.body.style.overflow = 'hidden';
  }
  drawer.hidden = false;
  backdrop.hidden = false;
  document.getElementById('drawerCiTitle').textContent = typeof item === 'object' ? item.name || 'Device details' : 'Device details';
  document.getElementById('drawerCiSource').textContent = 'Loading source…';
  document.getElementById('drawerContent').innerHTML = '<p role="status">Loading device evidence…</p>';
  document.getElementById('drawerCloseBtn').focus();
  const id = typeof item === 'string' ? item : item?.id;
  if (!id) {
    document.getElementById('drawerContent').innerHTML = '<p role="status">Device details unavailable: no configuration item ID was supplied.</p>';
    return;
  }
  try {
    const ci = await itomApi.getCiById(id);
    if (version !== requestVersion) return;
    renderDetails(ci);
  } catch {
    if (version !== requestVersion) return;
    document.getElementById('drawerContent').innerHTML = '<p role="status">Device details unavailable. Close this panel and try again.</p>';
    return;
  }
  try {
    const history = await itomApi.getCiHistory(id, 10);
    if (version !== requestVersion) return;
    if (!Array.isArray(history)) throw new Error('Invalid history response');
    document.getElementById('drawerHistoryList').innerHTML = history.length ? history.map(change => `
      <div class="drawer-history-entry"><strong>${escapeHtml(change.status || 'Unknown')} · ${escapeHtml(change.health_tier || 'Unknown')}</strong>
      <span>${escapeHtml(timestamp(change.recorded_at))}</span></div>`).join('') : 'No status changes recorded. This does not establish historical uptime.';
  } catch {
    if (version !== requestVersion) return;
    document.getElementById('drawerHistoryList').textContent = 'History unavailable. Current device details remain visible; close and reopen to try again.';
  }
}
