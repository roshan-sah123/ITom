import { itomApi } from '../api.js?v=12';
import { escapeHtml as e, formatNumber } from '../utils.js';
import { scorePill } from './groupPanel.js?v=2';
import { renderIntuneLocationPanel, intuneFreshness } from './intuneLocationPanel.js?v=1';
import { openLocationReviews } from './locationReviews.js?v=2';

const state={search:'',status:'',level:'',selected:null};
const n=value=>Number.isFinite(value) ? formatNumber(value) : 'Unavailable';

export async function renderIntuneLocations(host,onModeChange,filters={}) {
  for(const [id,key] of [['locSearch','search'],['locStatus','status'],['locLevel','level']]) if(filters[id]!==undefined) state[key]=filters[id];
  const focusedId=host.contains(document.activeElement) ? document.activeElement.id : null;
  const version=Symbol();host.intuneVersion=version;
  const active=()=>host.isConnected && host.intuneVersion===version && host.querySelector('#intuneLocationTree');
  let locations=[],coverage={};
  host.innerHTML=`<div class="location-health-heading"><h2>Locations Summary</h2><div class="location-header-actions">
    <label>View <select id="locMode" class="filter-select"><option value="infrastructure">SolarWinds</option><option value="combined">Combined · both sources</option><option value="endpoints" selected>Digital Workspace · Intune</option><option value="auto">By available sources</option></select></label>
    <button id="locReview" type="button" class="btn-filter-reset" aria-label="Review location mappings">Review mappings</button><button id="intuneRefresh" type="button" class="btn-filter-reset">Reload snapshot</button></div></div>
    <section id="locBrowse" aria-label="Intune locations"><p id="intuneEvidence" class="location-health-note" role="status">Loading Intune evidence…</p><p id="intuneCoverage" class="location-health-note"></p>
    <div class="grid-toolbar"><label>Search <input id="locSearch" type="search" class="filter-select" placeholder="Location name"></label>
    <label>Site Score <select id="locStatus" class="filter-select"><option value="">All statuses</option><option value="healthy">Green</option><option value="warning">Yellow</option><option value="critical">Red</option><option value="unavailable">Unavailable</option></select></label>
    <label>Level <select id="locLevel" class="filter-select"><option value="">All levels</option></select></label><button id="intuneReset" type="button" class="btn-filter-reset">Reset filters</button></div>
    <p class="location-health-note">Intune reporting locations use the existing location assignments. Select a location for its complete Intune inventory.</p>
    <p id="intuneMessage" role="status">Loading locations…</p><ul id="intuneLocationTree" class="sw-group-tree" aria-label="Intune locations"></ul>
    <section id="intuneLocationDetail" class="location-detail" aria-label="Selected Intune location" hidden></section></section><section id="locationReviewPanel" aria-label="Location mapping review" hidden></section>`;
  const get=id=>host.querySelector(`#${id}`);
  get('locMode').onchange=event=>onModeChange(event.target.value);
  get('intuneRefresh').onclick=()=>renderIntuneLocations(host,onModeChange);
  get('locSearch').value=state.search;get('locStatus').value=state.status;
  get('locSearch').oninput=event=>{state.search=event.target.value;renderTree();};
  get('locStatus').onchange=event=>{state.status=event.target.value;renderTree();};
  get('locLevel').onchange=event=>{state.level=event.target.value;renderTree();};
  get('intuneReset').onclick=()=>{
    state.search='';state.status='';state.level='';get('locSearch').value='';get('locStatus').value='';get('locLevel').value='';renderTree();
  };
  get('locReview').onclick=()=>{
    get('locBrowse').hidden=true;
    for(const id of ['locReview','intuneRefresh','locMode']) get(id).disabled=true;
    openLocationReviews(get('locationReviewPanel'),changed=>{
      if(!active()) return;
      if(changed) return renderIntuneLocations(host,onModeChange);
      get('locBrowse').hidden=false;
      for(const id of ['locReview','intuneRefresh','locMode']) get(id).disabled=false;
      get('locReview').focus();
    });
  };
  function renderTree() {
    if(!active()) return;
    const panel=get('intuneLocationDetail');panel.remove();
    const rows=locations.filter(loc=>loc.name.toLocaleLowerCase().includes(state.search.toLocaleLowerCase()) && (!state.status || loc.scores.endpoints.status===state.status) && (!state.level || loc.level===state.level));
    get('intuneLocationTree').innerHTML=rows.map(loc=>`<li><div class="sw-group-row" data-intune-location="${e(loc.id)}"><button class="sw-group-toggle" type="button" data-toggle-intune="${e(loc.id)}" aria-expanded="${state.selected===loc.id}" aria-label="${state.selected===loc.id ? 'Collapse' : 'Expand'} ${e(loc.name)}">${state.selected===loc.id ? '▾' : '▸'}</button><span class="sw-group-folder" aria-hidden="true"></span><button class="table-location-link sw-group-name" type="button" data-open-intune="${e(loc.id)}" aria-expanded="${state.selected===loc.id}">${e(loc.name)}</button><span>${n(loc.endpoints)} devices</span>${scorePill(loc.scores.endpoints)}</div></li>`).join('');
    get('intuneMessage').textContent=!locations.length ? 'No assigned Intune locations in the stored inventory.' : !rows.length ? 'No locations match the filters.' : `${n(rows.length)} / ${n(locations.length)} Intune reporting locations`;
    const anchor=[...host.querySelectorAll('[data-intune-location]')].find(row=>row.dataset.intuneLocation===state.selected);
    if(anchor) anchor.after(panel);else get('locBrowse').append(panel);
  }
  async function open(id,focus=true) {
    state.selected=id;renderTree();
    await renderIntuneLocationPanel(get('intuneLocationDetail'),{id,focus,onClose:()=>{
      state.selected=null;
      host.querySelectorAll('[data-open-intune],[data-toggle-intune]').forEach(button=>button.setAttribute('aria-expanded','false'));
      [...host.querySelectorAll('[data-toggle-intune]')].forEach(button=>button.textContent='▸');
      ([...host.querySelectorAll('[data-open-intune]')].find(button=>button.dataset.openIntune===id) || get('intuneUnassigned'))?.focus({preventScroll:true});
    }});
  }
  get('intuneLocationTree').onclick=event=>{
    const toggle=event.target.closest('[data-toggle-intune]'),name=event.target.closest('[data-open-intune]');
    const id=toggle?.dataset.toggleIntune || name?.dataset.openIntune;if(!id) return;
    if(toggle && state.selected===id) get('intuneClose')?.click();else open(id);
  };
  try {
    const {data}=await itomApi.getLocations();if(!active()) return;
    locations=data.items.filter(loc=>loc.id!=='unassigned' && loc.endpoints>0);coverage=data.coverage.INTUNE;
    get('intuneEvidence').textContent=intuneFreshness(data.freshness.sources.INTUNE);
    get('intuneCoverage').innerHTML=`${n(coverage.assigned)} / ${n(coverage.total)} Intune devices assigned to reporting locations · ${n(coverage.unassigned)} unassigned. <button id="intuneUnassigned" type="button" class="table-location-link">Review unassigned devices</button> · <button id="intuneAllInventory" type="button" class="table-location-link">Open full inventory</button>`;
    get('intuneUnassigned').onclick=()=>open('unassigned');get('intuneAllInventory').onclick=()=>window.navigateToView?.('endpoints');
    get('locLevel').innerHTML+=[...new Set(locations.map(loc=>loc.level))].sort().map(value=>`<option value="${e(value)}">${e(value)}</option>`).join('');
    if(![...get('locLevel').options].some(option=>option.value===state.level)) state.level='';get('locLevel').value=state.level;
    const count=document.getElementById('catSitesVal'),label=document.getElementById('catSitesSub');
    if(count) count.textContent=n(locations.length);if(label) label.textContent='Intune reporting locations';
    renderTree();
    if(state.selected!==null && (state.selected==='unassigned' || locations.some(loc=>loc.id===state.selected))) await open(state.selected,false);
    else state.selected=null;
    if(focusedId) get(focusedId)?.focus({preventScroll:true});
  } catch {
    if(!active()) return;
    get('intuneMessage').innerHTML='Intune location data unavailable. <button id="intuneRetry" type="button" class="btn-filter-reset">Retry</button>';
    get('intuneRetry').onclick=()=>renderIntuneLocations(host,onModeChange);
  }
}
