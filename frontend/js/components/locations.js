import { itomApi } from '../api.js?v=9';
import { escapeHtml, formatNumber } from '../utils.js';
import { openCiDrawer } from './drawer.js?v=4';
import { openLocationReviews } from './locationReviews.js?v=1';
import { renderSolarWindsGroups } from './solarwindsGroups.js?v=2';
import { renderIntuneLocations } from './intuneLocations.js?v=1';

let catalogue = [], currentMode = 'auto', selected = null, issue = 'all', source = '', page = 1;
let listRequest = 0, catalogueRequest = 0, visibleCards = 24, returnFocus = null;
let searchTimer;
const tones = { healthy: 'Green', warning: 'Amber', critical: 'Red', unavailable: 'Insufficient data' };
const modes = { endpoints: 'Digital Workspace', infrastructure: 'SolarWinds', combined: 'Combined' };
const pct = component => component?.value == null ? 'Unavailable' : `${component.value.toFixed(1)}%${component.usable ? '' : component.reason === 'Source data is stale or unavailable' ? ' (stale)' : ' (incomplete data)'}`;
const coverage = component => component.coverage_pct == null ? 'Unavailable' : `${component.coverage_pct}%`;
const statusTone = status => {
  const value = (status || '').trim().toLowerCase();
  if (['noncompliant', 'down', 'critical'].includes(value)) return 'critical';
  if (['compliant', 'up'].includes(value)) return 'healthy';
  return value === 'warning' ? 'warning' : 'unknown';
};
const modeFor = location => currentMode !== 'auto' ? currentMode : location.endpoints && location.nodes ? 'combined' : location.endpoints ? 'endpoints' : 'infrastructure';
const apiPath = (id, suffix, params = {}) => `/api/v1/locations/${encodeURIComponent(id)}/${suffix}?${new URLSearchParams(params)}`;
const componentNames = { compliance: 'Compliance', node_status: 'Nodes Up', recent_checkins: 'Recent check-ins' };
const requiredKeys = mode => mode === 'combined' ? ['compliance','node_status','recent_checkins'] : mode === 'endpoints' ? ['compliance','recent_checkins'] : ['node_status'];
const sourceName = src => src === 'INTUNE' ? 'Intune' : 'SolarWinds';
const sourceScope = l => l.endpoints && l.nodes ? 'Both sources' : l.endpoints ? 'Intune only' : 'SolarWinds only';
const utcDate = raw => new Date(/Z$|[+-]\d\d:\d\d$/.test(raw) ? raw : `${raw}Z`);
const observedAt = raw => raw ? utcDate(raw).toLocaleString() : 'No successful refresh';
const issueOptions = [['all','All devices'],['noncompliant','Noncompliant'],['other_compliance','Other compliance states'],['old_checkins','Check-in over 7 days'],['old_30d','Check-in over 30 days'],['invalid_checkins','Unknown check-in'],['up','Up'],['down','Down'],['critical','Critical'],['warning','Warning'],['unmanaged','Unmanaged'],['conflict','Mapping conflict / review']];
const nodeIssues = ['up','down','critical','warning','unmanaged'];
const endpointIssues = ['noncompliant','other_compliance','old_checkins','old_30d','invalid_checkins'];
const defaultSource = () => currentMode === 'infrastructure' ? 'SOLARWINDS' : currentMode === 'endpoints' ? 'INTUNE' : '';
const inModeScope = location => currentMode === 'infrastructure' ? location.nodes > 0 : currentMode === 'endpoints' ? location.endpoints > 0 : location.endpoints + location.nodes > 0;

function updateInventoryControls() {
  const options = issueOptions.filter(([value]) => !(source === 'SOLARWINDS' && endpointIssues.includes(value)) && !(source === 'INTUNE' && nodeIssues.includes(value)));
  if (!options.some(([value]) => value === issue)) issue = 'all';
  const control = document.getElementById('locIssue');
  control.innerHTML = options.map(([value,label]) => `<option value="${value}">${label}</option>`).join('');
  control.value = issue;
  const columns = ['Device','Source','Status', ...(source === 'SOLARWINDS' ? [] : ['Last Intune check-in']), 'Location assignment'];
  document.querySelector('#locDetail thead tr').innerHTML = columns.map(label => `<th scope="col">${label}</th>`).join('');
}
const componentRatio = component => component.denominator ? 100 * component.numerator / component.denominator : null;
const componentCounts = component => `${formatNumber(component.numerator)} / ${formatNumber(component.denominator)}`;
const componentIssues = { compliance: ['noncompliant','other_compliance'], recent_checkins: ['old_checkins','invalid_checkins'], node_status: ['down','critical','warning'] };
const issueDescription = (key,count) => {
  const device = count === 1 ? 'device' : 'devices', node = count === 1 ? 'node is' : 'nodes are';
  return { noncompliant: `noncompliant ${device}`, other_compliance: `${device} in other compliance states`, old_checkins: `${device} last checked in over 7 days ago`, invalid_checkins: `${device} with unknown check-ins`, down: `${node} Down`, critical: `${node} Critical`, warning: `${node} Warning` }[key];
};

function lastCheckin(ci) {
  if (ci.source_system !== 'INTUNE') return 'Not applicable';
  const raw = ci.attributes?.last_sync_date_time;
  const date = raw ? utcDate(String(raw)) : null;
  const age = date ? Date.now() - date.getTime() : NaN;
  if (!Number.isFinite(age) || age < -300000) return 'Unknown';
  const days = Math.max(0,Math.floor(age / 86400000));
  return `<span title="${escapeHtml(observedAt(String(raw)))}">${days ? `${days} ${days === 1 ? 'day' : 'days'} ago` : 'Within 24 hours'}</span>`;
}

function scoreReason(location, mode) {
  const score = location.scores[mode];
  if (mode !== 'infrastructure' && !location.endpoints) return 'No Intune records for this group.';
  if (mode !== 'endpoints' && !location.nodes) return 'No SolarWinds records for this group.';
  if (score.reason === 'Location identity needs review') return 'Confirm location mapping before using this score.';
  const required = requiredKeys(mode).map(key => [key,location.components[key]]);
  if (score.value == null) {
    if (required.some(([,c]) => c.denominator && location.freshness[c.source_system].status !== 'FRESH')) return 'Source data is stale or unavailable. Refresh evidence before assessing health.';
    if (required.some(([,c]) => !c.denominator)) return 'Only unmanaged nodes; no monitored nodes to score.';
    return 'Required data coverage is below 95%. Review missing fields.';
  }
  const low = required.filter(([,c]) => c.denominator && 100*c.numerator < 75*c.denominator).map(([key,c]) => `${componentNames[key]}: ${componentCounts(c)}, below 75%`);
  if (low.length) return `Red because the exact counts show ${low.join('; ')}. A high average cannot override this floor; displayed percentages are rounded.`;
  const ratio = key => componentRatio(location.components[key]);
  const exact = mode === 'infrastructure' ? ratio('node_status') : mode === 'endpoints' ? (40*ratio('compliance')+25*ratio('recent_checkins'))/65 : (40*ratio('compliance')+35*ratio('node_status')+25*ratio('recent_checkins'))/100;
  const boundary = [75,90].find(target => exact < target && score.value >= target);
  if (boundary) return `Rounded display; the exact score is below ${boundary}. Colour uses the full calculation from ${required.map(([key,c]) => `${componentNames[key]} ${componentCounts(c)}`).join('; ')}.`;
  if (score.reason) return score.reason;
  return score.status === 'healthy' ? 'Within the current operating bands.' : 'Score is below the 90% green target.';
}

function cardAttention(location, mode) {
  const score = location.scores[mode];
  const required = requiredKeys(mode).map(key => [key,location.components[key]]);
  if (score.reason === 'Location identity needs review') return { kind:'data', reason:'Location mapping needs confirmation before this score can be used.', action:'review', label:'Review location mappings' };
  const stale = required.find(([,c]) => c.denominator && location.freshness[c.source_system].status !== 'FRESH');
  if (score.value == null && stale) return { kind:'data', reason:`${sourceName(stale[1].source_system)} evidence is stale or unavailable. Reload the latest saved evidence; this does not start a source sync.`, action:'refresh', label:'Reload evidence' };
  if (score.value == null) {
    const missing = required.find(([,c]) => !c.denominator);
    if (missing) return { kind:'data', reason:scoreReason(location,mode), issue:missing[0] === 'node_status' && location.issues.unmanaged ? 'unmanaged' : 'all', label:missing[0] === 'node_status' && location.issues.unmanaged ? 'View unmanaged nodes' : 'View available records' };
    const incomplete = required.find(([,c]) => !c.usable);
    const key = incomplete?.[0];
    const issue = key === 'recent_checkins' && location.issues.invalid_checkins ? 'invalid_checkins' : key === 'compliance' && location.issues.other_compliance ? 'other_compliance' : 'all';
    return { kind:'data', reason:`${key ? componentNames[key] : 'Required data'} has less than 95% known field coverage. Inspect the source records.`, issue, source:issue === 'all' ? incomplete?.[1].source_system : undefined, label:issue === 'all' ? 'View source records' : 'View records to inspect' };
  }
  const low = required.filter(([,c]) => 100*c.numerator < 75*c.denominator).sort((a,b) => componentRatio(a[1])-componentRatio(b[1]));
  if (low.length && !componentIssues[low[0][0]].some(key => location.issues[key])) {
    const [key,c] = low[0];
    return { kind:'health', reason:`${componentNames[key]}: ${componentCounts(c)}, below 75%. Inspect the underlying ${sourceName(c.source_system)} records.`, issue:'all', source:c.source_system, label:key === 'node_status' ? 'View infrastructure records' : 'View endpoint records' };
  }
  const degraded = required.find(([,c]) => ['FAILED','PARTIAL'].includes(location.freshness[c.source_system].last_attempt_status));
  const downOrCritical = mode !== 'endpoints' && (location.issues.down || location.issues.critical);
  if (!low.length && !downOrCritical && degraded) return { kind:'data', reason:`The latest ${sourceName(degraded[1].source_system)} refresh failed or was incomplete. Showing the last successful snapshot. Reload reads saved evidence; it does not start a source sync.`, action:'refresh', label:'Reload evidence' };
  const candidates = [...low.map(([key]) => key), ...(mode !== 'endpoints' ? ['node_status'] : []), ...required.map(([key]) => key)];
  const issue = candidates.flatMap(key => componentIssues[key]).find(key => location.issues[key]);
  if (issue) return { kind:'health', reason:`${formatNumber(location.issues[issue])} ${issueDescription(issue,location.issues[issue])}.`, issue, label:issue === 'old_checkins' ? 'View overdue devices' : issue === 'invalid_checkins' ? 'View unknown check-ins' : issue === 'other_compliance' ? 'View other compliance states' : `View ${issue === 'noncompliant' ? 'noncompliant devices' : issue + ' nodes'}` };
  return { kind:'health', reason:'The score is below the current operating target. Inspect the underlying records.', issue:'all', label:'View devices' };
}

function sourceEvidence(freshness, counts) {
  return ['INTUNE','SOLARWINDS'].map(src => {
    const f = freshness[src], count = counts?.[src];
    const tone = f.status === 'FRESH' ? 'healthy' : 'warning';
    return `<div data-source="${src}"><span class="status-pill status-${tone}">${sourceName(src)} · ${f.status === 'FRESH' ? 'Fresh at load' : f.status === 'STALE' ? 'Stale at load' : 'No successful refresh'}</span><span>Last success: ${escapeHtml(observedAt(f.last_synchronized_at))}${count ? ` · ${formatNumber(count.assigned)} / ${formatNumber(count.total)} assigned` : ''}${['FAILED','PARTIAL'].includes(f.last_attempt_status) ? ' · Latest refresh failed or incomplete' : ''}</span></div>`;
  }).join('');
}

export async function renderLocationScorecards(options = {}) {
  const filterIds = ['locSearch','locMode','locStatus','locLevel'];
  const savedFilters = Object.fromEntries(filterIds.map(id => [id,document.getElementById(id)?.value]));
  if (options.mode) savedFilters.locMode = options.mode;
  if (savedFilters.locMode === 'endpoints') {
    catalogueRequest++; listRequest++; clearTimeout(searchTimer);
    const host = document.getElementById('locationScorecards');
    if (host) await renderIntuneLocations(host, mode => renderLocationScorecards({mode}), savedFilters);
    return;
  }
  if (['infrastructure','combined'].includes(savedFilters.locMode || 'infrastructure')) {
    catalogueRequest++; listRequest++; clearTimeout(searchTimer);
    const groupHost = document.getElementById('locationScorecards');
    if (groupHost) await renderSolarWindsGroups(groupHost, mode => renderLocationScorecards({mode}), savedFilters.locMode || 'infrastructure');
    return;
  }
  const restoreRefreshFocus = document.activeElement?.id === 'locRefresh';
  clearTimeout(searchTimer);
  const request = ++catalogueRequest;
  listRequest++;
  selected = null;
  const host = document.getElementById('locationScorecards');
  if (!host) return;
  host.innerHTML = '<p role="status">Loading location scores…</p>';
  try {
    const response = await itomApi.getLocations();
    if (request !== catalogueRequest) return;
    catalogue = response.data.items;
    host.innerHTML = `
      <div class="location-health-heading"><div><h2>Site Score</h2></div><div class="location-header-actions"><button id="locReview" type="button" class="btn-filter-reset" aria-label="Review location mappings">Review mappings</button><button id="locRefresh" type="button" class="btn-filter-reset">Refresh</button></div></div>
      <div id="locBrowse">
      <div id="locCoverage" class="location-source-evidence">${sourceEvidence(response.data.freshness.sources,response.data.coverage)}</div>
      <div class="grid-toolbar"><label>Search <input id="locSearch" class="filter-select" type="search" placeholder="Location name"></label>
      <label>Score <select id="locMode" class="filter-select"><option value="auto">By available sources</option><option value="combined">Combined · both sources</option><option value="endpoints">Digital Workspace · Intune</option><option value="infrastructure">SolarWinds</option></select></label>
      <label>Status <select id="locStatus" class="filter-select"><option value="">All statuses</option><option value="critical">Red</option><option value="warning">Amber</option><option value="healthy">Green</option><option value="unavailable">Insufficient data</option></select></label>
      <label>Level <select id="locLevel" class="filter-select"><option value="">All levels</option>${[...new Set(catalogue.filter(l => l.id !== 'unassigned').map(l => l.level))].sort().map(level => `<option value="${escapeHtml(level)}">${escapeHtml(level)}</option>`).join('')}</select></label>
      <button id="locReset" type="button" class="btn-filter-reset">Reset</button></div>
      <div id="locSummary" class="location-summary" aria-label="Reporting group status summary"></div>
      <details class="location-comparison"><summary>Comparison guidance</summary><p id="locComparison" class="location-health-note location-comparison-note"></p></details>
      <div id="locUnassigned" class="location-unassigned"></div>
      <div class="location-results"><p id="locResults" role="status"></p></div>
      <div id="locCards" class="location-score-grid"></div><button id="locShowMore" class="btn-filter-reset location-show-more" type="button" hidden>Show more locations</button>
      <details class="location-policy"><summary>Score policy and data limits</summary><p>Green ≥90; Amber 75–&lt;90; Red &lt;75, or any required component below 75%. Down / Critical nodes or a failed latest refresh prevent Green. Unknown or stale required data gives no score.</p><p>Combined: 40% compliance + 35% nodes Up + 25% check-ins within 7 days. Endpoints: (40 × compliance + 25 × recent check-ins) / 65. Infrastructure: nodes Up / monitored nodes. Unmanaged nodes are excluded. At least 95% known field coverage is required.</p><p>These are provisional operating bands. Counts are source records; the same physical device may appear in both systems. Location assignment does not confirm current physical presence.</p></details></div>
      <section id="locDetail" class="location-detail" hidden aria-label="Location inventory"></section><section id="locationReviewPanel" hidden aria-label="Location mapping review"></section>`;
    document.getElementById('locRefresh').onclick = renderLocationScorecards;
    document.getElementById('locReview').onclick = event => {
      const reviewTrigger = event.currentTarget;
      clearTimeout(searchTimer); listRequest++; selected=null;
      document.getElementById('locBrowse').hidden=true;
      document.getElementById('locDetail').hidden=true;
      document.getElementById('locRefresh').disabled=true;
      document.getElementById('locReview').disabled=true;
      openLocationReviews(document.getElementById('locationReviewPanel'), changed => {
        if(changed) return renderLocationScorecards();
        document.getElementById('locBrowse').hidden=false;
        document.getElementById('locRefresh').disabled=false;
        document.getElementById('locReview').disabled=false;
        (reviewTrigger?.isConnected ? reviewTrigger : document.getElementById('locReview')).focus();
      });
      document.querySelector('#locationReviewPanel h3')?.setAttribute('tabindex','-1');
      document.querySelector('#locationReviewPanel h3')?.focus({preventScroll:true});
    };
    for (const [id,value] of Object.entries(savedFilters)) {
      const control = document.getElementById(id);
      if (value !== undefined && (control.tagName !== 'SELECT' || [...control.options].some(option => option.value === value))) control.value = value;
    }
    visibleCards = 24;
    for (const id of ['locSearch', 'locMode', 'locStatus', 'locLevel']) document.getElementById(id).addEventListener('input', () => {
      if (['infrastructure','combined','endpoints'].includes(document.getElementById('locMode').value)) return renderLocationScorecards({mode:document.getElementById('locMode').value});
      visibleCards = 24; renderCards();
    });
    document.getElementById('locShowMore').onclick = () => { visibleCards += 24; renderCards(); };
    document.getElementById('locReset').onclick = () => {
      for (const id of ['locSearch', 'locStatus', 'locLevel']) document.getElementById(id).value = '';
      document.getElementById('locDetail').hidden = true;
      document.getElementById('locBrowse').hidden = false;
      visibleCards = 24; selected = null; listRequest++;
      renderCards();
    };
    renderCards();
    if (restoreRefreshFocus) document.getElementById('locRefresh').focus({preventScroll:true});
  } catch (error) {
    if (request !== catalogueRequest) return;
    host.innerHTML = '<p class="inline-error" role="alert">Location data unavailable. <button id="locRetry" class="btn-filter-reset" type="button">Retry</button></p>';
    document.getElementById('locRetry').onclick = renderLocationScorecards;
  }
}

function renderCards() {
  currentMode = document.getElementById('locMode').value;
  const groups = catalogue.filter(l => l.id !== 'unassigned' && inModeScope(l));
  document.getElementById('catSitesVal').textContent = formatNumber(groups.length);
  document.getElementById('catSitesSub').textContent = `${currentMode === 'infrastructure' ? 'SolarWinds' : currentMode === 'endpoints' ? 'Intune' : 'All sources ·'} reporting groups · mixed levels`;
  document.querySelector('#locCoverage [data-source="INTUNE"]').hidden = currentMode === 'infrastructure';
  document.querySelector('#locCoverage [data-source="SOLARWINDS"]').hidden = currentMode === 'endpoints';
  const unassigned = catalogue.find(l => l.id === 'unassigned');
  const unassignedCount = currentMode === 'infrastructure' ? unassigned?.nodes || 0 : currentMode === 'endpoints' ? unassigned?.endpoints || 0 : unassigned ? unassigned.endpoints + unassigned.nodes : 0;
  const recordLabel = currentMode === 'infrastructure' ? (unassignedCount === 1 ? 'node' : 'nodes') : (unassignedCount === 1 ? 'record' : 'records');
  document.getElementById('locUnassigned').innerHTML = `<div><strong>${formatNumber(unassignedCount)} unassigned ${recordLabel}</strong><p>Excluded from location scores. Assign a reporting location to complete coverage.</p></div>${unassignedCount ? '<button type="button" class="btn-filter-reset">Review unassigned devices</button>' : ''}`;
  document.querySelector('#locUnassigned button')?.addEventListener('click', e => openLocation('unassigned','all',e.currentTarget,defaultSource()));
  const search = document.getElementById('locSearch').value.toLowerCase();
  const status = document.getElementById('locStatus').value, level = document.getElementById('locLevel').value;
  const scope = groups.filter(l => l.name.toLowerCase().includes(search) && (!level || l.level === level));
  document.getElementById('locComparison').textContent = currentMode === 'auto' ? 'By available sources can mix score modes. Choose Digital Workspace, SolarWinds or Combined and the same reporting level to compare.' : `${modes[currentMode]} uses the same calculation for every group. Compare groups at the same reporting level.`;
  document.getElementById('locSummary').innerHTML = [['','All groups'],['critical','Red'],['warning','Amber'],['unavailable','Insufficient data'],['healthy','Green']].map(([value,label]) => {
    const count = value ? scope.filter(l => l.scores[modeFor(l)].status === value).length : scope.length;
    return `<button type="button" data-status="${value}" class="location-summary-item summary-${value || 'all'}" aria-pressed="${status === value}"><strong>${formatNumber(count)}</strong><span>${label}</span></button>`;
  }).join('');
  document.querySelectorAll('#locSummary button').forEach(b => b.onclick = () => {
    const value = b.dataset.status;
    document.getElementById('locStatus').value = value; visibleCards = 24; renderCards();
    document.querySelector(`#locSummary button[data-status="${value}"]`).focus({preventScroll:true});
  });
  const locations = scope.filter(l => !status || l.scores[modeFor(l)].status === status);
  const order = { critical: 0, warning: 1, unavailable: 2, healthy: 3 };
  locations.sort((a, b) => order[a.scores[modeFor(a)].status] - order[b.scores[modeFor(b)].status] || a.name.localeCompare(b.name));
  document.getElementById('locResults').textContent = `Showing ${formatNumber(Math.min(visibleCards,locations.length))} of ${formatNumber(locations.length)} reporting groups · ${currentMode === 'auto' ? 'Status uses each group’s available sources' : modes[currentMode] + ' scores'} · As of ${observedAt(scope[0]?.as_of || catalogue[0]?.as_of)}`;
  document.getElementById('locShowMore').hidden = visibleCards >= locations.length;
  document.getElementById('locCards').innerHTML = locations.length ? locations.slice(0,visibleCards).map(l => {
    const mode = modeFor(l), score = l.scores[mode];
    const attention = score.status === 'healthy' ? null : cardAttention(l,mode);
    const explainColour = attention?.kind === 'health' && score.value != null &&
      (score.status === 'critical' && score.value >= 75 || score.status === 'warning' && score.value >= 90);
    const link = (label, key) => l.issues[key] && !(currentMode === 'endpoints' && nodeIssues.includes(key)) && !(currentMode === 'infrastructure' && endpointIssues.includes(key)) ? `<button type="button" class="location-issue issue-${['noncompliant','down','critical'].includes(key) ? 'critical' : 'warning'}" data-id="${escapeHtml(l.id)}" data-issue="${key}">${formatNumber(l.issues[key])} ${label}</button>` : '';
    return `<article class="location-score-card score-${score.status}">
      <div class="location-card-title"><button type="button" class="table-location-link" data-id="${escapeHtml(l.id)}" data-issue="all">${escapeHtml(l.name)}</button><span>${escapeHtml(l.level)}</span></div>
      <p class="location-card-scope">${sourceScope(l)}${l.issues.conflict ? ' · Mapping needs review' : ''}</p>
      <p class="location-record-counts">${formatNumber(l.endpoints)} endpoints · ${formatNumber(l.nodes)} nodes</p>
      <div class="location-score-value"><strong>${score.value == null ? '—' : score.value.toFixed(1)}</strong><span>${tones[score.status]} · ${modes[mode]}</span></div>
      ${attention ? `<div class="location-card-attention attention-${attention.kind}"><span class="location-attention-label">${attention.kind === 'data' ? 'Data / mapping attention' : 'Health attention'}</span><p class="location-main-reason">${escapeHtml(attention.reason)}</p>${explainColour ? `<p class="location-score-reason">${escapeHtml(scoreReason(l,mode))}</p>` : ''}<button type="button" class="btn-filter-reset location-primary-action" ${attention.action ? `data-action="${attention.action}"` : `data-id="${escapeHtml(l.id)}" data-issue="${attention.issue}"${attention.source ? ` data-source="${attention.source}"` : ''}`} aria-label="${escapeHtml(attention.label)} for ${escapeHtml(l.name)}">${escapeHtml(attention.label)} →</button></div>` : ''}
      <details class="location-card-details"><summary>${attention ? 'Details and other issues' : 'Details and devices'}</summary>
      ${attention && !explainColour ? `<p class="location-score-reason">${escapeHtml(scoreReason(l,mode))}</p>` : ''}
      <dl class="location-components">${[['compliance','Compliance'],['node_status','Nodes in Up status'],['recent_checkins','Check-ins within 7 days']].filter(([key]) => key === 'node_status' ? l.nodes : l.endpoints).map(([key,label]) => { const c = l.components[key]; return `<div><dt>${label}</dt><dd>${pct(c)}<small>${formatNumber(c.numerator)} / ${formatNumber(c.denominator)}</small></dd></div>`; }).join('')}</dl>
      <div class="location-issue-links">${link('Down','down')}${link('Critical','critical')}${link('noncompliant','noncompliant')}${link('check-ins >7 days','old_checkins')}${link('unknown check-ins','invalid_checkins')}${link('other compliance','other_compliance')}${link('Warning','warning')}${link('unmanaged','unmanaged')}${link('mapping reviews','conflict')}</div>
      <div class="location-card-footer"><button type="button" class="table-location-link" data-id="${escapeHtml(l.id)}" data-issue="all" aria-label="View devices for ${escapeHtml(l.name)}">View devices →</button></div><p><strong>Data evidence</strong><br>${Object.entries(l.freshness).filter(([src]) => src === 'INTUNE' ? l.endpoints : l.nodes).map(([src,f]) => `${sourceName(src)}: ${escapeHtml(f.status)} · ${escapeHtml(observedAt(f.last_synchronized_at))} · latest attempt ${escapeHtml(f.last_attempt_status || 'Unknown')}`).join('<br>')}</p><p>${Object.entries(l.components).filter(([,c]) => c.denominator).map(([key,c]) => `${componentNames[key]} field coverage: ${coverage(c)}`).join('; ')}.</p><p>Policy ${escapeHtml(l.policy_version)}. Issue counts can overlap; do not add them as unique affected devices. Percentages are rounded for display; colours use exact counts and weights.</p></details>
    </article>`;
  }).join('') : '<p>No locations match these filters.</p>';
  document.querySelectorAll('#locCards button[data-id]').forEach(button => button.onclick = () => openLocation(button.dataset.id, button.dataset.issue,button,button.dataset.source));
  document.querySelectorAll('#locCards button[data-action="review"]').forEach(button => button.onclick = event => document.getElementById('locReview').onclick(event));
  document.querySelectorAll('#locCards button[data-action="refresh"]').forEach(button => button.onclick = () => { document.getElementById('locRefresh').focus({preventScroll:true}); renderLocationScorecards(); });
}

async function openLocation(id, nextIssue, trigger, nextSource = defaultSource()) {
  clearTimeout(searchTimer);
  returnFocus = trigger;
  selected = catalogue.find(l => l.id === id); issue = nextIssue; source = nextSource; page = 1;
  if (!selected) return;
  document.getElementById('locBrowse').hidden = true;
  const host = document.getElementById('locDetail'); host.hidden = false;
  const mode = modeFor(selected), score = selected.scores[mode];
  host.innerHTML = `<div class="location-health-heading"><div><h3 id="locDetailTitle" tabindex="-1">${escapeHtml(selected.name)} inventory</h3><p>${selected.id === 'unassigned' ? 'These records need a reporting location and are excluded from location scores.' : `${escapeHtml(selected.level)} · ${sourceScope(selected)} · ${modes[mode]} score ${score.value == null ? 'unavailable' : score.value.toFixed(1) + ' / 100'} · ${tones[score.status]}`}</p></div><button id="locClose" type="button" class="btn-filter-reset">← Back to locations</button></div>
    <p class="location-health-note">${selected.id === 'unassigned' ? 'Review device details for source location and assignment evidence.' : escapeHtml(scoreReason(selected,mode))} Click a device to inspect its source details. Issue counts may overlap.</p>
    <div class="grid-toolbar"><label>Source <select id="locSource" class="filter-select"><option value="">Both sources</option><option value="INTUNE">Intune</option><option value="SOLARWINDS">SolarWinds</option></select></label>
    <label>Issue <select id="locIssue" class="filter-select">${issueOptions.map(([value,label]) => `<option value="${value}">${label}</option>`).join('')}</select></label>
    <label>Search <input id="locDeviceSearch" type="search" class="filter-select" placeholder="Device name"></label>
    <button id="locClearDetail" type="button" class="btn-filter-reset">Reset filters</button><a id="locExport" class="btn-filter-reset">Export CSV</a></div>
    <p id="locSelection" class="location-health-note" role="status"></p><div class="grid-scroll"><table class="itom-table"><caption class="sr-only">${escapeHtml(selected.name)} device inventory</caption><thead><tr><th scope="col">Device</th><th scope="col">Source</th><th scope="col">Status</th><th scope="col">Last Intune check-in</th><th scope="col">Location assignment</th></tr></thead><tbody id="locDevices"></tbody></table></div>
    <div class="grid-footer"><button id="locPrev" type="button" class="btn-filter-reset">Previous</button><span id="locPage"></span><button id="locNext" type="button" class="btn-filter-reset">Next</button></div><div id="locHistory"></div>`;
  document.getElementById('locSource').value = source;
  updateInventoryControls();
  document.getElementById('locClose').onclick = () => { clearTimeout(searchTimer); host.hidden = true; listRequest++; selected = null; document.getElementById('locBrowse').hidden = false; if (returnFocus?.isConnected) returnFocus.focus(); };
  document.getElementById('locSource').onchange = e => { source = e.target.value; page = 1; updateInventoryControls(); loadDevices(); };
  document.getElementById('locIssue').onchange = e => { issue = e.target.value; page = 1; loadDevices(); };
  document.getElementById('locDeviceSearch').oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { page = 1; loadDevices(); }, 250); };
  document.getElementById('locClearDetail').onclick = () => { source = defaultSource(); issue = 'all'; page = 1; document.getElementById('locSource').value = source; document.getElementById('locDeviceSearch').value = ''; updateInventoryControls(); loadDevices(); };
  document.getElementById('locPrev').onclick = () => { page--; loadDevices(); };
  document.getElementById('locNext').onclick = () => { page++; loadDevices(); };
  document.getElementById('locDetailTitle').focus({ preventScroll: true });
  host.scrollIntoView({ behavior: 'instant', block: 'start' });
  await loadDevices();
  if (selected?.id !== id || host.hidden) return;
  await loadHistory(id);
}

async function loadDevices() {
  const request = ++listRequest;
  const columns = source === 'SOLARWINDS' ? 4 : 5;
  const params = { issue, page, page_size: 25, search: document.getElementById('locDeviceSearch').value, ...(source ? { source } : {}) };
  document.getElementById('locDevices').innerHTML = `<tr><td colspan="${columns}">Loading inventory…</td></tr>`;
  document.getElementById('locPrev').disabled = true;
  document.getElementById('locNext').disabled = true;
  const exportParams = { issue, search: params.search, ...(source ? { source } : {}) };
  document.getElementById('locExport').href = apiPath(selected.id, 'export', exportParams);
  try {
    const response = await itomApi.getLocationDevices(selected.id, params);
    if (request !== listRequest) return;
    const data = response.data;
    if (page > data.total_pages && page > 1) { page = data.total_pages; return loadDevices(); }
    const expected = issue === 'all' ? selected.endpoints + selected.nodes : selected.issues[issue];
    document.getElementById('locSelection').textContent = `${selected.name} · ${source ? sourceName(source) : 'All available sources'} · ${issueOptions.find(([value]) => value === issue)?.[1] || issue} · ${formatNumber(data.total)} matching records · As of ${observedAt(data.as_of)}${!source && !params.search && expected !== data.total ? ' · Inventory changed since the card was loaded; refresh cards for current counts.' : ''}`;
    const assignments = {mapped:'Assigned',review:'Review needed',conflict:'Conflict',unassigned:'Unassigned'};
    document.getElementById('locDevices').innerHTML = data.items.length ? data.items.map(ci => `<tr><td><button class="table-location-link" data-ci="${escapeHtml(ci.id)}">${escapeHtml(ci.name)}</button></td><td>${sourceName(ci.source_system)}</td><td><span class="status-pill status-${statusTone(ci.status)}">${escapeHtml(ci.status || 'Unknown')}</span></td>${source === 'SOLARWINDS' ? '' : `<td>${lastCheckin(ci)}</td>`}<td>${escapeHtml(assignments[ci.location_resolution] || 'Unassigned')}</td></tr>`).join('') : `<tr><td colspan="${columns}">No devices found for this selection.</td></tr>`;
    document.querySelectorAll('#locDevices button[data-ci]').forEach(b => b.onclick = () => openCiDrawer(b.dataset.ci));
    document.getElementById('locPage').textContent = `Page ${page} of ${data.total_pages}`;
    document.getElementById('locPrev').disabled = page <= 1;
    document.getElementById('locNext').disabled = page >= data.total_pages;
  } catch (error) {
    if (request !== listRequest) return;
    document.getElementById('locDevices').innerHTML = `<tr><td colspan="${columns}" class="inline-error">Inventory unavailable. Change or reset filters to retry.</td></tr>`;
    document.getElementById('locSelection').textContent = 'Data could not be loaded; this does not mean there are zero devices.';
  }
}

async function loadHistory(id) {
  try {
    const response = await itomApi.getLocationHistory(id);
    if (selected?.id !== id || !document.getElementById('locHistory')) return;
    const rows = response.data.items.filter(row => row.policy_version === selected.policy_version && row.mapping_revision === (selected.mapping_revision || 'none'));
    document.getElementById('locHistory').innerHTML = rows.length ? `<details><summary>Score history · ${rows.length} observations</summary><p>Same policy and mapping only. These are recorded observations, not an uptime or SLA trend.</p><div class="grid-scroll"><table class="itom-table"><thead><tr><th>Observed</th><th>Endpoints</th><th>Infrastructure</th><th>Combined</th></tr></thead><tbody>${rows.map(r => `<tr><td>${escapeHtml(observedAt(r.recorded_at))}</td>${['endpoints','infrastructure','combined'].map(m => `<td>${r.data.scores[m].value ?? 'Unavailable'}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>` : '<p class="location-health-note">No score history yet for the current policy and mapping.</p>';
  } catch (error) { if (selected?.id === id) document.getElementById('locHistory').textContent = 'Score history unavailable.'; }
}
