import { itomApi } from '../api.js?v=12';
import { escapeHtml as e, formatNumber } from '../utils.js';
import { scorePill } from './groupPanel.js?v=2';
import { openCiDrawer } from './drawer.js?v=4';

const states=new Map();
const n=value=>Number.isFinite(value) ? formatNumber(value) : 'Unavailable';
const issues=[['all','All devices'],['compliant','Compliant'],['noncompliant','Noncompliant'],['other_compliance','Other compliance states'],['recent_checkins','Check-in within 7 days'],['old_checkins','Check-in over 7 days'],['invalid_checkins','Unknown check-in'],['conflict','Mapping conflict / review']];
export const observationDate=value=>value ? new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString() : 'No successful refresh';
export const intuneFreshness=f=>`Intune · ${f?.status || 'UNKNOWN'} · As of ${observationDate(f?.last_synchronized_at)}${['FAILED','PARTIAL'].includes(f?.last_attempt_status) ? ' · Latest refresh failed or incomplete; showing last successful snapshot' : ''}`;
function checkin(ci) {
  const raw=ci.attributes?.last_sync_date_time;
  const date=raw ? new Date(/Z$|[+-]\d\d:\d\d$/.test(raw) ? raw : `${raw}Z`) : null;
  const age=date ? Date.now()-date.getTime() : NaN;
  if(!Number.isFinite(age) || age < -300000) return 'Unknown';
  const days=Math.max(0,Math.floor(age/86400000));
  return `<span title="${e(observationDate(raw))}">${days ? `${days} days ago` : 'Within 24 hours'}</span>`;
}

export async function renderIntuneLocationPanel(panel,{id,onClose,focus=true}) {
  if(!states.has(id)) states.set(id,{issue:'all',search:'',page:1,pageSize:25});
  const state=states.get(id),version=Symbol();panel.renderVersion=version;panel.hidden=false;
  const active=()=>panel.isConnected && panel.renderVersion===version;
  const get=suffix=>panel.querySelector(`#intune${suffix}`);
  let summary,request=0,timer;
  panel.innerHTML=`<div class="location-health-heading"><h3 id="intuneTitle" class="sw-group-name" tabindex="-1">Loading location…</h3><button id="intuneClose" type="button" class="btn-filter-reset">← Back to locations</button></div>
    <div id="intuneSummary" role="status">Loading Intune evidence…</div>
    <div class="grid-toolbar"><label>Search <input id="intuneDeviceSearch" class="filter-select" type="search" placeholder="Device name"></label>
    <label>Issue <select id="intuneIssue" class="filter-select">${issues.map(([value,label])=>`<option value="${value}">${label}</option>`).join('')}</select></label>
    <label>Rows <select id="intunePageSize" class="filter-select">${[10,25,50,100].map(value=>`<option>${value}</option>`).join('')}</select></label>
    <button id="intuneResetDevices" type="button" class="btn-filter-reset">Reset filters</button><a id="intuneExport" class="btn-filter-reset">Export CSV</a></div>
    <p id="intuneSelection" role="status"></p><div class="grid-scroll" role="region" aria-label="Intune location devices" tabindex="0"><table class="itom-table"><caption class="sr-only">Selected Intune location devices</caption><thead><tr>${['Device','Compliance state','Operating system','Last Intune check-in','Location assignment'].map(label=>`<th scope="col">${label}</th>`).join('')}</tr></thead><tbody id="intuneDevices"></tbody></table></div>
    <div class="grid-footer"><button id="intunePrev" type="button" class="btn-filter-reset">Previous</button><span id="intunePage"></span><button id="intuneNext" type="button" class="btn-filter-reset">Next</button></div>`;
  panel.onclick=event=>event.stopPropagation();
  get('Issue').value=state.issue;get('DeviceSearch').value=state.search;get('PageSize').value=String(state.pageSize);
  get('Close').onclick=()=>{clearTimeout(timer);panel.renderVersion=null;panel.hidden=true;onClose?.();};
  get('Issue').onchange=event=>{state.issue=event.target.value;state.page=1;renderSummary();loadDevices();};
  get('DeviceSearch').oninput=event=>{state.search=event.target.value;request++;clearTimeout(timer);timer=setTimeout(()=>{state.page=1;loadDevices();},250);};
  get('PageSize').onchange=event=>{state.pageSize=Number(event.target.value);state.page=1;loadDevices();};
  get('ResetDevices').onclick=()=>{
    clearTimeout(timer);Object.assign(state,{issue:'all',search:'',page:1});get('Issue').value='all';get('DeviceSearch').value='';renderSummary();loadDevices();
  };
  get('Prev').onclick=()=>{state.page--;loadDevices();};get('Next').onclick=()=>{state.page++;loadDevices();};
  get('Devices').onclick=event=>{const button=event.target.closest('[data-ci]');if(button) openCiDrawer(button.dataset.ci);};

  function renderSummary() {
    if(!active() || !summary) return;
    const component=summary.components,score=summary.scores.endpoints;
    const tile=(value,label,count)=>`<button type="button" class="group-category-tile" data-intune-issue="${value}" aria-pressed="${state.issue===value}"><b>${n(count)}</b><span>${label}</span></button>`;
    const value=c=>c.value==null ? 'Unavailable' : `${Number(c.value).toFixed(1)}%${c.usable ? '' : ' · evidence unavailable'}`;
    get('Summary').innerHTML=`<p class="location-health-note">${e(intuneFreshness(summary.freshness.INTUNE))}</p>
      <p class="location-health-note">${id==='unassigned' ? 'Unassigned Intune devices are excluded from location scores.' : 'Intune devices assigned to this reporting location.'}</p>
      <div class="group-category-tiles" aria-label="Intune compliance counts">${tile('all','Total devices',summary.endpoints)}${tile('compliant','Compliant',summary.issues.compliant)}${tile('noncompliant','Noncompliant',summary.issues.noncompliant)}${tile('other_compliance','Other / unknown states',summary.issues.other_compliance)}</div>
      <div class="group-category-tiles" aria-label="Intune check-in counts">${tile('recent_checkins','Check-in within 7 days',summary.issues.recent_checkins)}${tile('old_checkins','Check-in over 7 days',summary.issues.old_checkins)}${tile('invalid_checkins','Unknown check-in',summary.issues.invalid_checkins)}</div>
      <div class="group-score-summary"><div><b>Intune compliance</b><span>${e(value(component.compliance))}</span><small>${n(component.compliance.numerator)} / ${n(component.compliance.denominator)} confirmed compliant</small></div><div><b>Site Score · Intune</b>${scorePill(score)}<small>${e(score.reason || 'Within the current operating bands')}</small></div></div>
      <p class="location-health-note">Site Score covers the complete selected location's Intune population. Inventory filters do not change the score. Compliance and check-in tiles describe overlapping populations.</p>
      <details class="location-policy"><summary>Score components and evidence</summary><p>Intune Site Score = (40 × compliance % + 25 × check-ins within seven days %) / 65. Green ≥90; Yellow 75–&lt;90; Red &lt;75. A required component below 75% forces Red. Stale evidence, insufficient field coverage or a location requiring review gives Unavailable; a failed latest refresh prevents Green.</p>${['compliance','recent_checkins'].map(key=>{const c=component[key];return `<p><b>${key==='compliance' ? 'Compliance' : 'Recent check-ins'}</b>: ${n(c.numerator)} / ${n(c.denominator)} · Field coverage ${c.coverage_pct==null ? 'Unavailable' : `${c.coverage_pct}%`}${c.reason ? ` · ${e(c.reason)}` : ''}</p>`;}).join('')}<p>Location assignment describes a reporting group and does not establish current physical presence.</p></details>`;
    get('Summary').querySelectorAll('[data-intune-issue]').forEach(button=>button.onclick=()=>{
      state.issue=button.dataset.intuneIssue;state.page=1;get('Issue').value=state.issue;renderSummary();loadDevices();
    });
  }

  async function loadDevices() {
    const call=++request;if(!active()) return;
    get('Prev').disabled=true;get('Next').disabled=true;get('Devices').innerHTML='<tr><td colspan="5">Loading inventory…</td></tr>';
    const params={source:'INTUNE',issue:state.issue,search:state.search,page:state.page,page_size:state.pageSize};
    get('Export').href=`/api/v1/locations/${encodeURIComponent(id)}/export?${new URLSearchParams({source:'INTUNE',issue:state.issue,search:state.search})}`;
    try {
      const {data}=await itomApi.getLocationDevices(id,params);
      if(!active() || call!==request) return;
      if(state.page>data.total_pages) {state.page=data.total_pages;return loadDevices();}
      get('Selection').textContent=`${summary?.name || 'Location'} · Intune · ${issues.find(([value])=>value===state.issue)[1]} · ${n(data.total)} matching records`;
      const assignment={mapped:'Assigned',review:'Review needed',conflict:'Conflict',unassigned:'Unassigned'};
      get('Devices').innerHTML=data.items.length ? data.items.map(ci=>`<tr><td><button type="button" class="table-location-link" data-ci="${e(ci.id)}">${e(ci.name)}</button></td><td><span class="status-pill status-${ci.status?.toLowerCase()==='compliant' ? 'healthy' : ci.status?.toLowerCase()==='noncompliant' ? 'critical' : 'unknown'}">${e(ci.status || 'Unknown')}</span></td><td>${e(ci.operating_system || ci.ci_type || 'Unavailable')}</td><td>${checkin(ci)}</td><td>${e(assignment[ci.location_resolution] || 'Unassigned')}</td></tr>`).join('') : '<tr><td colspan="5">No devices found for this selection.</td></tr>';
      get('Page').textContent=`Page ${state.page} of ${data.total_pages}`;get('Prev').disabled=state.page<=1;get('Next').disabled=state.page>=data.total_pages;
    } catch {
      if(!active() || call!==request) return;
      get('Selection').textContent='Inventory unavailable; this does not mean there are zero devices.';
      get('Devices').innerHTML='<tr><td colspan="5"><button id="intuneRetryDevices" type="button" class="btn-filter-reset">Retry</button></td></tr>';
      get('RetryDevices').onclick=loadDevices;
    }
  }
  try {
    const {data}=await itomApi.getLocationScore(id);if(!active()) return;
    summary=data;get('Title').textContent=data.name;panel.querySelector('caption').textContent=`${data.name} Intune devices`;renderSummary();
    if(focus) get('Title').focus({preventScroll:true});await loadDevices();
  } catch {
    if(!active()) return;
    get('Title').textContent='Location unavailable';get('Summary').textContent='Intune location evidence unavailable. Reload snapshot to retry.';
    get('Devices').innerHTML='<tr><td colspan="5"><button id="intuneRetrySummary" type="button" class="btn-filter-reset">Retry</button></td></tr>';
    get('RetrySummary').onclick=()=>renderIntuneLocationPanel(panel,{id,onClose,focus:false});
  }
}
