/**
 * Module 1: Infrastructure Analytics Unified Workspace
 * 4 Primary Category Cards (Servers, Networks, Campus Sites, CMDB Baseline),
 * Sub-tab switching, location-wise filtration, interactive chart slicing, and full pagination.
 */
import { itomApi } from '../api.js';
import { formatNumber, formatPercent, formatLatency, escapeHtml, calculateNewPageAnchor, debounce, exportToCsv, destroyChartSafe, generatePaginationControls } from '../utils.js';
import { openCampusTrendModal } from './modal.js';
import { openCiDrawer } from './drawer.js';

let activeSubtab = 'servers';

// Chart instances
let swHealthChartInstance = null;
let swStatusChartInstance = null;
let swVendorChartInstance = null;
let fleetTrendChartInstance = null;

// Server state
let currentSwPage = 1;
let currentSwPageSize = 25;
let activeSwSearch = '';
let activeSwHealthTier = '';
let activeSwStatus = '';
let activeSwVendor = '';
let activeSwLocation = '';
let activeSwFilterLabel = '';
let allFetchedNodes = [];
let cachedTotalServers = 0;

// Campus sites state
let campusSitesData = [];
let activeCampusRegion = 'ALL';
let campusPage = 1;
const campusPageSize = 10;

// Network devices state
let currentNetPage = 1;
let currentNetPageSize = 25;
let activeNetSearch = '';
let activeNetType = '';
let allFetchedNetDevices = [];
let cachedTotalNetworks = 0;

function asNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function metricText(value, suffix = '') {
  const number = asNumber(value);
  return number === null ? '—' : `${formatNumber(number)}${suffix}`;
}

function percentageText(value) {
  const number = asNumber(value);
  return number === null ? '—' : `${number.toFixed(1)}%`;
}

function statusCount(statuses, label) {
  return asNumber(statuses?.[label] ?? statuses?.[label.toLowerCase()]);
}

export async function renderInfrastructureWorkspace() {
  initSubtabTriggers();
  await loadInfraCategoryMetrics();
  const summary = await loadServerKpisAndCharts();
  await loadCampusSites(summary);
  await loadServerGrid();
  await loadNetworkGrid();
  initServerFilters();
  initNetworkFilters();
}

/**
 * Switch subtab programmatically or from UI
 */
export function switchInfraSubtab(subtabName, preFilterLocation = '') {
  activeSubtab = subtabName;
  document.querySelectorAll('.category-card-tab').forEach(tab => {
    if (tab.dataset.subtab === subtabName) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });

  document.querySelectorAll('.infra-subview-panel').forEach(panel => {
    if (panel.id === `subview-${subtabName}`) {
      panel.style.display = 'block';
    } else {
      panel.style.display = 'none';
    }
  });

  if (subtabName === 'servers' && preFilterLocation) {
    activeSwLocation = preFilterLocation;
    activeSwFilterLabel = `Location: ${preFilterLocation}`;
    const locSelect = document.getElementById('swLocationSelect');
    if (locSelect) locSelect.value = preFilterLocation;
    updateServerFilterBanner();
    currentSwPage = 1;
    loadServerGrid();
  }
}

function initSubtabTriggers() {
  document.querySelectorAll('.category-card-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const subtab = tab.dataset.subtab;
      if (subtab) switchInfraSubtab(subtab);
    });
  });
}

async function loadInfraCategoryMetrics() {
  try {
    const swSum = await itomApi.getSolarWindsSummary();
    const metrics = swSum.metrics || {};
    const totalServers = asNumber(metrics.total_server_nodes);
    const availability = asNumber(metrics.availability_pct);

    cachedTotalServers = totalServers ?? 0;

    const catServVal = document.getElementById('catServersVal');
    const catServSub = document.getElementById('catServersSub');
    const catNetVal = document.getElementById('catNetworksVal');
    const catNetSub = document.getElementById('catNetworksSub');
    const catSitesVal = document.getElementById('catSitesVal');
    const catSitesSub = document.getElementById('catSitesSub');
    const catBaseVal = document.getElementById('catBaselineVal');
    const catBaseSub = document.getElementById('catBaselineSub');

    if (catServVal) catServVal.textContent = metricText(totalServers);
    if (catServSub) catServSub.textContent = `${percentageText(availability)} availability`;
    if (catNetVal) catNetVal.textContent = '—';
    if (catNetSub) catNetSub.textContent = 'Not reported by node summary';
    if (catSitesVal) catSitesVal.textContent = '—';
    if (catSitesSub) catSitesSub.textContent = 'Loaded from location analytics';
    if (catBaseVal) catBaseVal.textContent = '—';
    if (catBaseSub) catBaseSub.textContent = 'CMDB baseline not reported';

  } catch (err) {
    console.error('Failed to load infra category metrics:', err);
    ['catServersVal', 'catNetVal', 'catSitesVal', 'catBaselineVal'].forEach((id) => {
      const element = document.getElementById(id);
      if (element) element.textContent = '—';
    });
  }
}

/* =========================================================================
   SUB-VIEW 1: HYBRID ENTERPRISE SERVERS
   ========================================================================= */

async function loadServerKpisAndCharts() {
  try {
    const summary = await itomApi.getSolarWindsSummary();
    const metrics = summary.metrics || {};
    const total = asNumber(metrics.total_server_nodes);
    const active = asNumber(metrics.active_monitored_nodes);
    const availability = asNumber(metrics.availability_pct);
    const unavailable = asNumber(metrics.unavailable_nodes);

    const totalEl = document.getElementById('swTotalNodesVal');
    const totalSub = document.getElementById('swTotalNodesSub');
    const slaEl = document.getElementById('swSlaVal');
    const alertsEl = document.getElementById('swAlertsVal');
    const osEl = document.getElementById('swOsVal');

    if (totalEl) totalEl.textContent = metricText(total);
    if (totalSub) totalSub.textContent = active === null ? 'Active-node count not reported' : `${formatNumber(active)} actively monitored`;
    if (slaEl) slaEl.textContent = percentageText(availability);
    if (alertsEl) alertsEl.textContent = metricText(unavailable);
    if (osEl) osEl.textContent = 'Not reported by node summary';

    // Render Charts
    renderSwHealthChart(summary.health_breakdown || {});
    renderSwStatusChart(summary.status_breakdown || metrics.status_counts || {});
    renderSwVendorChart(summary.vendor_distribution || {});
    renderSwSaturatedTriage(summary.top_saturated_servers || []);

    // Populate Campus Location Select Dropdown
    populateCampusLocationSelect();

    return summary;
  } catch (err) {
    console.error('Failed to load SolarWinds server summary:', err);
    ['swTotalNodesVal', 'swSlaVal', 'swAlertsVal', 'swOsVal'].forEach((id) => {
      const element = document.getElementById(id);
      if (element) element.textContent = '—';
    });
    return null;
  }
}

function updateServerFilterBanner() {
  const banner = document.getElementById('swActiveFilterBanner');
  const labelEl = document.getElementById('swActiveFilterLabel');
  if (!banner || !labelEl) return;

  if (activeSwFilterLabel) {
    labelEl.textContent = activeSwFilterLabel;
    banner.style.display = 'flex';
  } else {
    banner.style.display = 'none';
  }
}

function renderSwHealthChart(health) {
  const canvas = document.getElementById('swHealthChart');
  if (!canvas) return;
  swHealthChartInstance = destroyChartSafe(swHealthChartInstance);

  const labels = ['High Health', 'Medium Health', 'Low / Critical'];
  const values = [health.High || 0, health.Medium || 0, health.Low || 0];

  const ctx = canvas.getContext('2d');
  swHealthChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: values,
        backgroundColor: ['#10B981', '#F59E0B', '#EF4444'],
        borderWidth: 2,
        borderColor: '#141414'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '70%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => ` ${c.label}: ${formatNumber(c.raw)} nodes`
          }
        }
      },
      onClick: (evt, els) => {
        if (els && els.length > 0) {
          const idx = els[0].index;
          activeSwHealthTier = idx === 0 ? 'High' : idx === 1 ? 'Medium' : 'Low';
          activeSwFilterLabel = `Health Tier: ${activeSwHealthTier}`;
          const select = document.getElementById('swFilterHealth');
          if (select) select.value = activeSwHealthTier;
          updateServerFilterBanner();
          currentSwPage = 1;
          loadServerGrid();
        }
      }
    }
  });
}

function renderSwStatusChart(statusCounts) {
  const canvas = document.getElementById('swStatusChart');
  if (!canvas) return;
  swStatusChartInstance = destroyChartSafe(swStatusChartInstance);

  const labels = ['Up', 'Warning', 'Critical', 'Down', 'Unmanaged'];
  const values = [
    statusCount(statusCounts, 'Up') ?? 0,
    statusCount(statusCounts, 'Warning') ?? 0,
    statusCount(statusCounts, 'Critical') ?? 0,
    statusCount(statusCounts, 'Down') ?? 0,
    statusCount(statusCounts, 'Unmanaged') ?? statusCount(statusCounts, 'unmanaged_unknown') ?? 0,
  ];

  const ctx = canvas.getContext('2d');
  swStatusChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Nodes',
        data: values,
        backgroundColor: ['#10B981', '#F59E0B', '#EF4444', '#B91C1C', '#6B7280'],
        borderRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => ` ${c.label}: ${formatNumber(c.raw)} nodes`
          }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#9CA3AF', font: { size: 10 } } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#6B7280', font: { size: 10 } } }
      },
      onClick: (evt, els) => {
        if (els && els.length > 0) {
          activeSwStatus = labels[els[0].index];
          activeSwFilterLabel = `Status: ${activeSwStatus}`;
          const select = document.getElementById('swFilterStatus');
          if (select) select.value = activeSwStatus;
          updateServerFilterBanner();
          currentSwPage = 1;
          loadServerGrid();
        }
      }
    }
  });
}

function renderSwVendorChart(vendors) {
  const canvas = document.getElementById('swVendorChart');
  if (!canvas) return;
  swVendorChartInstance = destroyChartSafe(swVendorChartInstance);

  const labels = Object.keys(vendors);
  const values = Object.values(vendors);

  const ctx = canvas.getContext('2d');
  swVendorChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: values,
        backgroundColor: ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#6B7280', '#06B6D4', '#64748B'],
        borderWidth: 2,
        borderColor: '#141414'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '70%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => ` ${c.label}: ${formatNumber(c.raw)} nodes`
          }
        }
      },
      onClick: (evt, els) => {
        if (els && els.length > 0) {
          activeSwVendor = labels[els[0].index];
          activeSwFilterLabel = `Vendor: ${activeSwVendor}`;
          updateServerFilterBanner();
          currentSwPage = 1;
          loadServerGrid();
        }
      }
    }
  });
}

function renderSwSaturatedTriage(servers) {
  const container = document.getElementById('swSaturatedList');
  if (!container) return;

  if (!servers.length) {
    container.innerHTML = `<div style="padding: 12px; color: #6B7280; font-size: 11px;">No saturation data was returned by the SolarWinds summary.</div>`;
    return;
  }

  container.innerHTML = servers.slice(0, 5).map(s => `
    <div class="triage-item" data-name="${escapeHtml(s.Caption || s.name)}">
      <span class="triage-node-name">${escapeHtml(s.Caption || s.name)}</span>
      <div class="triage-badges">
        <span class="badge-metric badge-cpu-crit">CPU: ${s.CPULoad !== undefined ? s.CPULoad : s.cpu_load || 0}%</span>
        <span class="badge-metric badge-ram-crit">RAM: ${s.PercentMemoryUsed !== undefined ? s.PercentMemoryUsed : s.memory_used || 0}%</span>
      </div>
    </div>
  `).join('');

  container.querySelectorAll('.triage-item').forEach(item => {
    item.addEventListener('click', () => {
      const searchInput = document.getElementById('swSearchInput');
      if (searchInput) searchInput.value = item.dataset.name;
      activeSwSearch = item.dataset.name;
      activeSwFilterLabel = `Node: ${item.dataset.name}`;
      updateServerFilterBanner();
      currentSwPage = 1;
      loadServerGrid();
    });
  });
}

async function populateCampusLocationSelect() {
  const select = document.getElementById('swLocationSelect');
  if (!select) return;

  try {
    const res = await itomApi.getSolarWindsSites();
    const sites = res.data?.items || res.items || [];
    const options = [`<option value="">Campus Location (All)</option>`];
    sites.forEach(s => {
      options.push(`<option value="${escapeHtml(s.name)}">${escapeHtml(s.name)} (${s.nodes_count || 0})</option>`);
    });
    select.innerHTML = options.join('');
    if (activeSwLocation) select.value = activeSwLocation;
  } catch (err) {
    console.error('Failed to populate campus locations:', err);
  }
}

async function loadServerGrid() {
  const tbody = document.getElementById('swServerTableBody');
  const recordCountEl = document.getElementById('swRecordCount');
  const tableContainer = document.querySelector('#subview-servers .grid-scroll');
  const paginationControls = document.getElementById('swPaginationControls');
  if (!tbody) return;

  try {
    const params = {
      page: currentSwPage,
      page_size: currentSwPageSize,
      ...(activeSwSearch ? { search: activeSwSearch } : {}),
      ...(activeSwHealthTier ? { health_tier: activeSwHealthTier } : {}),
      ...(activeSwStatus ? { status: activeSwStatus } : {}),
      ...(activeSwVendor ? { vendor: activeSwVendor } : {}),
    };

    const res = await itomApi.getSolarWindsNodes(params);
    const data = res.data || res;
    allFetchedNodes = data.items || [];

    // Filter by location if specified
    if (activeSwLocation) {
      allFetchedNodes = allFetchedNodes.filter(n => {
        const campus = (n.attributes?.campus_facility || n.attributes?.site || n.name || '').toLowerCase();
        return campus.includes(activeSwLocation.toLowerCase());
      });
    }

    const totalRecords = activeSwLocation ? allFetchedNodes.length : (data.total !== undefined ? data.total : (data.pagination?.total_records || cachedTotalServers));
    const totalPages = Math.max(1, Math.ceil(totalRecords / currentSwPageSize));

    currentSwPage = Math.min(currentSwPage, totalPages);
    const startRecord = totalRecords ? (currentSwPage - 1) * currentSwPageSize + 1 : 0;
    const endRecord = Math.min(startRecord + allFetchedNodes.length - 1, totalRecords);

    if (recordCountEl) {
      recordCountEl.textContent = `Showing ${formatNumber(startRecord)}–${formatNumber(endRecord)} of ${formatNumber(totalRecords)} Server Nodes`;
    }

    if (!allFetchedNodes.length) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 32px; color: #6B7280;">No server nodes match the specified search or filter criteria.</td></tr>`;
      if (paginationControls) paginationControls.innerHTML = '';
      return;
    }

    tbody.innerHTML = allFetchedNodes.map(n => {
      const cpu = asNumber(n.attributes?.cpu_load ?? n.cpu_load);
      const ram = asNumber(n.attributes?.percent_memory_used ?? n.memory_used);
      const healthTier = n.health_tier || 'Unknown';
      const ipAddress = n.ip_address || n.attributes?.ip_address || '—';
      const latency = asNumber(n.attributes?.response_time_ms ?? n.attributes?.latency_ms ?? n.latency_ms);

      return `
        <tr>
          <td><strong>${escapeHtml(n.name)}</strong></td>
          <td class="font-mono">${escapeHtml(ipAddress)}</td>
          <td>${escapeHtml(n.vendor || '—')}</td>
          <td><span class="status-pill status-${healthTier.toLowerCase() === 'high' ? 'healthy' : healthTier.toLowerCase() === 'medium' ? 'warning' : 'critical'}">${escapeHtml(healthTier)}</span></td>
          <td class="font-mono" style="color: ${cpu === null ? 'var(--text-muted)' : cpu > 80 ? '#EF4444' : '#10B981'};">${cpu === null ? '—' : `${cpu.toFixed(1)}%`}</td>
          <td class="font-mono" style="color: ${ram === null ? 'var(--text-muted)' : ram > 85 ? '#EF4444' : '#10B981'};">${ram === null ? '—' : `${ram.toFixed(1)}%`}</td>
          <td class="font-mono">${latency === null ? '—' : `${latency.toFixed(1)}ms`}</td>
          <td>
            <button class="btn-action btn-inspect-node" data-id="${escapeHtml(n.id || '')}" style="height: 28px; padding: 0 10px; font-size: 11px;">
              Inspect
            </button>
          </td>
        </tr>
      `;
    }).join('');

    tbody.querySelectorAll('.btn-inspect-node').forEach(btn => {
      btn.addEventListener('click', () => {
        const found = allFetchedNodes.find(item => (item.id || '') === btn.dataset.id);
        if (found) openCiDrawer(found);
      });
    });

    if (tableContainer) tableContainer.scrollTop = 0;

    // Smart pagination controls
    generatePaginationControls(paginationControls, currentSwPage, totalPages, (newPage) => {
      currentSwPage = newPage;
      loadServerGrid();
    });

  } catch (err) {
    console.error('Failed to load server nodes grid:', err);
    tbody.innerHTML = `<tr><td colspan="8" class="inline-error">Unable to query SolarWinds server nodes. SWIS API offline.</td></tr>`;
  }
}

function initServerFilters() {
  const searchInput = document.getElementById('swSearchInput');
  const healthSelect = document.getElementById('swFilterHealth');
  const statusSelect = document.getElementById('swFilterStatus');
  const locationSelect = document.getElementById('swLocationSelect');
  const pageSizeSelect = document.getElementById('swPageSizeSelect');
  const resetBtn = document.getElementById('swResetFilters');
  const clearFilterBtn = document.getElementById('swClearActiveFilterBtn');
  const exportBtn = document.getElementById('swExportCsv');

  if (searchInput) {
    searchInput.addEventListener('input', debounce((e) => {
      activeSwSearch = e.target.value.trim();
      if (!activeSwSearch && activeSwFilterLabel.startsWith('Search:')) {
        activeSwFilterLabel = '';
      } else if (activeSwSearch) {
        activeSwFilterLabel = `Search: "${activeSwSearch}"`;
      }
      updateServerFilterBanner();
      currentSwPage = 1;
      loadServerGrid();
    }, 250));
  }

  if (healthSelect) {
    healthSelect.addEventListener('change', (e) => {
      activeSwHealthTier = e.target.value;
      activeSwFilterLabel = activeSwHealthTier ? `Health Tier: ${activeSwHealthTier}` : '';
      updateServerFilterBanner();
      currentSwPage = 1;
      loadServerGrid();
    });
  }

  if (statusSelect) {
    statusSelect.addEventListener('change', (e) => {
      activeSwStatus = e.target.value;
      activeSwFilterLabel = activeSwStatus ? `Status: ${activeSwStatus}` : '';
      updateServerFilterBanner();
      currentSwPage = 1;
      loadServerGrid();
    });
  }

  if (locationSelect) {
    locationSelect.addEventListener('change', (e) => {
      activeSwLocation = e.target.value;
      activeSwFilterLabel = activeSwLocation ? `Location: ${activeSwLocation}` : '';
      updateServerFilterBanner();
      currentSwPage = 1;
      loadServerGrid();
    });
  }

  if (pageSizeSelect) {
    pageSizeSelect.addEventListener('change', (e) => {
      const newSize = parseInt(e.target.value, 10);
      currentSwPage = calculateNewPageAnchor(currentSwPage, currentSwPageSize, newSize, 100);
      currentSwPageSize = newSize;
      loadServerGrid();
    });
  }

  const clearAllServerFilters = () => {
    if (searchInput) searchInput.value = '';
    if (healthSelect) healthSelect.value = '';
    if (statusSelect) statusSelect.value = '';
    if (locationSelect) locationSelect.value = '';
    activeSwSearch = '';
    activeSwHealthTier = '';
    activeSwStatus = '';
    activeSwVendor = '';
    activeSwLocation = '';
    activeSwFilterLabel = '';
    updateServerFilterBanner();
    currentSwPage = 1;
    loadServerGrid();
  };

  if (resetBtn) resetBtn.addEventListener('click', clearAllServerFilters);
  if (clearFilterBtn) clearFilterBtn.addEventListener('click', clearAllServerFilters);

  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      if (!allFetchedNodes.length) return;
      const headers = [
        { label: 'Node Name', key: 'name' },
        { label: 'IP Address', key: 'ip' },
        { label: 'Vendor', key: 'vendor' },
        { label: 'Health Tier', key: 'health_tier' },
        { label: 'CPU Load %', key: 'cpu' },
        { label: 'Memory Used %', key: 'ram' },
        { label: 'Latency ms', key: 'latency' }
      ];
      const rows = allFetchedNodes.map(n => ({
        name: n.name,
        ip: n.ip_address || n.attributes?.ip_address || '—',
        vendor: n.vendor || '—',
        health_tier: n.health_tier || 'Unknown',
        cpu: asNumber(n.attributes?.cpu_load ?? n.cpu_load) === null ? '—' : `${asNumber(n.attributes?.cpu_load ?? n.cpu_load)}%`,
        ram: asNumber(n.attributes?.percent_memory_used ?? n.memory_used) === null ? '—' : `${asNumber(n.attributes?.percent_memory_used ?? n.memory_used)}%`,
        latency: asNumber(n.attributes?.response_time_ms ?? n.attributes?.latency_ms ?? n.latency_ms) === null ? '—' : `${asNumber(n.attributes?.response_time_ms ?? n.attributes?.latency_ms ?? n.latency_ms)}ms`
      }));
      exportToCsv(`SolarWinds_Server_Nodes_Page_${currentSwPage}`, headers, rows);
    });
  }
}

/* =========================================================================
   SUB-VIEW 2: NETWORK INFRASTRUCTURE DEVICES
   ========================================================================= */

async function loadNetworkGrid() {
  const tbody = document.getElementById('netDeviceTableBody');
  const recordCountEl = document.getElementById('netRecordCount');
  const tableContainer = document.querySelector('#subview-networks .grid-scroll');
  const paginationControls = document.getElementById('netPaginationControls');
  if (!tbody) return;

  try {
    const params = {
      page: currentNetPage,
      page_size: currentNetPageSize,
      ...(activeNetSearch ? { search: activeNetSearch } : {}),
      source_system: 'SOLARWINDS'
    };

    const res = await itomApi.getCmdbCis(params);
    const data = res.data || res;
    allFetchedNetDevices = (data.items || []).filter(item => {
      const type = (item.ci_type || '').toLowerCase();
      const isNetworkDevice = type.includes('switch') || type.includes('router') || type.includes('firewall') || type.includes('appliance');
      return isNetworkDevice && (!activeNetType || type.includes(activeNetType));
    });

    // The API does not expose a network-only total. Do not label an unverified
    // aggregate as the fleet population.
    const totalRecords = allFetchedNetDevices.length;
    const totalPages = 1;

    currentNetPage = Math.min(currentNetPage, totalPages);
    const startRecord = totalRecords ? 1 : 0;
    const endRecord = Math.min(startRecord + allFetchedNetDevices.length - 1, totalRecords);

    if (recordCountEl) {
      recordCountEl.textContent = `Showing ${formatNumber(startRecord)}–${formatNumber(endRecord)} of ${formatNumber(totalRecords)} Network Devices`;
    }

    if (!allFetchedNetDevices.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 32px; color: #6B7280;">No network devices were returned by the current CMDB query.</td></tr>`;
      if (paginationControls) paginationControls.innerHTML = '';
      return;
    }

    tbody.innerHTML = allFetchedNetDevices.map(dev => {
      const healthTier = dev.health_tier || 'Unknown';
      const healthClass = healthTier.toLowerCase() === 'high' ? 'healthy' : healthTier.toLowerCase() === 'medium' ? 'warning' : 'critical';
      const latency = asNumber(dev.attributes?.response_time_ms ?? dev.attributes?.latency_ms ?? dev.latency_ms);

      return `
        <tr>
          <td><strong>${escapeHtml(dev.name)}</strong></td>
          <td class="font-mono">${escapeHtml(dev.ip_address || dev.attributes?.ip_address || '—')}</td>
          <td><span class="status-pill status-healthy">${escapeHtml(dev.ci_type || '—')}</span></td>
          <td>${escapeHtml(dev.vendor || '—')}</td>
          <td><span class="status-pill status-${healthClass}">${escapeHtml(healthTier)}</span></td>
          <td class="font-mono">${latency === null ? '—' : `${latency.toFixed(1)}ms`}</td>
          <td>
            <button class="btn-action btn-inspect-net" data-id="${escapeHtml(dev.id || '')}" style="height: 28px; padding: 0 10px; font-size: 11px;">
              Inspect
            </button>
          </td>
        </tr>
      `;
    }).join('');

    tbody.querySelectorAll('.btn-inspect-net').forEach(btn => {
      btn.addEventListener('click', () => {
        const found = allFetchedNetDevices.find(item => (item.id || '') === btn.dataset.id);
        if (found) openCiDrawer(found);
      });
    });

    if (tableContainer) tableContainer.scrollTop = 0;

    generatePaginationControls(paginationControls, currentNetPage, totalPages, (newPage) => {
      currentNetPage = newPage;
      loadNetworkGrid();
    });

  } catch (err) {
    console.error('Failed to load network devices:', err);
    tbody.innerHTML = `<tr><td colspan="7" class="inline-error">Unable to query network infrastructure.</td></tr>`;
  }
}

function initNetworkFilters() {
  const searchInput = document.getElementById('netSearchInput');
  const typeSelect = document.getElementById('netFilterType');
  const pageSizeSelect = document.getElementById('netPageSizeSelect');

  if (searchInput) {
    searchInput.addEventListener('input', debounce((e) => {
      activeNetSearch = e.target.value.trim();
      currentNetPage = 1;
      loadNetworkGrid();
    }, 250));
  }

  if (typeSelect) {
    typeSelect.addEventListener('change', (e) => {
      activeNetType = e.target.value;
      currentNetPage = 1;
      loadNetworkGrid();
    });
  }

  if (pageSizeSelect) {
    pageSizeSelect.addEventListener('change', (e) => {
      currentNetPageSize = parseInt(e.target.value, 10);
      currentNetPage = 1;
      loadNetworkGrid();
    });
  }
}

/* =========================================================================
   SUB-VIEW 3: 71 CAMPUS SITES & 24H SLA CONTINUOUS TREND
   ========================================================================= */

async function loadCampusSites(summary) {
  renderFleetStatusProfile(summary?.status_breakdown || {});
  await renderCampusFacilitiesTable();
}

function renderFleetStatusProfile(statusCounts) {
  const canvas = document.getElementById('ovFleetSlaChart');
  if (!canvas) return;
  fleetTrendChartInstance = destroyChartSafe(fleetTrendChartInstance);

  const labels = ['Up', 'Warning', 'Critical', 'Down', 'Unmanaged'];
  const values = labels.map((label) => statusCount(statusCounts, label) ?? 0);

  const ctx = canvas.getContext('2d');
  fleetTrendChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'SolarWinds nodes',
        data: values,
        backgroundColor: ['#10B981', '#F59E0B', '#EF4444', '#B91C1C', '#6B7280'],
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#9CA3AF', font: { family: 'Inter', size: 11 } } }
      },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { color: '#6B7280', font: { family: 'JetBrains Mono', size: 10 } } },
        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { color: '#6B7280', font: { family: 'JetBrains Mono', size: 10 } } },
      }
    }
  });
}

async function renderCampusFacilitiesTable() {
  const tbody = document.getElementById('ovCampusTableBody');
  const countLabel = document.getElementById('ovCampusRecordCount');
  if (!tbody) return;

  try {
    const res = await itomApi.getSolarWindsSites();
    campusSitesData = res.data?.items || res.items || [];
    renderCampusRows();
    initCampusFilters();
  } catch (err) {
    console.error('Failed to load campus facilities:', err);
    tbody.innerHTML = `<tr><td colspan="7" class="inline-error">Unable to load campus facility metrics.</td></tr>`;
  }
}

function initCampusFilters() {
  const tabs = document.querySelectorAll('.campus-reg-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      activeCampusRegion = tab.dataset.region || 'ALL';
      campusPage = 1;
      renderCampusRows();
    });
  });
}

function renderCampusRows() {
  const tbody = document.getElementById('ovCampusTableBody');
  const countLabel = document.getElementById('ovCampusRecordCount');
  const paginationControls = document.getElementById('ovCampusPagination');
  if (!tbody) return;

  let filtered = campusSitesData;
  if (activeCampusRegion !== 'ALL') {
    filtered = campusSitesData.filter(s => s.region === activeCampusRegion);
  }

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / campusPageSize));
  campusPage = Math.min(campusPage, totalPages);
  const start = (campusPage - 1) * campusPageSize;
  const items = filtered.slice(start, start + campusPageSize);

  if (countLabel) {
    countLabel.textContent = `Showing ${total ? start + 1 : 0}–${Math.min(start + campusPageSize, total)} of ${total} Facilities`;
  }

  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 24px; color: #6B7280;">No campus facilities match the selected filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(s => {
    const statusClass = s.health_status === 'healthy' ? 'healthy' : s.health_status === 'warning' ? 'warning' : 'critical';
    const statusText = s.health_status ? s.health_status.toUpperCase() : 'UNKNOWN';

    // SVG sparkline
    const points = Array.isArray(s.trend_24h) ? s.trend_24h : [];
    const siteName = s.name || s.location || 'Unnamed location';
    const nodeCount = asNumber(s.nodes_count ?? s.total_cis);
    const availability = asNumber(s.sla_pct ?? s.availability_pct);
    const avgCpu = asNumber(s.avg_cpu);
    const avgRam = asNumber(s.avg_ram);
    const hasTrend = points.length > 1;
    const minVal = hasTrend ? Math.min(...points) : 0;
    const maxVal = hasTrend ? Math.max(...points) : 1;
    const range = Math.max(1, maxVal - minVal);
    const svgPoints = points.map((p, idx) => {
      const x = (idx / (points.length - 1)) * 90 + 5;
      const y = 25 - ((p - minVal) / range) * 20;
      return `${x},${y}`;
    }).join(' ');

    return `
      <tr>
        <td><strong>${escapeHtml(siteName)}</strong></td>
        <td><span class="badge-region">${escapeHtml(s.region || 'GLOBAL')}</span></td>
        <td class="font-mono">${nodeCount === null ? '—' : formatNumber(nodeCount)}</td>
        <td class="font-mono" style="color: ${availability === null ? 'var(--text-muted)' : availability < 95 ? '#EF4444' : '#10B981'}; font-weight: 600;">${availability === null ? '—' : `${availability.toFixed(1)}%`}</td>
        <td class="font-mono">${avgCpu === null ? '—' : `${avgCpu.toFixed(1)}%`} / ${avgRam === null ? '—' : `${avgRam.toFixed(1)}%`}</td>
        <td>
          ${hasTrend ? `<svg class="sparkline-svg" viewBox="0 0 100 30"><polyline fill="none" stroke="#10B981" stroke-width="1.5" points="${svgPoints}" /></svg>` : '<span class="text-muted">Not reported</span>'}
        </td>
        <td>
          <div style="display: flex; gap: 6px; align-items: center;">
            <button class="btn-action btn-site-trend" data-name="${escapeHtml(siteName)}" data-region="${escapeHtml(s.region)}" style="height: 26px; padding: 0 8px; font-size: 11px;">
              Trend
            </button>
            <button class="btn-action btn-filter-campus-servers" data-name="${escapeHtml(siteName)}" style="height: 26px; padding: 0 8px; font-size: 11px; border-color: rgba(249, 115, 22, 0.4); color: var(--accent-ops);">
              Nodes
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.btn-site-trend').forEach(btn => {
    btn.addEventListener('click', () => {
      openCampusTrendModal(btn.dataset.name, btn.dataset.region);
    });
  });

  tbody.querySelectorAll('.btn-filter-campus-servers').forEach(btn => {
    btn.addEventListener('click', () => {
      switchInfraSubtab('servers', btn.dataset.name);
    });
  });

  // Render pagination
  if (paginationControls) {
    generatePaginationControls(paginationControls, campusPage, totalPages, (newPage) => {
      campusPage = newPage;
      renderCampusRows();
    });
  }
}
