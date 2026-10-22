import { workspaceLabels, applyWorkspaceLabels } from '../labels.js';
import { renderGroupOverview } from './groupOverview.js?v=1';
import { itomApi } from '../api.js?v=11';

let mounted = false;
let requestVersion = 0;
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));
const number = (value) => Number.isFinite(value) ? value.toLocaleString('en-US') : 'Unavailable';
const age = (seconds) => seconds == null ? 'Unknown age' : seconds < 3600 ? `${Math.floor(seconds / 60)}m old` : `${Math.floor(seconds / 3600)}h old`;
const timestamp = (value) => {
  if (!value) return 'Observation time unavailable';
  const normalized = typeof value === 'string' && /T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value) ? `${value}Z` : value;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? 'Observation time unavailable' : parsed.toLocaleString();
};
const metricCard = (id, label, description, view) => `<article class="overview-kpi decision-kpi"><h3>${label}</h3><strong id="${id}">—</strong><small id="${id}Evidence">Loading evidence…</small><div id="${id}Freshness" class="decision-metric-freshness" role="status">Checking source freshness…</div><div id="${id}Coverage" class="decision-metric-coverage" hidden></div><details><summary>Definition &amp; evidence</summary><p>${description}</p><div id="${id}CoverageDetail"></div><div id="${id}Definition">Loading…</div></details><button type="button" class="decision-drilldown" data-target-view="${view}">Explore ${workspaceLabels[view]}</button></article>`;

export async function renderHome() {
  const root = document.getElementById('view-home');
  if (!root) return;
  if (!mounted) {
    mounted = true;
    root.innerHTML = `<section class="overview-hero"><div><span class="section-kicker">Home page</span><h1>What needs attention?</h1><p>Current posture, actionable exceptions, and the evidence behind each decision.</p></div><div class="overview-actions"><span class="data-badge" id="overviewFreshness" role="status">Checking freshness</span><button class="btn-action" id="overviewRefresh" type="button">Reload snapshot</button></div></section>
      <section class="overview-fleet" aria-label="Inventory context"><span><b id="overviewEndpoints">—</b> managed endpoints</span><span><b id="overviewNodes">—</b> SolarWinds nodes</span><span><b id="overviewCis">—</b> configuration items</span><span class="overview-snapshot-note">Persisted snapshots · status at the last successful refresh, not historical uptime</span></section>
      <section class="overview-kpis decision-kpis" aria-label="Decision metrics">${metricCard('decisionCompliance', 'Endpoint compliance', 'Confirmed compliant endpoints / all managed endpoints. Unknown states stay in scope.', 'endpoints')}${metricCard('decisionAvailability', 'Nodes reporting Up', 'Up / monitored nodes. Explicitly Unmanaged nodes are excluded; unknown states stay in scope.', 'infrastructure')}${metricCard('decisionPressure', 'Nodes above CPU / memory thresholds', 'Observed CPU ≥75% or memory ≥80%. This is a snapshot indicator, not a capacity forecast.', 'infrastructure')}</section>
      <section id="homeOverviewTable" class="ops-panel home-location-overview" aria-label="Location overview"></section>
      <section class="overview-grid"><article class="ops-panel attention-panel"><header><div><span class="section-kicker">Operator queue</span><h2>Operational exceptions</h2></div><span class="panel-count" id="attentionCount">—</span></header><div id="attentionList" class="attention-list" aria-live="polite"><div class="panel-loading">Loading operational state…</div></div><p class="source-note">Separate populations: endpoint compliance and infrastructure classifications. Counts are never added into a risk score.</p></article><article class="ops-panel source-panel"><header><div><span class="section-kicker">Evidence guardrails</span><h2>Data confidence</h2></div><span class="panel-count" id="sourceState">—</span></header><div id="dataConfidence" class="confidence-list" aria-live="polite">Checking measurement coverage…</div><div id="sourceList" class="source-list"><div class="panel-loading">Checking sources…</div></div><div class="source-note">Freshness describes source synchronization. Recent device check-ins do not establish a fresh compliance evaluation. Review source runs under Operations in the footer.</div></article></section>
      <section class="overview-lower"><article class="ops-panel"><header><div><span class="section-kicker">Workspaces</span><h2>Open a workspace</h2></div></header><div class="workspace-links"><button data-target-view="infrastructure"><b data-workspace-label="infrastructure"></b><span>Node status, resource evidence, and locations</span></button><button data-target-view="endpoints"><b data-workspace-label="endpoints"></b><span>Compliance and device reporting posture</span></button><button data-target-view="cmdb"><b data-workspace-label="cmdb"></b><span>Inventory, provenance, and reconciliation</span></button><button data-target-view="knowledge"><b>Knowledge Centre</b><span>Onboarding, guides, and recorded training</span></button><button data-target-view="automations"><b>Automations</b><span>Future ITOM operational workflows</span></button></div></article></section>`;
    applyWorkspaceLabels(root);
    root.querySelectorAll('[data-target-view]').forEach((button) => button.addEventListener('click', () => window.navigateToView?.(button.dataset.targetView)));
    root.querySelector('#overviewRefresh').addEventListener('click', () => loadOverview(root));
  }
  await loadOverview(root);
}

function renderMetric(root, id, metric, source, freshness, latestAttempt) {
  const hasPopulation = Number.isFinite(metric?.denominator) && Number.isFinite(metric?.numerator);
  root.querySelector(`#${id}`).textContent = hasPopulation ? metric.denominator === 0 ? 'No population' : Number.isFinite(metric.value) ? `${metric.value.toFixed(1)}%` : 'Unavailable' : 'Unavailable';
  root.querySelector(`#${id}Evidence`).textContent = hasPopulation ? `${number(metric.numerator)} / ${number(metric.denominator)} in scope · ${number(metric.unknown_count)} ${id === 'decisionPressure' ? 'incomplete telemetry' : 'unknown'}` : 'Measurement evidence unavailable';
  root.querySelector(`#${id}Definition`).textContent = metric ? `${metric.definition || 'Definition unavailable'}. Population: ${metric.population || 'Unavailable'}. Coverage: ${number(metric.coverage_pct)}%. Observation: ${timestamp(metric.observed_at)}. Window: ${metric.measurement_window || 'Unavailable'}. Exclusions: ${Array.isArray(metric.exclusions) ? metric.exclusions.join('; ') || 'None' : metric.exclusions || 'None'}.` : 'The source summary did not provide this metric. Reload snapshot or inspect its workspace.';
  root.querySelector(`#${id}Definition`).textContent += ` Last successful refresh: ${freshness?.last_synchronized_at ? timestamp(freshness.last_synchronized_at) : 'Unavailable'}.`;
  const state = hasPopulation && ['FRESH','STALE','UNKNOWN'].includes(freshness?.status) ? freshness.status : 'UNAVAILABLE';
  const labels = {FRESH:'Fresh',STALE:'Stale',UNKNOWN:'No successful refresh',UNAVAILABLE:hasPopulation ? 'Freshness unavailable' : 'Unavailable'};
  const message = state === 'STALE' ? 'Showing an older snapshot.' : state === 'UNKNOWN' || !freshness ? 'Successful source refresh cannot be verified.' : '';
  const failed = ['FAILED','PARTIAL'].includes(latestAttempt);
  root.querySelector(`#${id}Freshness`).innerHTML = `<span class="data-badge" data-status="${state.toLowerCase()}">${source} · ${labels[state] || 'Freshness unavailable'}</span>${message ? `<small>${message}</small>` : ''}${failed ? '<small>Latest refresh failed or incomplete.</small>' : ''}`;
  const coverage = root.querySelector(`#${id}Coverage`);
  coverage.hidden = id !== 'decisionPressure' || !hasPopulation || metric.denominator === 0;
  if (!coverage.hidden) {
    const known = Number.isFinite(metric.coverage_pct);
    const incomplete = !known || !Number.isFinite(metric.known_count) || metric.known_count < metric.denominator;
    root.querySelector(`#${id}CoverageDetail`).textContent = `${number(metric.known_count)} / ${number(metric.denominator)} nodes have both CPU and memory readings. Incomplete readings may hide additional nodes above thresholds.`;
    coverage.classList.toggle('limited',incomplete);
    coverage.innerHTML = `<b>${known ? `${incomplete ? 'Limited coverage' : 'Complete coverage'} · ${metric.coverage_pct.toFixed(1)}%` : 'Resource coverage unavailable'}</b>`;
  }
}

async function loadOverview(root) {
  const version = ++requestVersion;
  const refresh = root.querySelector('#overviewRefresh');
  refresh.disabled = true;
  refresh.textContent = 'Reloading…';
  root.setAttribute('aria-busy', 'true');
  const locationOverview = renderGroupOverview(root.querySelector('#homeOverviewTable'));
  const results = await Promise.allSettled([itomApi.getFreshness(), itomApi.getIntuneSummary(), itomApi.getSolarWindsSummary(), itomApi.getCmdbSummary(), itomApi.getReadiness(), itomApi.getSyncStatus()]);
  if (version !== requestVersion) return;
  const [fresh, i, s, c, db, sync] = results.map((result) => result.status === 'fulfilled' ? result.value : null);
  const im = i?.metrics || {}, sm = s?.metrics || {}, idecision = i?.decision_metrics || {}, sdecision = s?.decision_metrics || {};
  const cmdbAvailable = c && c.data_available !== false;
  const effectiveStatus = !fresh || !i?.metrics || !s?.metrics || !cmdbAvailable ? 'UNAVAILABLE' : fresh.overall_status || 'UNKNOWN';
  const dbLabel = document.getElementById('databaseEngineLabel');
  if (dbLabel) dbLabel.textContent = db?.active_database_engine ? `${db.active_database_engine} · ${db.database_status}` : 'Unavailable';
  root.querySelector('#overviewEndpoints').textContent = number(im.total_managed_devices ?? im.total_cis);
  root.querySelector('#overviewNodes').textContent = number(sm.total_nodes ?? sm.total_cis);
  root.querySelector('#overviewCis').textContent = cmdbAvailable ? number(c.total_cis) : 'Unavailable';
  renderMetric(root, 'decisionCompliance', idecision.confirmed_compliance, 'Intune', fresh?.sources?.INTUNE, sync?.intune?.status);
  renderMetric(root, 'decisionAvailability', sdecision.current_node_status, 'SolarWinds', fresh?.sources?.SOLARWINDS, sync?.solarwinds?.status);
  renderMetric(root, 'decisionPressure', sdecision.resource_pressure, 'SolarWinds', fresh?.sources?.SOLARWINDS, sync?.solarwinds?.status);
  const badge = root.querySelector('#overviewFreshness');
  badge.textContent = `${effectiveStatus} · ${age(fresh?.oldest_age_seconds)}`;
  badge.dataset.status = effectiveStatus.toLowerCase();
  const items = [];
  const infrastructureExceptions = sm.low_critical_nodes ?? sm.low_health_count;
  const endpointExceptions = im.noncompliant_devices ?? im.non_compliant_devices;
  if (infrastructureExceptions > 0) items.push({ tone: 'critical', title: `${number(infrastructureExceptions)} SolarWinds nodes need review`, detail: 'Persisted low or critical classification. Check operational status and resource measurements separately.', view: 'infrastructure', subview: 'servers', filter: { health_tier: 'Low' } });
  if (endpointExceptions > 0) items.push({ tone: 'warning', title: `${number(endpointExceptions)} endpoints are noncompliant`, detail: 'Confirmed Microsoft Intune noncompliance. Open endpoint evidence to investigate policy failures.', view: 'endpoints', subview: '', filter: { status: 'Noncompliant' } });
  if (!items.length) items.push({ tone: 'neutral', title: effectiveStatus === 'FRESH' && Number.isFinite(endpointExceptions) && Number.isFinite(infrastructureExceptions) ? 'No reported operational exceptions' : 'Operational assessment incomplete', detail: 'Check data confidence before concluding that the fleet is healthy.', view: null });
  root.querySelector('#attentionCount').textContent = `${items.filter(item => item.view).length} categories`;
  root.querySelector('#attentionList').innerHTML = items.map((item, index) => {
    const content = `<span class="attention-mark" aria-hidden="true"></span><span><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.detail)}</small></span>`;
    return item.view ? `<button type="button" class="attention-item ${item.tone}" data-item-index="${index}">${content}<i>View</i></button>` : `<div class="attention-item ${item.tone}">${content}</div>`;
  }).join('');
  root.querySelectorAll('#attentionList button').forEach((button) => button.addEventListener('click', () => {
    const item = items[Number(button.dataset.itemIndex)];
    window.navigateToView?.(item.view, item.subview || '', item.filter || '');
  }));
  const confidence = [];
  if (!fresh) confidence.push('Source freshness unavailable');
  if (!i?.metrics) confidence.push('Microsoft Intune summary unavailable');
  if (!s?.metrics) confidence.push('SolarWinds summary unavailable');
  if (!cmdbAvailable) confidence.push('Assets Analytics summary unavailable');
  if (fresh && fresh.overall_status !== 'FRESH') confidence.push(`Source synchronization ${fresh.overall_status || 'unknown'} · ${age(fresh.oldest_age_seconds)}`);
  for (const source of ['INTUNE', 'SOLARWINDS']) {
    const attempt = sync?.[source.toLowerCase()]?.status || fresh?.sources?.[source]?.last_attempt_status;
    if (['FAILED', 'PARTIAL'].includes(attempt)) confidence.push(`${source} latest refresh ${attempt.toLowerCase()}; showing the last successful snapshot`);
  }
  const compliance = idecision.confirmed_compliance, checkins = idecision.recent_checkins, status = sdecision.status_evidence;
  confidence.push(compliance ? `${number(compliance.unknown_count)} endpoints lack confirmed compliance · ${number(compliance.coverage_pct)}% state coverage` : 'Endpoint compliance coverage unavailable');
  const states = idecision.compliance_state_counts;
  if (states) confidence.push(`Reported endpoint states: ${number(states.in_grace_period)} in grace period · ${number(states.error)} errors · ${number(states.conflict)} conflicts`);
  confidence.push(checkins ? `${number(checkins.numerator)} / ${number(checkins.denominator)} endpoint check-ins within 7 days · ${number(checkins.unknown_count)} missing or invalid` : 'Endpoint check-in evidence unavailable');
  confidence.push(status ? `${number(status.unknown_count)} nodes with unknown status · ${number(status.unmanaged_count)} explicitly unmanaged` : 'Node status coverage unavailable');
  const cpu = sdecision.cpu_coverage, memory = sdecision.memory_coverage;
  confidence.push(cpu && memory ? `CPU coverage ${number(cpu.numerator)} / ${number(cpu.denominator)} · Memory coverage ${number(memory.numerator)} / ${number(memory.denominator)}` : 'Resource measurement coverage unavailable');
  root.querySelector('#dataConfidence').innerHTML = confidence.map(message => `<p>${escapeHtml(message)}</p>`).join('');
  root.querySelector('#sourceState').textContent = `Sync ${effectiveStatus}`;
  const sources = [['INTUNE', i?.metrics], ['SOLARWINDS', s?.metrics]];
  root.querySelector('#sourceList').innerHTML = sources.map(([key, summary]) => {
    const value = fresh?.sources?.[key], sourceStatus = !summary || !fresh ? 'UNAVAILABLE' : value?.status || 'UNKNOWN';
    const attempt = sync?.[key.toLowerCase()]?.status || value?.last_attempt_status;
    const latest = attempt ? `Latest sync: ${attempt.toLowerCase()}${['FAILED', 'PARTIAL'].includes(attempt) ? ' · Showing last successful snapshot when available' : ''}` : 'Latest sync outcome unavailable';
    return `<div class="source-row"><span><b>${key === 'INTUNE' ? 'Microsoft Intune' : 'SolarWinds Orion'}</b><small>${value?.last_synchronized_at ? `Snapshot updated ${escapeHtml(timestamp(value.last_synchronized_at))}` : 'No successful sync recorded'}</small><small>${escapeHtml(latest)}</small></span><strong class="source-status ${sourceStatus.toLowerCase()}">${escapeHtml(sourceStatus)}<small>${age(value?.age_seconds)}</small></strong></div>`;
  }).join('');
  await locationOverview;
  refresh.disabled = false;
  refresh.textContent = 'Reload snapshot';
  root.setAttribute('aria-busy', 'false');
}
