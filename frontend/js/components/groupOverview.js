import { itomApi } from '../api.js?v=11';
import { escapeHtml as e, formatNumber as n } from '../utils.js';
import { renderGroupPanel, nativeHealth, scorePill, snapshotNote } from './groupPanel.js?v=2';
import { siteScoreLabel } from '../labels.js';

let mode='infrastructure', search='', selected=null, version=0;
export async function renderGroupOverview(host) {
  const focusedId=host.contains(document.activeElement) ? document.activeElement.id : null;
  const call=++version;
  host.innerHTML=`<header class="location-health-heading"><h2>Overview Table</h2><div class="location-header-actions"><label>Site Score <select id="homeScoreMode" class="filter-select"><option value="infrastructure">SolarWinds</option><option value="combined">Combined</option></select></label><label>Location search <input id="homeLocationSearch" type="search" class="filter-select" placeholder="Exact SolarWinds location names"></label></div></header>
    <p id="homeGroupEvidence" class="location-health-note" role="status">Loading location snapshot…</p><p id="homeGroupCoverage" class="location-health-note"></p>
    <div class="grid-scroll" tabindex="0" role="region" aria-label="Overview Table"><table class="itom-table group-overview"><thead><tr>${['Location','Total devices','Servers','Network devices','Other / unclassified','SolarWinds health',siteScoreLabel].map(v=>`<th scope="col">${v}</th>`).join('')}</tr></thead><tbody id="homeOverviewRows"></tbody></table></div>`;
  host.querySelector('#homeScoreMode').value=mode; host.querySelector('#homeLocationSearch').value=search;
  host.querySelector('#homeScoreMode').onchange=event=>{mode=event.target.value; renderGroupOverview(host);};
  let items=[],data;
  const current=()=>call===version && host.isConnected;
  host.querySelector('#homeLocationSearch').oninput=event=>{search=event.target.value; renderRows();};
  function renderRows() {
    const rows=host.querySelector('#homeOverviewRows');
    const oldPanel=host.querySelector('#homeGroupPanel');
    const visible=items.filter(row=>row.group.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
    rows.innerHTML=visible.map(row=>`<tr data-location="${row.group.group_id}"><td><button type="button" class="table-location-link sw-group-name" data-open-group="${row.group.group_id}" aria-expanded="${selected===row.group.group_id}">${e(row.group.name)}</button></td><td>${n(row.total_devices)}</td><td>${n(row.server_count)}</td><td>${n(row.network_count)}</td><td>${n(row.other_count)}</td><td>${nativeHealth(row.group)}</td><td title="${e(row.site_score.reason || '')}">${scorePill(row.site_score)}</td></tr>`).join('') || `<tr><td colspan="7">${data?.data_available ? 'No locations match the search.' : 'No successful SolarWinds group snapshot yet.'}</td></tr>`;
    rows.querySelectorAll('[data-open-group]').forEach(button=>button.onclick=()=>open(Number(button.dataset.openGroup)));
    if(oldPanel && visible.some(row=>row.group.group_id===selected)) insert(oldPanel);
  }
  function insert(panel) {
    const anchor=host.querySelector(`[data-location="${selected}"]`);
    if(!anchor) return;
    const tr=document.createElement('tr'),td=document.createElement('td');
    tr.className='group-overview-detail';td.colSpan=7;td.append(panel);tr.append(td);anchor.after(tr);
  }
  async function open(id,focus=true) {
    host.querySelector('.group-overview-detail')?.remove(); selected=id;
    const panel=document.createElement('section');panel.id='homeGroupPanel';panel.className='location-detail';panel.setAttribute('aria-label','Selected location');
    insert(panel);
    host.querySelectorAll('[data-open-group]').forEach(button=>button.setAttribute('aria-expanded',String(Number(button.dataset.openGroup)===id)));
    await renderGroupPanel(panel,{id,mode,prefix:'homeGroup',focus,onClose:()=>{
      selected=null; panel.closest('tr').remove();
      const button=host.querySelector(`[data-open-group="${id}"]`);button?.setAttribute('aria-expanded','false');button?.focus({preventScroll:true});
    }});
  }
  try {
    ({data}=await itomApi.getGroupOverview(mode));
    if(!current()) return;
    items=data.items;
    host.querySelector('#homeGroupEvidence').textContent=snapshotNote(data);
    const fleet=data.fleet;
    host.querySelector('#homeGroupCoverage').innerHTML=`${n(fleet.grouped_devices)} / ${n(fleet.total_devices)} devices in regular groups · ${n(fleet.ungrouped_devices)} outside groups. <button type="button" class="table-location-link" id="homeAllInventory">Open full inventory</button>. Shared devices count once in fleet totals; location rows can overlap.`;
    host.querySelector('#homeAllInventory').onclick=()=>window.navigateToView?.('infrastructure','servers');
    renderRows();
    if(selected!==null && items.some(row=>row.group.group_id===selected) && host.querySelector(`[data-location="${selected}"]`)) await open(selected,false);
    if(focusedId) host.querySelector(`#${CSS.escape(focusedId)}`)?.focus({preventScroll:true});
  } catch {
    if(!current()) return;
    host.querySelector('#homeGroupEvidence').innerHTML='Location overview unavailable. <button id="homeOverviewRetry" type="button" class="btn-filter-reset">Retry</button>';
    host.querySelector('#homeOverviewRetry').onclick=()=>renderGroupOverview(host);
  }
}
