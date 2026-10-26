import { itomApi } from '../api.js?v=13';
import { escapeHtml, formatNumber } from '../utils.js';
import { renderGroupPanel, scorePill } from './groupPanel.js?v=2';
import { openCiDrawer } from './drawer.js?v=4';

let generation = 0;
let search = '', status = '', selectedId = null, selectedPath = null;
let mappingOpen = false, mappingFilter = '';

const expanded = new Set();
const tone = value => value === 1 ? 'healthy' : [2, 14].includes(value) ? 'critical' : value === 3 ? 'warning' : 'unknown';
const pill = (label, code) => `<span class="status-pill status-${tone(code)}">${escapeHtml(label || 'Unknown')}</span>`;
const date = value => value ? new Date(value).toLocaleString() : 'No successful refresh';
const mappingLabels = {approved:'Approved', unmapped:'Unmapped', review:'Needs review', rejected:'Rejected'};
const mappingState = row => row.mapping?.status === 'APPROVED' ? row.mapping.location_name ? 'approved' : 'review' : row.mapping?.status === 'REJECTED' ? 'rejected' : !row.mapping?.status || row.mapping.status === 'UNMAPPED' ? 'unmapped' : 'review';
const scoreable = row => row.site_score?.value != null && row.site_score.status !== 'unavailable';

export async function renderSolarWindsGroups(host, onModeChange, mode = 'infrastructure') {
  const focusedId = host.contains(document.activeElement) ? document.activeElement.id : null;
  const version = ++generation;
  let roots = [], evidence = {}, groups = new Map(), cache = new Map(), pending = new Set();
  let assessments = [], locationRequest = null, previewRequest = 0;
  let searchTimer;
  const active = () => version === generation && host.isConnected && host.querySelector('#swGroupTree');
  host.innerHTML = `<div class="location-health-heading"><h2>Groups Summary</h2><div class="location-header-actions">
    <label>View <select id="locMode" class="filter-select"><option value="infrastructure">SolarWinds</option><option value="auto">By available sources</option><option value="combined">Combined · both sources</option><option value="endpoints">Digital Workspace · Intune</option></select></label>
    <button id="swGroupRefresh" type="button" class="btn-filter-reset">Reload snapshot</button></div></div>
    <p id="swGroupEvidence" class="location-health-note" role="status"></p>
    <p id="swGroupCoverage" class="location-health-note"></p>
    ${mode === 'combined' ? `<section class="mapping-readiness-region" aria-label="Combined score readiness">
      <div id="swMappingSummary" role="status">Loading mapping readiness…</div>
      <button id="swMappingToggle" class="btn-filter-reset" type="button" aria-expanded="${mappingOpen}" aria-controls="swMappingWorkbench">Site mapping &amp; coverage</button>
      <section id="swMappingWorkbench" class="mapping-workbench" aria-labelledby="swMappingHeading" ${mappingOpen ? '' : 'hidden'}>
        <h3 id="swMappingHeading">Site mapping &amp; coverage</h3>
        <div class="grid-toolbar"><label>Readiness <select id="swMappingFilter" class="filter-select"><option value="">All groups</option><option value="approved">Approved links</option><option value="unmapped">Unmapped</option><option value="review">Needs review</option><option value="rejected">Rejected links</option><option value="scoreable">Scoreable</option><option value="empty">Empty groups</option></select></label></div>
        <p id="swMappingResults" class="location-health-note" role="status"></p>
        <div class="grid-scroll mapping-table-scroll" tabindex="0" role="region" aria-label="Site mapping inventory"><table class="itom-table"><thead><tr><th scope="col">SolarWinds group</th><th scope="col">SolarWinds devices</th><th scope="col">Linked Intune location</th><th scope="col">Intune endpoints</th><th scope="col">Link status</th><th scope="col">Combined score</th></tr></thead><tbody id="swMappingRows"></tbody></table></div>
        <section id="swMappingPreview" class="mapping-preview" aria-label="Site link population preview" hidden></section>
      </section></section>` : ''}
    <section id="swOutsideInventory" class="location-detail" aria-label="Devices outside regular groups" hidden></section>
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

  if (mode === 'combined') {
    host.querySelector('#swMappingToggle').onclick = event => {
      mappingOpen = !mappingOpen;
      event.currentTarget.setAttribute('aria-expanded', String(mappingOpen));
      host.querySelector('#swMappingWorkbench').hidden = !mappingOpen;
      if (!mappingOpen) {
        previewRequest++;
        host.querySelector('#swMappingPreview').hidden = true;
      }
    };
    host.querySelector('#swMappingFilter').value = mappingFilter;
    host.querySelector('#swMappingFilter').onchange = event => {
      mappingFilter = event.target.value;
      previewRequest++;
      host.querySelector('#swMappingPreview').hidden = true;
      renderMappingRows();
    };
    host.querySelector('#swMappingRows').onclick = event => {
      const button = event.target.closest('[data-preview-group]');
      if (button) previewMapping(Number(button.dataset.previewGroup));
    };
  }

  function renderMappingRows() {
    const visible = assessments.filter(row => !mappingFilter || (mappingFilter === 'empty' ? row.total_devices === 0 : mappingFilter === 'scoreable' ? scoreable(row) : mappingState(row) === mappingFilter));
    host.querySelector('#swMappingResults').textContent = evidence.data_available ? `${formatNumber(visible.length)} / ${formatNumber(assessments.length)} top-level groups · Group populations may overlap` : 'No successful SolarWinds group snapshot yet.';
    host.querySelector('#swMappingRows').innerHTML = visible.map(row => `<tr><td><button type="button" class="table-location-link sw-group-name" data-preview-group="${row.group.group_id}">${escapeHtml(row.group.name)}</button></td><td>${formatNumber(row.total_devices)}</td><td>${escapeHtml(row.mapping.location_name || 'Not linked')}</td><td>${mappingState(row) === 'approved' ? formatNumber(row.intune_endpoints) : 'Not linked'}</td><td>${mappingLabels[mappingState(row)]}</td><td>${scorePill(row.site_score)}<small class="mapping-score-reason">${escapeHtml(row.site_score.reason || '')}</small></td></tr>`).join('') || '<tr><td colspan="6">No groups match this readiness filter.</td></tr>';
  }

  function renderMappingReadiness() {
    const counts = Object.fromEntries(Object.keys(mappingLabels).map(state => [state, assessments.filter(row => mappingState(row) === state).length]));
    const measures = [['Groups', assessments.length], ['Approved links', counts.approved], ['Unmapped', counts.unmapped], ['Needs review', counts.review], ['Rejected', counts.rejected], ['Scoreable', assessments.filter(scoreable).length], ['Empty groups', assessments.filter(row => row.total_devices === 0).length]];
    host.querySelector('#swMappingSummary').innerHTML = `<dl class="mapping-readiness">${measures.map(([label, value]) => `<div><dt>${label}</dt><dd>${evidence.data_available ? formatNumber(value) : 'Unavailable'}</dd></div>`).join('')}</dl>`;
    host.querySelector('#swMappingToggle').disabled = !evidence.data_available;
    renderMappingRows();
  }

  async function previewMapping(id) {
    const row = assessments.find(item => item.group.group_id === id);
    if (!row) return;
    const call = ++previewRequest;
    const preview = host.querySelector('#swMappingPreview');
    preview.hidden = false;
    preview.innerHTML = `<h4 tabindex="-1">${escapeHtml(row.group.name)}</h4><p role="status">Loading Intune location populations…</p>`;
    preview.querySelector('h4').focus({preventScroll:true});
    preview.scrollIntoView({block:'nearest'});
    try {
      if (!locationRequest) locationRequest = itomApi.getLocations().catch(error => {locationRequest = null; throw error;});
      const {data} = await locationRequest;
      if (!active() || call !== previewRequest) return;
      const locations = data.items.filter(location => location.id !== 'unassigned' && location.endpoints > 0).sort((left, right) => left.name.localeCompare(right.name));
      const restoreFocus = preview.contains(document.activeElement);
      preview.innerHTML = `<div class="mapping-preview-heading"><h4 tabindex="-1">${escapeHtml(row.group.name)}</h4><button id="swMappingClosePreview" type="button" class="btn-filter-reset">Close preview</button></div>
        <p class="location-health-note">SolarWinds group ID: ${row.group.group_id} · Current link: ${mappingLabels[mappingState(row)]}${row.mapping.location_name ? ` · ${escapeHtml(row.mapping.location_name)}` : ''}</p>
        <p class="location-health-note">Preview only · No links or device assignments changed. Approval remains with the local operator review.</p>
        <label class="mapping-candidate">Candidate Intune location <select id="swMappingLocation" class="filter-select"><option value="">${locations.length ? 'No candidate selected' : 'No populated Intune locations available'}</option>${locations.map(location => `<option value="${escapeHtml(location.id)}">${escapeHtml(location.name)} · ${escapeHtml(location.level)} · ${formatNumber(location.endpoints)} endpoints</option>`).join('')}</select></label>
        <div id="swMappingPopulation" class="mapping-population" role="status">No candidate selected.</div>`;
      const candidate = preview.querySelector('#swMappingLocation');
      candidate.onchange = () => {
        const location = locations.find(item => item.id === candidate.value);
        const population = preview.querySelector('#swMappingPopulation');
        if (!location) {population.textContent = 'No candidate selected.'; return;}
        const fresh = data.freshness?.sources?.INTUNE;
        population.innerHTML = `<p><b>${formatNumber(row.total_devices)} SolarWinds devices</b> · ${escapeHtml(row.group.name)}</p><p><b>${formatNumber(location.endpoints)} Intune endpoints</b> · ${escapeHtml(location.name)} · ${escapeHtml(location.level)}</p><p class="location-health-note">SolarWinds snapshot: ${escapeHtml(date(evidence.as_of))} · ${escapeHtml(evidence.freshness?.status || 'UNKNOWN')}<br>Intune snapshot: ${escapeHtml(date(fresh?.last_synchronized_at))} · ${escapeHtml(fresh?.status || 'UNKNOWN')}</p>${location.scores?.combined?.reason === 'Location identity needs review' ? '<p class="location-health-note">Candidate location identity needs review.</p>' : ''}`;
      };
      preview.querySelector('#swMappingClosePreview').onclick = () => {
        previewRequest++; preview.hidden = true;
        host.querySelector(`[data-preview-group="${id}"]`)?.focus({preventScroll:true});
      };
      if (restoreFocus) preview.querySelector('h4').focus({preventScroll:true});
    } catch {
      if (!active() || call !== previewRequest) return;
      preview.innerHTML = `<h4>${escapeHtml(row.group.name)}</h4><p role="status">Intune location catalogue unavailable.</p><button id="swMappingRetry" type="button" class="btn-filter-reset">Retry</button>`;
      preview.querySelector('#swMappingRetry').onclick = () => previewMapping(id);
    }
  }

  async function openOutsideInventory() {
    const panel = host.querySelector('#swOutsideInventory');
    const renderToken = Symbol();
    panel.renderToken = renderToken; panel.hidden = false;
    let currentPage = 1, pageSize = 25, query = '', deviceStatus = '', request = 0, timer;
    const current = () => active() && panel.renderToken === renderToken;
    const get = suffix => panel.querySelector(`#swOutside${suffix}`);
    panel.innerHTML = `<div class="location-health-heading"><h3 id="swOutsideTitle" tabindex="-1">Outside regular groups</h3><button id="swOutsideClose" type="button" class="btn-filter-reset">Close inventory</button></div>
      <p class="location-health-note">These devices remain in SolarWinds inventory. No site or group assignment is inferred.</p>
      <p id="swOutsideEvidence" class="location-health-note"></p>
      <div class="grid-toolbar"><label>Search <input id="swOutsideSearch" type="search" class="filter-select" placeholder="Device name or IP address"></label><label>Status <select id="swOutsideStatus" class="filter-select"><option value="">All statuses</option>${['Up','Warning','Down','Critical','Unmanaged','Unknown','Shutdown','Unreachable','External','Unplugged'].map(value => `<option>${value}</option>`).join('')}</select></label><label>Rows <select id="swOutsidePageSize" class="filter-select">${[10,25,50,100].map(value => `<option ${value === pageSize ? 'selected' : ''}>${value}</option>`).join('')}</select></label><button id="swOutsideReset" type="button" class="btn-filter-reset">Reset filters</button></div>
      <p id="swOutsideSelection" role="status"></p><div class="grid-scroll mapping-table-scroll" tabindex="0" role="region" aria-label="Outside-group devices"><table class="itom-table"><thead><tr>${['Device','IP address','Status','Source category','Source type'].map(value => `<th scope="col">${value}</th>`).join('')}</tr></thead><tbody id="swOutsideDevices"></tbody></table></div>
      <div class="grid-footer"><button id="swOutsidePrev" type="button" class="btn-filter-reset">Previous</button><span id="swOutsidePage"></span><button id="swOutsideNext" type="button" class="btn-filter-reset">Next</button></div>`;
    get('Evidence').textContent = host.querySelector('#swGroupEvidence').textContent;
    get('Title').focus({preventScroll:true});
    panel.scrollIntoView({block:'nearest'});
    get('Close').onclick = () => {
      clearTimeout(timer); panel.renderToken = null; panel.hidden = true;
      host.querySelector('#swGroupOutsideInventory')?.focus({preventScroll:true});
    };
    get('Search').oninput = event => {
      query = event.target.value; currentPage = 1; request++; clearTimeout(timer);
      timer = setTimeout(load, 250);
    };
    get('Status').onchange = event => {deviceStatus = event.target.value; currentPage = 1; load();};
    get('PageSize').onchange = event => {pageSize = Number(event.target.value); currentPage = 1; load();};
    get('Reset').onclick = () => {
      clearTimeout(timer); query = ''; deviceStatus = ''; currentPage = 1;
      get('Search').value = ''; get('Status').value = ''; load();
    };
    get('Prev').onclick = () => {currentPage--; load();};
    get('Next').onclick = () => {currentPage++; load();};
    get('Devices').onclick = event => {
      const button = event.target.closest('[data-ci]');
      if (button) openCiDrawer(button.dataset.ci, button);
    };
    async function load() {
      clearTimeout(timer);
      const call = ++request;
      get('Prev').disabled = true; get('Next').disabled = true;
      get('Devices').innerHTML = '<tr><td colspan="5">Loading outside-group inventory…</td></tr>';
      try {
        const {data} = await itomApi.getSolarWindsUngroupedDevices({page:currentPage, page_size:pageSize, search:query, status:deviceStatus});
        if (!current() || call !== request) return;
        if (data.snapshot_id !== evidence.snapshot_id) throw new Error('Snapshot changed');
        if (currentPage > data.total_pages) {currentPage = data.total_pages; return load();}
        get('Selection').textContent = `${formatNumber(data.total)} matching ${data.total === 1 ? 'device' : 'devices'} outside regular groups`;
        get('Devices').innerHTML = data.items.map(device => `<tr><td><button type="button" class="table-location-link sw-group-name" data-ci="${escapeHtml(device.id)}">${escapeHtml(device.name)}</button></td><td>${escapeHtml(device.ip_address || 'Unavailable')}</td><td>${pill(device.status, device.attributes?.orion_status_code)}</td><td class="source-name">${escapeHtml(device.source_category ?? 'Unclassified')}</td><td class="source-name">${escapeHtml(device.source_type ?? 'Unavailable')}</td></tr>`).join('') || '<tr><td colspan="5">No devices match the filters.</td></tr>';
        get('Page').textContent = `Page ${currentPage} of ${data.total_pages}`;
        get('Prev').disabled = currentPage <= 1; get('Next').disabled = currentPage >= data.total_pages;
      } catch {
        if (!current() || call !== request) return;
        get('Selection').textContent = ''; get('Page').textContent = '';
        get('Devices').innerHTML = '<tr><td colspan="5">Outside-group inventory unavailable or snapshot changed. <button id="swOutsideRetry" type="button" class="btn-filter-reset">Retry</button> <button id="swOutsideReload" type="button" class="btn-filter-reset">Reload snapshot</button></td></tr>';
        get('Retry').onclick = load;
        get('Reload').onclick = () => renderSolarWindsGroups(host, onModeChange, mode);
      }
    }
    await load();
  }

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
    assessments = overview.data.items;
    if (mode === 'combined') renderMappingReadiness();
    const fleet = overview.data.fleet;
    host.querySelector('#swGroupCoverage').innerHTML = `${formatNumber(fleet.grouped_devices)} / ${formatNumber(fleet.total_devices)} devices in regular groups · ${formatNumber(fleet.ungrouped_devices)} outside groups. <button id="swGroupOutsideInventory" type="button" class="table-location-link" ${data.data_available ? '' : 'disabled'}>View outside groups</button> · <button id="swGroupFullInventory" type="button" class="table-location-link">Open full inventory</button>. Fleet totals count shared devices once.`;
    host.querySelector('#swGroupOutsideInventory').onclick = openOutsideInventory;
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
    if (active()) {
      showMessage('Group data unavailable.', true);
      if (mode === 'combined') {
        host.querySelector('#swMappingSummary').textContent = 'Mapping readiness unavailable.';
        host.querySelector('#swMappingToggle').disabled = true;
      }
    }
  }
}
