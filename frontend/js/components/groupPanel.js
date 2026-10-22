import { itomApi } from '../api.js?v=11';
import { escapeHtml as e, formatNumber as n } from '../utils.js';
import { openCiDrawer } from './drawer.js?v=4';
import { siteScoreLabel } from '../labels.js';

export const nativeHealth = group => `<span class="status-pill status-${group.status_code === 1 ? 'healthy' : [2,14].includes(group.status_code) ? 'critical' : group.status_code === 3 ? 'warning' : 'unknown'}">${e(group.status || 'Unknown')}</span>`;
export const scorePill = score => `<span class="status-pill status-${e(score.status === 'unavailable' ? 'unknown' : score.status)}">${score.value == null ? 'Unavailable' : `${Number(score.value).toFixed(1)}% · ${{healthy:'Green',warning:'Yellow',critical:'Red'}[score.status] || 'Unknown'}`}</span>`;
export const snapshotNote = data => `SolarWinds · ${data.freshness?.status || 'UNKNOWN'} · As of ${data.as_of ? new Date(data.as_of).toLocaleString() : 'No successful refresh'}${['FAILED','PARTIAL'].includes(data.last_attempt_status) ? ' · Latest refresh failed; showing last successful snapshot' : ''}`;
const states = new Map();

export async function renderGroupPanel(panel, {id, mode = 'infrastructure', prefix = 'swGroup', onClose, focus = true}) {
  const key = `${prefix}:${id}`;
  if (!states.has(key)) states.set(key, {search:'', status:'', category:undefined, type:'', page:1, pageSize:25});
  const state = states.get(key), version = Symbol();
  panel.renderVersion = version; panel.hidden = false;
  const current = () => panel.isConnected && panel.renderVersion === version;
  const get = suffix => panel.querySelector(`#${prefix}${suffix}`);
  let summary, timer, request = 0;
  panel.innerHTML = `<div class="location-health-heading"><h3 id="${prefix}Title" class="sw-group-name" tabindex="-1">Loading location…</h3><button id="${prefix}Back" class="btn-filter-reset" type="button">← Back to locations</button></div>
    <div id="${prefix}Summary" role="status">Loading location evidence…</div>
    <div class="grid-toolbar">
      <label>Search <input id="${prefix}DeviceSearch" class="filter-select" type="search" placeholder="Device name or IP address"></label>
      <label>Status <select id="${prefix}DeviceStatus" class="filter-select"><option value="">All statuses</option>${['Up','Warning','Down','Critical','Unmanaged','Unknown','Shutdown','Unreachable','External','Unplugged'].map(v=>`<option>${v}</option>`).join('')}</select></label>
      <label>Source type <input id="${prefix}SourceType" class="filter-select" placeholder="Exact SolarWinds NodeType"></label>
      <label>Rows <select id="${prefix}PageSize" class="filter-select">${[10,25,50,100].map(v=>`<option>${v}</option>`).join('')}</select></label>
      <button id="${prefix}ResetDevices" class="btn-filter-reset" type="button">Reset filters</button></div>
    <p id="${prefix}Selection" role="status"></p><div class="grid-scroll" role="region" aria-label="Group devices" tabindex="0"><table class="itom-table"><caption class="sr-only">Selected location devices</caption><thead><tr>${['Device','IP address','Status','Source category','Source type','Hardware'].map(v=>`<th scope="col">${v}</th>`).join('')}</tr></thead><tbody id="${prefix}Devices"></tbody></table></div>
    <div class="grid-footer"><button id="${prefix}Prev" class="btn-filter-reset" type="button">Previous</button><span id="${prefix}Page"></span><button id="${prefix}Next" class="btn-filter-reset" type="button">Next</button></div>`;
  panel.onclick = event => event.stopPropagation();
  get('DeviceSearch').value = state.search; get('DeviceStatus').value = state.status;
  get('SourceType').value = state.type; get('PageSize').value = String(state.pageSize);
  get('Back').onclick = () => { clearTimeout(timer); panel.renderVersion = null; panel.hidden = true; onClose?.(); };
  function debounceLoad() { request++; clearTimeout(timer); state.page = 1; timer = setTimeout(loadDevices,250); }
  get('DeviceSearch').oninput = event => {state.search = event.target.value; debounceLoad();};
  get('SourceType').oninput = event => {state.type = event.target.value; debounceLoad();};
  get('DeviceStatus').onchange = event => {state.status = event.target.value; state.page=1; loadDevices();};
  get('PageSize').onchange = event => {state.pageSize=Number(event.target.value); state.page=1; loadDevices();};
  get('ResetDevices').onclick = () => {
    clearTimeout(timer); Object.assign(state,{search:'',status:'',category:undefined,type:'',page:1});
    get('DeviceSearch').value=''; get('DeviceStatus').value=''; get('SourceType').value=''; renderSummary(); loadDevices();
  };
  get('Prev').onclick = () => {state.page--; loadDevices();};
  get('Next').onclick = () => {state.page++; loadDevices();};
  get('Devices').onclick = event => {const button=event.target.closest('[data-ci]'); if(button) openCiDrawer(button.dataset.ci,button);};

  function renderSummary() {
    if (!summary || !current()) return;
    const score = summary.site_score;
    const categories = [...summary.categories];
    // Keep required zero-count summaries visible without creating source members.
    if (!summary.server_count) categories.push({value:'Server',name:'Server',count:0});
    if (!summary.network_count) categories.push({value:'Network',name:'Network',count:0});
    get('Summary').innerHTML = `<p class="location-health-note">${e(snapshotNote(summary))}</p>
      <p class="location-health-note">Inventory and category counts: SolarWinds group members.</p>
      <div class="group-category-tiles"><button type="button" class="group-category-tile" data-category-index="all" aria-pressed="${state.category === undefined}"><b>${n(summary.total_devices)}</b><span>Total devices</span></button>${categories.map((c,index)=>`<button type="button" class="group-category-tile" data-category-index="${index}" aria-pressed="${state.category === c.value}"><b>${n(c.count)}</b><span class="source-name">${e(c.name)}</span></button>`).join('')}</div>
      <div class="group-score-summary"><div><b>SolarWinds health</b>${nativeHealth(summary.group)}<small>Native group rollup</small></div><div><b>${siteScoreLabel} · ${mode === 'combined' ? 'Combined' : 'SolarWinds'}</b>${scorePill(score)}<small>${e(score.reason || 'Calculated from the complete selected location')}</small></div></div>
      <p class="location-health-note">Site Score covers the complete selected location, including all subgroups. Inventory filters do not change the score.${mode === 'combined' ? ` Intune endpoints: ${n(summary.intune_endpoints)} · Link: ${e(summary.mapping.status)}${summary.mapping.location_name ? ` · ${e(summary.mapping.location_name)}` : ''}.` : ''}</p>
      <details class="location-policy"><summary>Score components and evidence</summary><p>${mode === 'combined' ? '40% Intune compliance + 35% SolarWinds nodes Up + 25% Intune check-ins within seven days.' : 'Up / monitored nodes across all device classes. Unmanaged nodes are excluded.'} Green ≥90; Yellow 75–&lt;90; Red &lt;75. Required component below 75% forces Red; Down/Critical or failed refresh prevents Green. Stale or missing evidence, or coverage below 95%, gives Unavailable.</p>${Object.entries(summary.components).filter(([key])=>mode === 'combined' || key === 'node_status').map(([key,c])=>`<p><b>${{compliance:'Intune compliance',node_status:'SolarWinds nodes Up',recent_checkins:'Intune check-ins within seven days'}[key]}</b>: ${n(c.numerator)} / ${n(c.denominator)} · Field coverage ${c.coverage_pct == null ? 'Unavailable' : `${c.coverage_pct}%`}${c.reason ? ` · ${e(c.reason)}` : ''}</p>`).join('')}${Object.entries(summary.source_freshness).filter(([source])=>mode === 'combined' || source === 'SOLARWINDS').map(([source,f])=>`<p>${e(source)} · ${e(f.status)} · Last successful refresh: ${f.last_synchronized_at ? e(new Date(f.last_synchronized_at).toLocaleString()) : 'Unavailable'}${['FAILED','PARTIAL'].includes(f.last_attempt_status) ? ' · Latest refresh failed or incomplete' : ''}</p>`).join('')}</details>`;
    get('Summary').querySelectorAll('[data-category-index]').forEach(button => button.onclick = () => {
      state.category = button.dataset.categoryIndex === 'all' ? undefined : categories[Number(button.dataset.categoryIndex)].value;
      state.page=1; renderSummary(); loadDevices();
    });
  }

  async function loadDevices() {
    const call = ++request;
    if (!current()) return;
    get('Prev').disabled=true; get('Next').disabled=true;
    get('Devices').innerHTML='<tr><td colspan="6">Loading inventory…</td></tr>';
    try {
      const params={page:state.page,page_size:state.pageSize,search:state.search};
      if(state.status) params.status=state.status;
      if(state.type) params.source_type=state.type;
      if(state.category === null) params.category_missing=true;
      else if(state.category !== undefined) params.category=state.category;
      const {data}=await itomApi.getSolarWindsGroupDevices(id,params);
      if(!current() || call!==request) return;
      if(summary && data.snapshot_id !== summary.snapshot_id) throw new Error('Snapshot changed; reload');
      if(state.page>data.total_pages) {state.page=data.total_pages; return loadDevices();}
      get('Selection').textContent=`${n(data.total)} matching devices · All subgroups included${state.category !== undefined ? ` · Category: ${state.category ?? 'Unclassified'}` : ''}`;
      get('Devices').innerHTML=data.items.length ? data.items.map(ci=>`<tr><td><button type="button" class="table-location-link" data-ci="${e(ci.id)}">${e(ci.name)}</button></td><td>${e(ci.ip_address || 'Unavailable')}</td><td>${e(ci.status)}</td><td class="source-name">${e(ci.source_category ?? 'Unclassified')}</td><td class="source-name">${e(ci.source_type ?? 'Unavailable')}</td><td>${e(ci.ci_type || 'Unavailable')}</td></tr>`).join('') : '<tr><td colspan="6">No devices found.</td></tr>';
      get('Page').textContent=`Page ${state.page} of ${data.total_pages}`;
      get('Prev').disabled=state.page<=1; get('Next').disabled=state.page>=data.total_pages;
    } catch {
      if(!current() || call!==request) return;
      get('Selection').textContent=''; get('Page').textContent='';
      get('Devices').innerHTML=`<tr><td colspan="6">Group inventory unavailable or changed. <button id="${prefix}RetryDevices" type="button" class="btn-filter-reset">Retry</button></td></tr>`;
      get('RetryDevices').onclick=reload;
    }
  }
  async function reload() {
    try {
      const {data}=await itomApi.getGroupSummary(id,mode);
      if(!current()) return;
      summary=data; get('Title').textContent=data.group.name;
      panel.querySelector('caption').textContent=`${data.group.name} devices`;
      renderSummary(); if(focus) get('Title').focus({preventScroll:true}); await loadDevices();
    } catch {
      if(!current()) return;
      get('Title').textContent='Location unavailable';
      get('Summary').textContent='Location summary unavailable. Reload snapshot to retry.';
      get('Devices').innerHTML='<tr><td colspan="6">Inventory unavailable.</td></tr>';
    }
  }
  await reload();
}
