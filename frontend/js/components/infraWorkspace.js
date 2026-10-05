/**
 * Module 1: Infrastructure Analytics Unified Workspace
 * 4 Primary Category Cards (classified servers, networks, campus sites, CMDB baseline),
 * Sub-tab switching, location-wise filtration, interactive chart slicing, and full pagination.
 */
import { itomApi } from '../api.js?v=6';
import { formatNumber, formatPercent, formatLatency, escapeHtml, calculateNewPageAnchor, debounce, exportToCsv, fetchAllFilteredRows, destroyChartSafe, generatePaginationControls } from '../utils.js';
import { openCiDrawer } from './drawer.js';

let activeSubtab = 'servers';

// Chart instances
let swHealthChartInstance = null;
let swStatusChartInstance = null;
let swVendorChartInstance = null;

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
let campusPage = 1;
const campusPageSize = 10;

// Network devices state
let currentNetPage = 1;
let currentNetPageSize = 25;
let activeNetSearch = '';
let activeNetType = '';
let activeNetLocation = '';
let allFetchedNetDevices = [];
let cachedTotalNetworks = 0;

let serverFiltersInitialized = false;

export function parseServerFilter(filterParam) {
  if (!filterParam) return {};
  if (typeof filterParam === 'object') return { ...filterParam };
  if (typeof filterParam === 'string') {
    const trimmed = filterParam.trim();
    if (!trimmed) return {};
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
      try {
        return JSON.parse(trimmed);
      } catch (e) {
        // fallback
      }
    }
    if (trimmed.includes('=')) {
      const parsed = {};
      const usp = new URLSearchParams(trimmed);
      for (const [k, v] of usp.entries()) {
        parsed[k] = v;
      }
      return parsed;
    }
    if (['Low', 'Medium', 'High'].includes(trimmed)) {
      return { health_tier: trimmed };
    }
    return { location: trimmed };
  }
  return {};
}

export function applyServerFilter(filterParam) {
  const filters = parseServerFilter(filterParam);
  if (filters.health_tier) {
    activeSwHealthTier = filters.health_tier;
    const healthSelect = document.getElementById('swFilterHealth');
    if (healthSelect) {
      healthSelect.value = filters.health_tier;
      const selectedOptionText = healthSelect.options[healthSelect.selectedIndex]?.text;
      activeSwFilterLabel = `Health Tier: ${selectedOptionText || filters.health_tier}`;
    } else {
      activeSwFilterLabel = `Health Tier: ${filters.health_tier === 'Low' ? 'Low / Critical' : filters.health_tier}`;
    }
  }
  if (filters.status) {
    activeSwStatus = filters.status;
    const statusSelect = document.getElementById('swFilterStatus');
    if (statusSelect) statusSelect.value = filters.status;
    activeSwFilterLabel = `Status: ${filters.status}`;
  }
  if (filters.location) {
    activeSwLocation = filters.location;
    const locSelect = document.getElementById('swLocationSelect');
    if (locSelect) locSelect.value = filters.location;
    activeSwFilterLabel = `Location: ${filters.location}${activeSwStatus ? ` · Status: ${activeSwStatus}` : ''}`;
  }
  if (filters.search) {
    activeSwSearch = filters.search;
    const searchInput = document.getElementById('swSearchInput');
    if (searchInput) searchInput.value = filters.search;
    activeSwFilterLabel = `Search: "${filters.search}"`;
  }
  updateServerFilterBanner();
  currentSwPage = 1;
  return loadServerGrid();
}

export async function renderInfrastructureWorkspace(subtabName = 'servers', filterParam = '') {
  initSubtabTriggers();
  initServerFilters();
  initNetworkFilters();
  await loadInfraCategoryMetrics();
  await loadServerKpisAndCharts();
  await loadCampusSites();
  if (subtabName && subtabName !== 'servers') {
    switchInfraSubtab(subtabName, filterParam);
  } else if (filterParam) {
    await applyServerFilter(filterParam);
  } else {
    await loadServerGrid();
  }
  await loadNetworkGrid();
  showUnsupportedInfrastructureViews();
}

function showUnsupportedInfrastructureViews() {
  const baseline = document.getElementById('subview-baseline');
  if (baseline) baseline.innerHTML = '<div class="coming-soon-panel"><p class="eyebrow">SolarWinds Volumes and Alerts</p><h1>Capacity & Alert Analytics</h1><p>Volume and alert APIs are not available in the current POC.</p><span>Coming soon</span></div>';
}

/**
 * Switch subtab programmatically or from UI
 */
export function switchInfraSubtab(subtabName, filterParam = '') {
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

  if (subtabName === 'servers' && filterParam) {
    applyServerFilter(filterParam);
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
    const [swSum, sitesResponse, networkResponse] = await Promise.all([
      itomApi.getSolarWindsSummary(),
      itomApi.getSolarWindsSites().catch(() => ({ data: { items: [] } })),
      itomApi.getSolarWindsNetworkDevices({ page: 1, page_size: 10 }).catch(() => ({ total: null })),
    ]);
    const metrics = swSum.metrics || {};
    const totalNodes = metrics.total_server_nodes;
    const totalServers = metrics.server_nodes_count;
    const totalNetworkDevices = metrics.network_devices_count;
    const unclassifiedNodes = metrics.unclassified_nodes_count;
    const highHealthPct = metrics.high_health_pct;
    const sites = sitesResponse.data?.items || sitesResponse.items || [];

    cachedTotalServers = totalServers;

    const catServVal = document.getElementById('catServersVal');
    const catServSub = document.getElementById('catServersSub');
    const catNetVal = document.getElementById('catNetworksVal');
    const catNetSub = document.getElementById('catNetworksSub');
    const catSitesVal = document.getElementById('catSitesVal');
    const catSitesSub = document.getElementById('catSitesSub');
    const catBaseVal = document.getElementById('catBaselineVal');
    const catBaseSub = document.getElementById('catBaselineSub');

    if (catServVal) catServVal.textContent = totalServers != null ? formatNumber(totalServers) : 'Unavailable';
    if (catServSub) catServSub.textContent = totalNodes != null
      ? `Classified servers of ${formatNumber(totalNodes)} SolarWinds nodes`
      : 'No current SolarWinds data';
    if (catNetVal) catNetVal.textContent = networkResponse.total != null ? formatNumber(networkResponse.total) : 'Unavailable';
    if (catNetSub) catNetSub.textContent = networkResponse.total != null ? 'SolarWinds node inventory' : 'Network inventory unavailable';
    if (catSitesVal) catSitesVal.textContent = formatNumber(sites.length);
    if (catSitesSub) catSitesSub.textContent = 'Find locations that need attention';
    if (catBaseVal) catBaseVal.textContent = 'Coming soon';
    if (catBaseSub) catBaseSub.textContent = 'Volume and alert APIs required';

  } catch (err) {
    console.error('Failed to load infra category metrics:', err);
  }
}

/* =========================================================================
   SUB-VIEW 1: SOLARWINDS NODE INVENTORY
   ========================================================================= */

async function loadServerKpisAndCharts() {
  try {
    const summary = await itomApi.getSolarWindsSummary();
    const metrics = summary.metrics || {};
    const total = metrics.total_nodes ?? metrics.total_server_nodes;
    const serverCount = metrics.server_nodes_count;
    const networkCount = metrics.network_devices_count;
    const unclassifiedCount = metrics.unclassified_nodes_count;
    const active = metrics.active_monitored_nodes;
    const highHealth = metrics.high_health_pct;
    const avail = metrics.availability_pct;
    const alerts = (metrics.status_counts?.warning ?? 0) + (metrics.status_counts?.critical ?? 0) + (metrics.status_counts?.down ?? 0);

    const totalEl = document.getElementById('swTotalNodesVal');
    const totalSub = document.getElementById('swTotalNodesSub');
    const slaEl = document.getElementById('swSlaVal');
    const availSub = document.getElementById('swAvailSub');
    const alertsEl = document.getElementById('swAlertsVal');
    const osEl = document.getElementById('swOsVal');

    if (totalEl) totalEl.textContent = total != null ? formatNumber(total) : 'Unavailable';
    if (totalSub) totalSub.textContent = total != null
      ? `${formatNumber(active ?? 0)} actively monitored · ${formatNumber(serverCount ?? 0)} servers · ${formatNumber(networkCount ?? 0)} network · ${formatNumber(unclassifiedCount ?? 0)} unclassified`
      : 'No current data';
    if (slaEl) slaEl.textContent = highHealth != null ? `${Number(highHealth).toFixed(1)}%` : 'Unavailable';
    if (availSub) availSub.textContent = avail != null ? `${Number(avail).toFixed(1)}%` : 'Unavailable';
    if (alertsEl) alertsEl.textContent = metrics.status_counts ? formatNumber(alerts) : 'Unavailable';
    if (osEl) osEl.textContent = Object.keys(summary.vendor_distribution || {}).join(' / ') || 'Unavailable';

    // Render Charts
    renderSwHealthChart(summary.health_breakdown || {});
    renderSwStatusChart(metrics.status_counts || {});
    renderSwVendorChart(summary.vendor_distribution || {});
    renderSwSaturatedTriage(summary.top_saturated_servers !== undefined ? summary.top_saturated_servers : null);

    // Populate Campus Location Select Dropdown
    populateCampusLocationSelect();

  } catch (err) {
    console.error('Failed to load SolarWinds server summary:', err);
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
  const values = [statusCounts.up || 0, statusCounts.warning || 0, statusCounts.critical || 0, statusCounts.down || 0, statusCounts.unmanaged_unknown || 0];

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

  if (servers === null || servers === undefined) {
    container.innerHTML = `<div style="padding: 12px; color: #9CA3AF; font-size: 11px;">Saturation telemetry unavailable.</div>`;
    return;
  }

  if (!Array.isArray(servers) || !servers.length) {
    container.innerHTML = `<div style="padding: 12px; color: #10B981; font-size: 11px;">No saturation threshold breaches (CPU ≥75% or RAM ≥80%).</div>`;
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
      options.push(`<option value="${escapeHtml(s.name)}">${escapeHtml(s.name)} (${s.total_nodes ?? s.nodes_count ?? 0})</option>`);
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
      ...(activeSwLocation ? { location: activeSwLocation } : {}),
    };

    const res = await itomApi.getSolarWindsNodes(params);
    const data = res.data || res;
    allFetchedNodes = data.items || [];

    const totalRecords = data.total !== undefined ? data.total : (data.pagination?.total_records || cachedTotalServers);
    const totalPages = Math.max(1, Math.ceil(totalRecords / currentSwPageSize));

    currentSwPage = Math.min(currentSwPage, totalPages);
    const startRecord = totalRecords > 0 ? (currentSwPage - 1) * currentSwPageSize + 1 : 0;
    const endRecord = totalRecords > 0 ? Math.min(startRecord + allFetchedNodes.length - 1, totalRecords) : 0;

    if (recordCountEl) {
      recordCountEl.textContent = `Showing ${formatNumber(startRecord)}–${formatNumber(endRecord)} of ${formatNumber(totalRecords)} SolarWinds Nodes`;
    }

    if (!allFetchedNodes.length) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding: 32px; color: #6B7280;">No SolarWinds nodes match the specified search or filter criteria.</td></tr>`;
      if (paginationControls) paginationControls.innerHTML = '';
      return;
    }

    tbody.innerHTML = allFetchedNodes.map((n, idx) => {
      const cpu = n.attributes?.cpu_load ?? n.cpu_load;
      const ram = n.attributes?.memory_used ?? n.attributes?.percent_memory_used ?? n.memory_used;
      const latency = n.attributes?.latency_ms ?? n.attributes?.response_time_ms ?? n.latency_ms;
      const healthTier = n.health_tier || 'Unknown';

      return `
        <tr>
          <td><strong class="ci-name-link" data-node-idx="${idx}" style="cursor: pointer; color: #60A5FA;" title="View node details">${escapeHtml(n.name)}</strong></td>
          <td class="font-mono">${escapeHtml(n.ip_address || n.attributes?.ip_address || 'Unavailable')}</td>
          <td>${escapeHtml(n.status || 'Unavailable')}</td>
          <td>${escapeHtml(n.ci_type || 'Unavailable')}</td>
          <td>${escapeHtml(n.vendor || 'Unavailable')}</td>
          <td><span class="status-pill status-${healthTier.toLowerCase() === 'high' ? 'healthy' : healthTier.toLowerCase() === 'medium' ? 'warning' : 'critical'}">${escapeHtml(healthTier)}</span></td>
          <td class="font-mono" style="color: ${cpu > 80 ? '#EF4444' : '#10B981'};">${cpu != null ? `${Number(cpu).toFixed(1)}%` : '—'}</td>
          <td class="font-mono" style="color: ${ram > 85 ? '#EF4444' : '#10B981'};">${ram != null ? `${Number(ram).toFixed(1)}%` : '—'}</td>
          <td class="font-mono">${latency != null ? `${Number(latency).toFixed(1)}ms` : 'Unavailable'}</td>
        </tr>
      `;
    }).join('');

    tbody.querySelectorAll('.ci-name-link').forEach(link => {
      link.addEventListener('click', () => {
        const idx = parseInt(link.dataset.nodeIdx, 10);
        if (allFetchedNodes[idx]) {
          openCiDrawer(allFetchedNodes[idx]);
        }
      });
    });

    if (tableContainer) tableContainer.scrollTop = 0;

    // Smart pagination controls
    generatePaginationControls(paginationControls, currentSwPage, totalPages, (newPage) => {
      currentSwPage = newPage;
      loadServerGrid();
    });

  } catch (err) {
    console.error('Failed to load SolarWinds nodes grid:', err);
    tbody.innerHTML = `<tr><td colspan="9" class="inline-error">Unable to query SolarWinds nodes. The inventory API may be unavailable.</td></tr>`;
  }
}

function initServerFilters() {
  if (serverFiltersInitialized) return;
  serverFiltersInitialized = true;

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
      const selectedOptionText = healthSelect.options[healthSelect.selectedIndex]?.text;
      activeSwFilterLabel = activeSwHealthTier ? `Health Tier: ${selectedOptionText || activeSwHealthTier}` : '';
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
    exportBtn.addEventListener('click', async () => {
      const originalText = exportBtn.innerHTML;
      exportBtn.disabled = true;
      exportBtn.textContent = 'Preparing CSV…';
      try {
      const filters = {
        ...(activeSwSearch ? { search: activeSwSearch } : {}),
        ...(activeSwHealthTier ? { health_tier: activeSwHealthTier } : {}),
        ...(activeSwStatus ? { status: activeSwStatus } : {}),
        ...(activeSwVendor ? { vendor: activeSwVendor } : {}),
        ...(activeSwLocation ? { location: activeSwLocation } : {}),
      };
      const exportNodes = await fetchAllFilteredRows(params => itomApi.getSolarWindsNodes(params), filters);
      if (!exportNodes.length) { window.alert('No SolarWinds nodes match the active filters.'); return; }
      const headers = [
        { label: 'Node Name', key: 'name' },
        { label: 'IP Address', key: 'ip' },
        { label: 'Operational Status', key: 'status' },
        { label: 'Device Type', key: 'device_type' },
        { label: 'Vendor', key: 'vendor' },
        { label: 'Health Tier', key: 'health_tier' },
        { label: 'CPU Load %', key: 'cpu' },
        { label: 'Memory Used %', key: 'ram' },
        { label: 'Latency ms', key: 'latency' }
      ];
      const rows = exportNodes.map(n => ({
        name: n.name,
        ip: n.ip_address || n.attributes?.ip_address || 'Unavailable',
        status: n.status || 'Unavailable',
        device_type: n.ci_type || 'Unavailable',
        vendor: n.vendor || 'Unavailable',
        health_tier: n.health_tier || 'Unknown',
        cpu: (n.attributes?.cpu_load !== undefined ? n.attributes.cpu_load : n.cpu_load || 0) + '%',
        ram: (n.attributes?.percent_memory_used !== undefined ? n.attributes.percent_memory_used : n.memory_used || 0) + '%',
        latency: (n.attributes?.latency_ms ?? n.attributes?.response_time_ms ?? n.latency_ms) != null ? `${n.attributes?.latency_ms ?? n.attributes?.response_time_ms ?? n.latency_ms}ms` : 'Unavailable'
      }));
      exportToCsv('SolarWinds_Server_Nodes_Filtered', headers, rows);
      } catch (error) {
        console.error('SolarWinds CSV export failed:', error);
        window.alert(`CSV export failed: ${error.message}`);
      } finally {
        exportBtn.disabled = false;
        exportBtn.innerHTML = originalText;
      }
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
      ...(activeNetType ? { ci_type: activeNetType } : {}),
      ...(activeNetLocation ? { location: activeNetLocation } : {}),
    };

    const res = await itomApi.getSolarWindsNetworkDevices(params);
    const data = res.data || res;
    allFetchedNetDevices = data.items || [];
    const totalRecords = data.total !== undefined ? data.total : cachedTotalNetworks;
    cachedTotalNetworks = totalRecords;
    const totalPages = Math.max(1, Math.ceil(totalRecords / currentNetPageSize));

    currentNetPage = Math.min(currentNetPage, totalPages);
    const startRecord = totalRecords ? (currentNetPage - 1) * currentNetPageSize + 1 : 0;
    const endRecord = Math.min(startRecord + allFetchedNetDevices.length - 1, totalRecords);

    if (recordCountEl) {
      recordCountEl.textContent = `Showing ${formatNumber(startRecord)}–${formatNumber(endRecord)} of ${formatNumber(totalRecords)} Network Devices`;
    }

    if (!allFetchedNetDevices.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:32px; color:#6B7280;">No network devices match the active filters.</td></tr>';
      if (paginationControls) paginationControls.innerHTML = '';
      return;
    }

    tbody.innerHTML = allFetchedNetDevices.map(dev => {
      const healthClass = (dev.health_tier || 'High').toLowerCase() === 'high' ? 'healthy' : (dev.health_tier || '').toLowerCase() === 'medium' ? 'warning' : 'critical';

      return `
        <tr>
          <td><strong>${escapeHtml(dev.name)}</strong></td>
          <td class="font-mono">${escapeHtml(dev.ip_address || dev.attributes?.ip_address || 'Unavailable')}</td>
          <td><span class="status-pill status-healthy">${escapeHtml(dev.ci_type || 'Unavailable')}</span></td>
          <td>${escapeHtml(dev.vendor || 'Unavailable')}</td>
          <td>${escapeHtml(dev.status || 'Unavailable')}</td>
          <td><span class="status-pill status-${healthClass}">${escapeHtml(dev.health_tier || 'High')}</span></td>
          <td class="font-mono">${dev.attributes?.latency_ms != null ? `${Number(dev.attributes.latency_ms).toFixed(1)}ms` : 'Unavailable'}</td>
        </tr>
      `;
    }).join('');


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
  const locationSelect = document.getElementById('netLocationSelect');
  const pageSizeSelect = document.getElementById('netPageSizeSelect');
  const exportBtn = document.getElementById('netExportCsv');

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

  if (locationSelect) {
    itomApi.getSolarWindsSites().then(response => {
      const sites = response?.data?.items || [];
      locationSelect.innerHTML = '<option value="">Location (All)</option>' + sites
        .map(site => `<option value="${escapeHtml(site.name)}">${escapeHtml(site.name)} (${site.total_nodes ?? 0})</option>`)
        .join('');
      locationSelect.value = activeNetLocation;
    }).catch(() => {});
    locationSelect.addEventListener('change', (e) => {
      activeNetLocation = e.target.value;
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

  if (exportBtn) {
    exportBtn.addEventListener('click', async () => {
      const originalText = exportBtn.innerHTML;
      exportBtn.disabled = true;
      exportBtn.textContent = 'Preparing CSV…';
      try {
        const filters = {
          ...(activeNetSearch ? { search: activeNetSearch } : {}),
          ...(activeNetType ? { ci_type: activeNetType } : {}),
          ...(activeNetLocation ? { location: activeNetLocation } : {}),
        };
        const devices = await fetchAllFilteredRows(params => itomApi.getSolarWindsNetworkDevices(params), filters);
        if (!devices.length) { window.alert('No network devices match the active filters.'); return; }
        const headers = [
          { label: 'Device Name', key: 'name' }, { label: 'IP Address', key: 'ip' },
          { label: 'Device Type', key: 'type' }, { label: 'Vendor', key: 'vendor' },
          { label: 'Operational Status', key: 'status' }, { label: 'Health Tier', key: 'health' },
          { label: 'Ping Latency ms', key: 'latency' },
        ];
        const rows = devices.map(dev => ({
          name: dev.name, ip: dev.ip_address || dev.attributes?.ip_address || 'Unavailable',
          type: dev.ci_type || 'Unavailable', vendor: dev.vendor || 'Unavailable',
          status: dev.status || 'Unavailable', health: dev.health_tier || 'High',
          latency: dev.attributes?.latency_ms ?? 'Unavailable',
        }));
        exportToCsv('SolarWinds_Network_Devices_Filtered', headers, rows);
      } catch (error) {
        console.error('SolarWinds network CSV export failed:', error);
        window.alert(`CSV export failed: ${error.message}`);
      } finally {
        exportBtn.disabled = false;
        exportBtn.innerHTML = originalText;
      }
    });
  }
}

/* =========================================================================
   SUB-VIEW 3: 71 CAMPUS SITES & 24H SLA CONTINUOUS TREND
   ========================================================================= */

async function loadCampusSites() {
  initCampusFilters();
  const tbody = document.getElementById('ovCampusTableBody');
  const summary = document.getElementById('locationHealthSummary');
  try {
    const res = await itomApi.getSolarWindsSites();
    campusSitesData = res.data?.items || res.items || [];
    renderCampusRows();
  } catch (err) {
    campusSitesData = [];
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="inline-error">Unable to load location health. Reopen this workspace to retry.</td></tr>';
    if (summary) summary.textContent = 'Location data could not be loaded.';
    document.getElementById('ovCampusRecordCount').textContent = '';
    document.getElementById('ovCampusPagination').innerHTML = '';
    console.error('Failed to load location health:', err);
  }
}

function initCampusFilters() {
  const search = document.getElementById('locationHealthSearch');
  const issues = document.getElementById('locationIssuesOnly');
  const reset = document.getElementById('locationHealthReset');
  if (!search || search.dataset.initialized) return;
  search.dataset.initialized = 'true';
  search.addEventListener('input', () => { campusPage = 1; renderCampusRows(); });
  issues.addEventListener('change', () => { campusPage = 1; renderCampusRows(); });
  reset.addEventListener('click', () => {
    search.value = '';
    issues.checked = false;
    campusPage = 1;
    renderCampusRows();
  });
}

function renderCampusRows() {
  const tbody = document.getElementById('ovCampusTableBody');
  const countLabel = document.getElementById('ovCampusRecordCount');
  const paginationControls = document.getElementById('ovCampusPagination');
  if (!tbody) return;
  const query = document.getElementById('locationHealthSearch').value.trim().toLowerCase();
  const onlyIssues = document.getElementById('locationIssuesOnly').checked;
  const count = (site, key) => Number(site[key] ?? 0);
  const issues = site => count(site, 'down_nodes') + count(site, 'warning_nodes') + count(site, 'critical_nodes');
  const filtered = campusSitesData
    .filter(site => String(site.name).toLowerCase().includes(query) && (!onlyIssues || issues(site) > 0))
    .sort((a, b) => (count(b, 'critical_nodes') + count(b, 'down_nodes')) - (count(a, 'critical_nodes') + count(a, 'down_nodes'))
      || count(b, 'warning_nodes') - count(a, 'warning_nodes') || a.name.localeCompare(b.name));
  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / campusPageSize));
  campusPage = Math.max(1, Math.min(campusPage, totalPages));
  const start = (campusPage - 1) * campusPageSize;
  const items = filtered.slice(start, start + campusPageSize);
  countLabel.textContent = `Showing ${total ? start + 1 : 0}–${Math.min(start + campusPageSize, total)} of ${formatNumber(total)} locations`;
  document.getElementById('locationHealthSummary').textContent = `${formatNumber(filtered.reduce((sum, site) => sum + count(site, 'total_nodes'), 0))} devices across ${formatNumber(total)} locations · ${formatNumber(filtered.filter(site => issues(site) > 0).length)} locations with Down, Warning or Critical devices. Other / Unmanaged contains all remaining statuses.`;
  paginationControls.innerHTML = '';
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="location-empty">No locations match these filters. Try another search or reset the filters.</td></tr>';
    return;
  }
  const statusCell = (site, key, status, tone) => {
    const value = count(site, key);
    return value > 0
      ? `<td class="location-count"><button class="location-status ${tone}" data-location="${escapeHtml(site.name)}" data-status="${status}" aria-label="${escapeHtml(site.name)}: ${value} ${status} devices">${formatNumber(value)}</button></td>`
      : '<td class="location-count"><span class="location-zero">0</span></td>';
  };
  tbody.innerHTML = items.map(site => {
    const other = count(site, 'total_nodes') - count(site, 'up_nodes') - issues(site);
    return `<tr>
      <td><button class="table-location-link" data-location="${escapeHtml(site.name)}" data-status="">${escapeHtml(site.name)}</button></td>
      <td class="location-count"><button class="table-location-link" data-location="${escapeHtml(site.name)}" data-status="" aria-label="All devices at ${escapeHtml(site.name)}">${formatNumber(count(site, 'total_nodes'))}</button></td>
      ${statusCell(site, 'up_nodes', 'Up', 'status-healthy')}
      ${statusCell(site, 'down_nodes', 'Down', 'status-critical')}
      ${statusCell(site, 'warning_nodes', 'Warning', 'status-warning')}
      ${statusCell(site, 'critical_nodes', 'Critical', 'status-critical')}
      <td class="location-count">${formatNumber(other)}</td>
    </tr>`;
  }).join('');
  tbody.querySelectorAll('button[data-location]').forEach(button => {
    button.addEventListener('click', () => {
      // The chosen count must open exactly that location/status, without old filters.
      activeSwSearch = '';
      activeSwHealthTier = '';
      activeSwVendor = '';
      activeSwStatus = button.dataset.status;
      for (const id of ['swSearchInput', 'swFilterHealth', 'swFilterVendor']) {
        const control = document.getElementById(id);
        if (control) control.value = '';
      }
      const statusControl = document.getElementById('swFilterStatus');
      if (statusControl) statusControl.value = activeSwStatus;
      switchInfraSubtab('servers', button.dataset.location);
    });
  });
  if (totalPages > 1) generatePaginationControls(paginationControls, campusPage, totalPages, page => {
    campusPage = page;
    renderCampusRows();
  });
}
