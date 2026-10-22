import { itomApi } from '../api.js?v=11';
import { escapeHtml, formatNumber } from '../utils.js';
import { renderGroupPanel } from './groupPanel.js?v=1';
import { openCiDrawer } from './drawer.js?v=4';

let generation = 0;
let search = '', status = '', selectedId = null, selectedPath = null;

const expanded = new Set();
const tone = value => value === 1 ? 'healthy' : [2, 14].includes(value) ? 'critical' : value === 3 ? 'warning' : 'unknown';
const pill = (label, code) => `<span class="status-pill status-${tone(code)}">${escapeHtml(label || 'Unknown')}</span>`;
const date = value => value ? new Date(value).toLocaleString() : 'No successful refresh';

export async function renderSolarWindsGroups(host, onModeChange, mode = 'infrastructure') {
  const focusedId = host.contains(document.activeElement) ? document.activeElement.id : null;
  const version = ++generation;
  let roots = [], evidence = {}, groups = new Map(), cache = new Map(), pending = new Set();
  let searchTimer;
  const active = () => version === generation && host.isConnected && host.querySelector('#swGroupTree');
  host.innerHTML = `<div class="location-health-heading"><h2>Groups Summary</h2><div class="location-header-actions">
    <label>View <select id="locMode" class="filter-select"><option value="infrastructure">SolarWinds</option><option value="auto">By available sources</option><option value="combined">Combined · both sources</option><option value="endpoints">Digital Workspace · Intune</option></select></label>
    <button id="swGroupRefresh" type="button" class="btn-filter-reset">Reload snapshot</button></div></div>
    <p id="swGroupEvidence" class="location-health-note" role="status"></p>
    <p id="swGroupCoverage" class="location-health-note"></p>
    <section id="swGroupBrowse" aria-label="SolarWinds locations"><div class="grid-toolbar">
      <label>Search <input id="swGroupSearch" class="filter-select" type="search" placeholder="Location name"></label>
      <label>Status <select id="swGroupStatus" class="filter-select"><option value="">All statuses</option></select></label>
      <button id="swGroupReset" type="button" class="btn-filter-reset">Reset filters</button></div>
      <div id="swGroupMessage" role="status">Loading SolarWinds groups…</div>
      <ul id="swGroupTree" class="sw-group-tree" aria-label="SolarWinds groups"></ul></section>
    <section id="swGroupDetail" class="location-detail" aria-label="Group device inventory" hidden></section>`;
  host.querySelector('#locMode').value = mode;
  host.querySelector('#locMode').onchange = event => {
    generation++; clearTimeout(searchTimer); onModeChange(event.target.value);
  };
  host.querySelector('#swGroupRefresh').onclick = () => renderSolarWindsGroups(host, onModeChange, mode);
  host.querySelector('#swGroupSearch').value = search;
  host.querySelector('#swGroupSearch').oninput = event => { search = event.target.value; renderTree(); };
  host.querySelector('#swGroupStatus').onchange = event => { status = event.target.value; renderTree(); };
  host.querySelector('#swGroupReset').onclick = () => {
    search = ''; status = '';
    host.querySelector('#swGroupSearch').value = '';
    host.querySelector('#swGroupStatus').value = ''; renderTree();
  };

  function showMessage(text, retry) {
    const message = host.querySelector('#swGroupMessage');
    message.textContent = text;
    if (retry) {
      const button = document.createElement('button');
      button.id = 'swGroupRetry'; button.type = 'button'; button.className = 'btn-filter-reset';
      button.textContent = 'Retry'; button.onclick = () => renderSolarWindsGroups(host, onModeChange, mode);
      message.append(' ', button);
    }
  }

  function showEvidence(data) {
    host.querySelector('#swGroupEvidence').textContent = `SolarWinds · ${data.freshness?.status || 'UNKNOWN'} · As of ${date(data.as_of)}${['FAILED', 'PARTIAL'].includes(data.last_attempt_status) ? ' · Latest refresh failed; showing the last successful snapshot' : ''}`;
  }

  function renderTree() {
    if (!active()) return;
    const focus = document.activeElement?.dataset;
    const focusKey = focus?.toggleKey || focus?.openKey;
    const focusType = focus?.toggleKey ? 'toggleKey' : 'openKey';
    const needed = new Set();
    function itemsMarkup(items, path = '') {
      return items.map(item => {
        if (item.kind === 'device') return `<li><div class="sw-group-row sw-group-device"><span class="sw-group-spacer"></span><button type="button" class="table-location-link" data-ci="${escapeHtml(item.id)}">${escapeHtml(item.name)}</button>${pill(item.status, item.attributes?.orion_status_code)}</div></li>`;
        groups.set(item.group_id, item);
        const key = path ? `${path}/${item.group_id}` : String(item.group_id);
        const isOpen = expanded.has(key) && item.has_members;
        let children = '';
        if (isOpen) {
          if (cache.has(item.group_id)) children = itemsMarkup(cache.get(item.group_id), key);
          else { needed.add(item.group_id); children = '<li role="status">Loading members…</li>'; }
        }
        return `<li><div class="sw-group-row" data-group-path="${key}">
          ${item.has_members ? `<button type="button" class="sw-group-toggle" data-toggle-key="${key}" aria-expanded="${isOpen}" aria-label="${isOpen ? 'Collapse' : 'Expand'} ${escapeHtml(item.name)}">${isOpen ? '▾' : '▸'}</button>` : '<span class="sw-group-spacer"></span>'}
          <span class="sw-group-folder" aria-hidden="true"></span><button type="button" class="table-location-link sw-group-name" data-open-key="${key}">${escapeHtml(item.name)}</button>${pill(item.status, item.status_code)}</div>
          ${isOpen ? `<ul>${children}</ul>` : ''}</li>`;
      }).join('');
    }
    const visible = roots.filter(item => item.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()) && (!status || item.status === status));
    const panel = host.querySelector('#swGroupDetail');
    panel.remove();
    host.querySelector('#swGroupTree').innerHTML = itemsMarkup(visible);
    const anchor = [...host.querySelectorAll('[data-group-path]')].find(row => row.dataset.groupPath === selectedPath);
    if (anchor) anchor.after(panel); else host.append(panel);
    showMessage(!evidence.data_available ? 'No successful SolarWinds group snapshot yet.' : !roots.length ? 'No SolarWinds groups.' : !visible.length ? 'No groups match the filters.' : '');
    if (focusKey) [...host.querySelectorAll('button')].find(button => button.dataset[focusType] === focusKey)?.focus({ preventScroll: true });
    for (const id of needed) {
      if (pending.has(id)) continue;
      pending.add(id);
      itomApi.getSolarWindsGroupMembers(id).then(response => {
        if (!active()) return;
        if (response.data.snapshot_id !== evidence.snapshot_id) throw new Error('Snapshot changed');
        cache.set(id, response.data.items); renderTree();
      }).catch(() => {
        if (!active()) return;
        // Stop displaying a loading row after a failed expansion; keep Retry reachable.
        for (const key of expanded) if (Number(key.split('/').at(-1)) === id) expanded.delete(key);
        renderTree(); showMessage('Group members unavailable or changed. Refresh to retry.', true);
      }).finally(() => pending.delete(id));
    }
  }

  host.querySelector('#swGroupTree').onclick = event => {
    const toggle = event.target.closest('[data-toggle-key]');
    if (toggle) {
      const key = toggle.dataset.toggleKey;
      if (expanded.has(key)) expanded.delete(key); else expanded.add(key);
      renderTree(); return;
    }
    const group = event.target.closest('[data-open-key]');
    if (group) {
      selectedPath = group.dataset.openKey;
      openGroup(Number(selectedPath.split('/').at(-1))); return;
    }
    const device = event.target.closest('[data-ci]');
    if (device) openCiDrawer(device.dataset.ci, device);
  };

  async function openGroup(id, focus = true) {
    selectedId = id;
    const panel = host.querySelector('#swGroupDetail');
    const anchor = [...host.querySelectorAll('[data-group-path]')].find(row => row.dataset.groupPath === selectedPath);
    if (anchor) anchor.after(panel); else host.append(panel);
    await renderGroupPanel(panel, {id, mode, focus, onClose: () => {
      selectedId = null;
      [...host.querySelectorAll('[data-open-key]')].find(button => button.dataset.openKey === selectedPath)?.focus({preventScroll:true});
    }});
  }

  try {
    const [response, overview] = await Promise.all([itomApi.getSolarWindsGroups(), itomApi.getGroupOverview(mode)]);
    const {data} = response;
    if (!active()) return;
    if (data.snapshot_id !== overview.data.snapshot_id) throw new Error('Snapshot changed');
    roots = data.items; evidence = data;
    const fleet = overview.data.fleet;
    host.querySelector('#swGroupCoverage').innerHTML = `${formatNumber(fleet.grouped_devices)} / ${formatNumber(fleet.total_devices)} devices in regular groups · ${formatNumber(fleet.ungrouped_devices)} outside groups. <button id="swGroupFullInventory" type="button" class="table-location-link">Open full inventory</button>. Fleet totals count shared devices once.`;
    host.querySelector('#swGroupFullInventory').onclick = () => window.navigateToView?.('infrastructure','servers');
    for (const group of roots) groups.set(group.group_id, group);
    showEvidence(data);
    const control = host.querySelector('#swGroupStatus');
    control.innerHTML += [...new Set(roots.map(group => group.status))].sort().map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('');
    if (![...control.options].some(option => option.value === status)) status = '';
    control.value = status;
    const count = document.getElementById('catSitesVal'), label = document.getElementById('catSitesSub');
    if (count) count.textContent = data.data_available ? formatNumber(roots.length) : 'Unavailable';
    if (label) label.textContent = 'SolarWinds top-level groups';
    renderTree();
    if (selectedId !== null) await openGroup(selectedId, false);
    if (focusedId) host.querySelector(`#${CSS.escape(focusedId)}`)?.focus({preventScroll:true});
  } catch (error) {
    if (active()) showMessage('Group data unavailable.', true);
  }
}
