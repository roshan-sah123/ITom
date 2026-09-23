import { itomApi } from '../api.js?v=6';

let mounted = false;
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));
const number = (value) => Number(value || 0).toLocaleString('en-US');
const age = (seconds) => seconds == null ? 'Unknown age' : seconds < 3600 ? `${Math.floor(seconds / 60)}m old` : `${Math.floor(seconds / 3600)}h old`;
const parseUtc = (value) => {
  if (!value) return null;
  const normalized = typeof value === 'string' && /T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value) ? `${value}Z` : value;
  return new Date(normalized);
};

export async function renderHome() {
  const root = document.getElementById('view-home');
  if (!root) return;
  if (!mounted) {
    mounted = true;
    root.innerHTML = `<section class="overview-hero"><div><span class="section-kicker">Operations overview</span><h1>What needs attention?</h1><p>Live operational posture across endpoint, infrastructure, and CMDB sources.</p></div><div class="overview-actions"><span class="data-badge" id="overviewFreshness">Checking freshness</span><button class="btn-action" id="overviewRefresh" type="button">Refresh data</button></div></section><section class="overview-kpis" aria-label="Fleet summary"><article class="overview-kpi"><span>Managed endpoints</span><strong id="overviewEndpoints">—</strong><small id="overviewEndpointsMeta">Microsoft Intune</small></article><article class="overview-kpi"><span>Monitored nodes</span><strong id="overviewNodes">—</strong><small id="overviewNodesMeta">SolarWinds Orion</small></article><article class="overview-kpi"><span>Configuration items</span><strong id="overviewCis">—</strong><small id="overviewCisMeta">Authoritative CMDB</small></article><article class="overview-kpi overview-kpi-risk"><span>Needs review</span><strong id="overviewRisk">—</strong><small id="overviewRiskMeta">Critical, stale, or failed</small></article></section><section class="overview-grid"><article class="ops-panel attention-panel"><header><div><span class="section-kicker">Operator queue</span><h2>Needs attention</h2></div><span class="panel-count" id="attentionCount">—</span></header><div id="attentionList" class="attention-list"><div class="panel-loading">Loading operational state…</div></div></article><article class="ops-panel source-panel"><header><div><span class="section-kicker">Trust boundary</span><h2>Source health</h2></div><span class="panel-count" id="sourceState">—</span></header><div id="sourceList" class="source-list"><div class="panel-loading">Checking sources…</div></div><div class="source-note">Every number is bound to a source snapshot and freshness contract.</div></article></section><section class="overview-lower"><article class="ops-panel"><header><div><span class="section-kicker">Workspaces</span><h2>Open an operational view</h2></div></header><div class="workspace-links"><button data-target-view="infrastructure"><b>Infrastructure</b><span>SolarWinds health, nodes, and sites</span></button><button data-target-view="endpoints"><b>Endpoints</b><span>Intune compliance and device posture</span></button><button data-target-view="cmdb"><b>CMDB</b><span>Inventory, provenance, and reconciliation</span></button><button data-target-view="sync"><b>Sync runs</b><span>Ingestion history and failures</span></button></div></article></section>`;
    root.querySelectorAll('[data-target-view]').forEach((button) => button.addEventListener('click', () => window.navigateToView?.(button.dataset.targetView)));
    document.getElementById('overviewRefresh')?.addEventListener('click', () => loadOverview(root));
  }
  await loadOverview(root);
}

async function loadOverview(root) {
  const [freshness, intune, solarwinds, cmdb] = await Promise.allSettled([itomApi.getFreshness(), itomApi.getIntuneSummary(), itomApi.getSolarWindsSummary(), itomApi.getCmdbSummary()]);
  const fresh = freshness.status === 'fulfilled' ? freshness.value : { overall_status: 'UNAVAILABLE', sources: {} };
  const i = intune.status === 'fulfilled' ? intune.value : null;
  const s = solarwinds.status === 'fulfilled' ? solarwinds.value : null;
  const c = cmdb.status === 'fulfilled' ? cmdb.value : null;
  const im = i?.metrics || {}, sm = s?.metrics || {};
  const risk = Number(im.noncompliant_devices || im.non_compliant_devices || 0) + Number(sm.low_critical_nodes || sm.low_health_count || 0) + (fresh.overall_status === 'FRESH' ? 0 : 1);
  root.querySelector('#overviewEndpoints').textContent = i ? number(im.total_managed_devices || im.total_cis) : 'Unavailable';
  root.querySelector('#overviewNodes').textContent = s ? number(sm.total_server_nodes || sm.total_cis) : 'Unavailable';
  root.querySelector('#overviewCis').textContent = c ? number(c.total_cis) : 'Unavailable';
  root.querySelector('#overviewRisk').textContent = number(risk);
  root.querySelector('#overviewEndpointsMeta').textContent = i ? `${im.compliance_rate_pct ?? '—'}% compliant` : 'Source unavailable';
  root.querySelector('#overviewNodesMeta').textContent = s ? `${sm.availability_pct ?? '—'}% available` : 'Source unavailable';
  root.querySelector('#overviewCisMeta').textContent = c ? `${number(c.high_health_count)} high health` : 'Source unavailable';
  root.querySelector('#overviewRiskMeta').textContent = fresh.overall_status === 'FRESH' ? 'Current operational exceptions' : 'Includes stale source data';
  const badge = root.querySelector('#overviewFreshness'); badge.textContent = `${fresh.overall_status || 'UNKNOWN'} · ${age(fresh.oldest_age_seconds)}`; badge.dataset.status = (fresh.overall_status || 'unknown').toLowerCase();
  const items = [];
  if (fresh.overall_status !== 'FRESH') items.push({ tone: 'critical', title: 'Source data is stale', detail: `Last successful sync is ${age(fresh.oldest_age_seconds)}. Refresh connectivity before operational decisions.`, view: 'sync', subview: '', filter: null });
  if (sm.low_critical_nodes || sm.low_health_count) items.push({ tone: 'critical', title: `${number(sm.low_critical_nodes || sm.low_health_count)} SolarWinds nodes need review`, detail: 'Low or critical health classification from the latest persisted snapshot.', view: 'infrastructure', subview: 'servers', filter: { health_tier: 'Low' } });
  if (im.noncompliant_devices || im.non_compliant_devices) items.push({ tone: 'warning', title: `${number(im.noncompliant_devices || im.non_compliant_devices)} endpoints are noncompliant`, detail: 'Microsoft Intune compliance posture requires endpoint follow-up.', view: 'endpoints', subview: '', filter: { status: 'Noncompliant' } });
  if (!items.length) items.push({ tone: 'healthy', title: 'No active exceptions reported', detail: 'All connected sources are fresh and within the current operating thresholds.', view: 'home', subview: '', filter: null });
  root.querySelector('#attentionCount').textContent = items.length;
  root.querySelector('#attentionList').innerHTML = items.map((item) => `<button class="attention-item ${item.tone}" data-target-view="${item.view}" data-target-subview="${item.subview || ''}" data-filter-params="${item.filter ? escapeHtml(JSON.stringify(item.filter)) : ''}"><span class="attention-mark"></span><span><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.detail)}</small></span><i>View</i></button>`).join('');
  root.querySelectorAll('#attentionList .attention-item').forEach((button, index) => button.addEventListener('click', () => {
    const item = items[index];
    if (item) {
      window.navigateToView?.(item.view, item.subview || '', item.filter || '');
    }
  }));
  const sourceEntries = ['INTUNE', 'SOLARWINDS'].map((key) => [key, fresh.sources?.[key]]);
  root.querySelector('#sourceState').textContent = fresh.overall_status || 'UNKNOWN';
  root.querySelector('#sourceList').innerHTML = sourceEntries.map(([key, value]) => `<div class="source-row"><span><b>${key === 'INTUNE' ? 'Microsoft Intune' : 'SolarWinds Orion'}</b><small>${value?.last_synchronized_at ? `Last sync ${parseUtc(value.last_synchronized_at).toLocaleString()}` : 'No successful sync recorded'}</small></span><strong class="source-status ${(value?.status || 'unknown').toLowerCase()}">${value?.status || 'UNKNOWN'}<small>${age(value?.age_seconds)}</small></strong></div>`).join('');
}
