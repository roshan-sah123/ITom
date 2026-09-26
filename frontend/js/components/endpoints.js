/**
 * Module 3: Digital Workplace Experience (DEX) / Endpoints (Microsoft Intune Cloud Mirror)
 * 4 KPI cards, 5 visualizations, interactive chart slice filtering, true full pagination across 27,412 devices
 */
import { itomApi } from '../api.js?v=4';
import { formatNumber, formatPercent, escapeHtml, calculateNewPageAnchor, debounce, exportToCsv, fetchAllFilteredRows, destroyChartSafe, generatePaginationControls } from '../utils.js';
import { openCiDrawer } from './drawer.js';

let osChartInstance = null;
let complianceChartInstance = null;
let mfgChartInstance = null;

let currentEpPage = 1;
let currentEpPageSize = 25;
let activeEpSearch = '';
let activeEpStatus = '';
let activeEpVendor = '';
let activeEpFilterLabel = '';

let allFetchedDevices = [];
let cachedTotalRecords = 0;

let endpointsFiltersInitialized = false;

export function parseEndpointFilter(filterParam) {
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
    if (['Compliant', 'Noncompliant', 'ConfigManager'].includes(trimmed)) {
      return { status: trimmed };
    }
    return { search: trimmed };
  }
  return {};
}

export function applyEndpointFilter(filterParam) {
  applyEndpointFilterState(filterParam);
  return loadEndpointsGrid();
}

function applyEndpointFilterState(filterParam) {
  const filters = parseEndpointFilter(filterParam);
  if (filters.status) {
    activeEpStatus = filters.status;
    const statusSelect = document.getElementById('epFilterStatus');
    if (statusSelect) statusSelect.value = filters.status;
    activeEpFilterLabel = `Compliance: ${filters.status}`;
  }
  if (filters.search) {
    activeEpSearch = filters.search;
    const searchInput = document.getElementById('epSearchInput');
    if (searchInput) searchInput.value = filters.search;
    activeEpFilterLabel = `Search: "${filters.search}"`;
  }
  if (filters.vendor) {
    activeEpVendor = filters.vendor;
    activeEpFilterLabel = `Manufacturer: ${filters.vendor}`;
  }
  updateActiveFilterBanner();
  currentEpPage = 1;
}

export async function renderEndpoints(subtabName = '', filterParam = '') {
  initEndpointsFilters();
  await loadEndpointsKpisAndCharts();
  if (filterParam) {
    applyEndpointFilterState(filterParam);
  }
  await loadEndpointsGrid();
}

async function loadEndpointsKpisAndCharts() {
  try {
    const summary = await itomApi.getIntuneSummary();
    const metrics = summary.metrics || {};
    const available = summary.data_available !== false && metrics.total_managed_devices != null;
    const total = metrics.total_managed_devices ?? 0;
    const compliant = metrics.compliant_devices ?? 0;
    const compRate = metrics.compliance_rate_pct;

    cachedTotalRecords = total;
    if (!available) {
      renderEndpointsUnavailable();
      return;
    }
    renderStoragePanel(metrics, total, available);

    const totalEl = document.getElementById('epTotalVal');
    const totalSub = document.getElementById('epTotalSub');
    const compEl = document.getElementById('epCompRateVal');
    const compSub = document.getElementById('epCompRateSub');
    const osDivEl = document.getElementById('epOsDiversityVal');
    const osSubEl = document.getElementById('epOsDiversitySub');
    const zeroTrustEl = document.getElementById('epZeroTrustVal');

    if (totalEl) totalEl.textContent = available ? formatNumber(total) : 'Unavailable';
    if (totalSub) totalSub.textContent = available ? `${formatNumber(compliant)} compliant` : 'No current Intune data';
    if (compEl) compEl.textContent = compRate != null ? `${Number(compRate).toFixed(1)}%` : 'Unavailable';
    if (compSub) compSub.textContent = compRate != null ? 'Calculated from current device status' : 'No current compliance metric';
    if (osDivEl) osDivEl.textContent = Object.keys(summary.os_distribution || summary.os_breakdown || {}).join(' / ') || 'Unavailable';
    if (osSubEl) osSubEl.textContent = Object.keys(summary.os_distribution || summary.os_breakdown || {}).length ? 'Current Intune device types' : 'No current Intune data';
    if (zeroTrustEl) zeroTrustEl.textContent = 'Coming soon';

    // 1. OS Distribution (with click filtering)
    renderOsChart(summary.os_distribution || summary.os_breakdown || {});

    // 2. Compliance Chart (with click filtering)
    renderComplianceChart(summary.compliance_breakdown || {});

    // 3. Manufacturer Chart (with click filtering)
    renderMfgChart(summary.vendor_distribution || summary.manufacturer_breakdown || {});

    // 4. Inactivity & Modernization Widgets

  } catch (err) {
    console.error('Failed to load endpoints summary:', err);
    renderEndpointsUnavailable();
  }
}

function renderEndpointsUnavailable() {
  cachedTotalRecords = 0;
  allFetchedDevices = [];
  const unavailableValues = ['epTotalVal', 'epCompRateVal', 'epOsDiversityVal'];
  unavailableValues.forEach((id) => {
    const element = document.getElementById(id);
    if (element) element.textContent = 'Unavailable';
  });
  const totalSub = document.getElementById('epTotalSub');
  const compSub = document.getElementById('epCompRateSub');
  const osSub = document.getElementById('epOsDiversitySub');
  if (totalSub) totalSub.textContent = 'Intune data is unavailable';
  if (compSub) compSub.textContent = 'Intune data is unavailable';
  if (osSub) osSub.textContent = 'Intune data is unavailable';

  renderStorageDemo();
  renderOsChart({});
  renderComplianceChart({});
  renderMfgChart({});
}

function renderStoragePanel(metrics, total, sourceAvailable) {
  const badge = document.getElementById('epStorageBadge');
  const content = document.getElementById('epStorageContent');
  if (!badge || !content) return;

  const median = Number(metrics.median_device_storage_used_pct);
  const capacity = Number(metrics.fleet_capacity_used_pct ?? metrics.avg_storage_used_pct);
  const sample = Number(metrics.storage_sample_size);
  const hasLiveStorage = sourceAvailable && total > 0 && sample > 0
    && Number.isFinite(median) && median >= 0 && median <= 100
    && Number.isFinite(capacity) && capacity >= 0 && capacity <= 100;

  if (!hasLiveStorage) {
    renderStorageDemo();
    return;
  }

  badge.textContent = 'Live Intune data';
  badge.dataset.mode = 'live';
  content.innerHTML = `${renderStorageMeter('Median per-device usage', median)}
    ${renderStorageMeter('Fleet capacity used', capacity)}
    <p class="storage-note">Based on ${formatNumber(sample)} devices with storage data (${formatPercent((sample / total) * 100, 1)} of the managed fleet). Fleet capacity is weighted by disk size.</p>`;
}

function renderStorageDemo() {
  const badge = document.getElementById('epStorageBadge');
  const content = document.getElementById('epStorageContent');
  if (!badge || !content) return;

  badge.textContent = 'DEMO DATA';
  badge.dataset.mode = 'demo';
  content.innerHTML = `${renderStorageMeter('Median per-device usage (demo)', 68)}
    ${renderStorageMeter('Fleet capacity used (demo)', 41)}
    <p class="storage-note storage-demo-note">Example values only — not live device measurements. Intune storage metrics are unavailable.</p>`;
}

function renderStorageMeter(label, value) {
  const safeValue = Math.max(0, Math.min(100, value));
  return `<div class="storage-meter">
      <div class="storage-meter-label"><span>${label}</span><strong>${formatPercent(safeValue, 1)}</strong></div>
      <div class="storage-meter-track" role="progressbar" aria-label="${label}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${safeValue}">
        <span style="width:${safeValue}%"></span>
      </div>
    </div>`;
}

function updateActiveFilterBanner() {
  const banner = document.getElementById('epActiveFilterBanner');
  const labelEl = document.getElementById('epActiveFilterLabel');
  if (!banner || !labelEl) return;

  if (activeEpFilterLabel) {
    labelEl.textContent = activeEpFilterLabel;
    banner.style.display = 'flex';
  } else {
    banner.style.display = 'none';
  }
}

function renderOsChart(osData) {
  const canvas = document.getElementById('epOsChart');
  if (!canvas) return;
  osChartInstance = destroyChartSafe(osChartInstance);

  const labels = Object.keys(osData);
  const values = Object.values(osData);

  const ctx = canvas.getContext('2d');
  osChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: values,
        backgroundColor: ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#6B7280'],
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
            label: (ctx) => ` ${ctx.label}: ${formatNumber(ctx.raw)} devices`
          }
        }
      },
      onClick: (evt, elements) => {
        if (elements && elements.length > 0) {
          const idx = elements[0].index;
          const selectedOs = labels[idx];
          activeEpSearch = selectedOs.replace(/\(.*\)/, '').trim();
          activeEpFilterLabel = `OS: ${selectedOs}`;
          const searchInput = document.getElementById('epSearchInput');
          if (searchInput) searchInput.value = activeEpSearch;
          updateActiveFilterBanner();
          currentEpPage = 1;
          loadEndpointsGrid();
        }
      }
    }
  });
}

function renderComplianceChart(compData) {
  const canvas = document.getElementById('epComplianceChart');
  if (!canvas) return;
  complianceChartInstance = destroyChartSafe(complianceChartInstance);

  const labels = Object.keys(compData);
  const values = Object.values(compData);

  const ctx = canvas.getContext('2d');
  complianceChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Devices',
        data: values,
        backgroundColor: labels.map(l => {
          const lower = l.toLowerCase();
          if (lower.includes('compliant') && !lower.includes('non')) return '#10B981';
          if (lower.includes('noncompliant')) return '#EF4444';
          if (lower.includes('config')) return '#3B82F6';
          return '#F59E0B';
        }),
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
            label: (ctx) => ` ${ctx.label}: ${formatNumber(ctx.raw)} devices`
          }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#9CA3AF', font: { size: 10 } } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#6B7280', font: { size: 10 } } }
      },
      onClick: (evt, elements) => {
        if (elements && elements.length > 0) {
          const idx = elements[0].index;
          const selectedStatus = labels[idx];
          activeEpStatus = selectedStatus;
          activeEpFilterLabel = `Compliance: ${selectedStatus}`;
          const statusSelect = document.getElementById('epFilterStatus');
          if (statusSelect) statusSelect.value = selectedStatus;
          updateActiveFilterBanner();
          currentEpPage = 1;
          loadEndpointsGrid();
        }
      }
    }
  });
}

function renderMfgChart(mfgData) {
  const canvas = document.getElementById('epMfgChart');
  if (!canvas) return;
  mfgChartInstance = destroyChartSafe(mfgChartInstance);

  const labels = Object.keys(mfgData);
  const values = Object.values(mfgData);

  const ctx = canvas.getContext('2d');
  mfgChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: values,
        backgroundColor: ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#6B7280'],
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
            label: (ctx) => ` ${ctx.label}: ${formatNumber(ctx.raw)} devices`
          }
        }
      },
      onClick: (evt, elements) => {
        if (elements && elements.length > 0) {
          const idx = elements[0].index;
          const selectedMfg = labels[idx];
          activeEpVendor = selectedMfg;
          activeEpFilterLabel = `Manufacturer: ${selectedMfg}`;
          const searchInput = document.getElementById('epSearchInput');
          if (searchInput) searchInput.value = '';
          updateActiveFilterBanner();
          currentEpPage = 1;
          loadEndpointsGrid();
        }
      }
    }
  });
}


async function loadEndpointsGrid() {
  const tbody = document.getElementById('epDeviceTableBody');
  const recordCountEl = document.getElementById('epRecordCount');
  const tableContainer = document.querySelector('#view-endpoints .grid-scroll');
  const paginationControls = document.getElementById('epPaginationControls');
  if (!tbody) return;

  try {
    const params = {
      page: currentEpPage,
      page_size: currentEpPageSize,
      ...(activeEpSearch ? { search: activeEpSearch } : {}),
      ...(activeEpStatus ? { status: activeEpStatus } : {}),
      ...(activeEpVendor ? { vendor: activeEpVendor } : {}),
    };

    const res = await itomApi.getIntuneDevices(params);
    const data = res.data || res;
    allFetchedDevices = data.items || [];

    // Correctly resolve total records from backend response
    const totalRecords = data.total !== undefined ? data.total : (data.pagination?.total_records || cachedTotalRecords);
    const totalPages = Math.max(1, Math.ceil(totalRecords / currentEpPageSize));

    currentEpPage = Math.min(currentEpPage, totalPages);
    const startRecord = totalRecords > 0 ? (currentEpPage - 1) * currentEpPageSize + 1 : 0;
    const endRecord = totalRecords > 0 ? Math.min(startRecord + allFetchedDevices.length - 1, totalRecords) : 0;

    if (recordCountEl) {
      recordCountEl.textContent = `Showing ${formatNumber(startRecord)}–${formatNumber(endRecord)} of ${formatNumber(totalRecords)} Managed Devices`;
    }

    if (!allFetchedDevices.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 32px; color: #6B7280;">No devices match the active search or filter criteria.</td></tr>`;
      if (paginationControls) paginationControls.innerHTML = '';
      return;
    }

    tbody.innerHTML = allFetchedDevices.map((dev, idx) => {
      const isCompliant = (dev.status || '').toLowerCase() === 'compliant';
      const statusClass = isCompliant ? 'healthy' : (dev.status || '').toLowerCase() === 'noncompliant' ? 'critical' : 'warning';

      return `
        <tr>
          <td><strong class="ci-name-link" data-ep-idx="${idx}" style="cursor: pointer; color: #60A5FA;" title="Open device details drawer">${escapeHtml(dev.name)}</strong></td>
          <td>${escapeHtml(dev.attributes?.user_principal_name || dev.attributes?.primary_user || 'Unavailable')}</td>
          <td>${escapeHtml(dev.operating_system || dev.ci_type || 'Unavailable')}</td>
          <td>${escapeHtml(dev.vendor || 'Unavailable')}</td>
          <td><span class="status-pill status-${statusClass}">${escapeHtml(dev.status || 'Unknown')}</span></td>
          <td class="font-mono">${escapeHtml(dev.serial_number || 'N/A')}</td>
        </tr>
      `;
    }).join('');

    tbody.querySelectorAll('.ci-name-link').forEach(link => {
      link.addEventListener('click', () => {
        const idx = parseInt(link.dataset.epIdx, 10);
        if (allFetchedDevices[idx]) {
          openCiDrawer(allFetchedDevices[idx]);
        }
      });
    });


    // Reset table scroll on page changes
    if (tableContainer) tableContainer.scrollTop = 0;

    // Render smart full-dataset pagination controls
    generatePaginationControls(paginationControls, currentEpPage, totalPages, (newPage) => {
      currentEpPage = newPage;
      loadEndpointsGrid();
    });

  } catch (err) {
    console.error('Failed to load endpoints grid:', err);
    if (recordCountEl) recordCountEl.textContent = 'Intune device count unavailable';
    if (paginationControls) paginationControls.innerHTML = '';
    tbody.innerHTML = `<tr><td colspan="6" class="inline-error">Unable to fetch endpoint devices. Upstream Graph API offline.</td></tr>`;
  }
}

function initEndpointsFilters() {
  if (endpointsFiltersInitialized) return;
  endpointsFiltersInitialized = true;

  const searchInput = document.getElementById('epSearchInput');
  const statusSelect = document.getElementById('epFilterStatus');
  const pageSizeSelect = document.getElementById('epPageSizeSelect');
  const resetBtn = document.getElementById('epResetFilters');
  const exportBtn = document.getElementById('epExportCsv');
  const clearFilterBtn = document.getElementById('epClearActiveFilterBtn');

  if (searchInput) {
    searchInput.addEventListener('input', debounce((e) => {
      activeEpSearch = e.target.value.trim();
      if (!activeEpSearch && activeEpFilterLabel.startsWith('Search:')) {
        activeEpFilterLabel = '';
      } else if (activeEpSearch) {
        activeEpFilterLabel = `Search: "${activeEpSearch}"`;
      }
      updateActiveFilterBanner();
      currentEpPage = 1;
      loadEndpointsGrid();
    }, 250));
  }

  if (statusSelect) {
    statusSelect.addEventListener('change', (e) => {
      activeEpStatus = e.target.value;
      if (activeEpStatus) {
        activeEpFilterLabel = `Status: ${activeEpStatus}`;
      } else {
        activeEpFilterLabel = '';
      }
      updateActiveFilterBanner();
      currentEpPage = 1;
      loadEndpointsGrid();
    });
  }

  if (pageSizeSelect) {
    pageSizeSelect.addEventListener('change', (e) => {
      const newSize = parseInt(e.target.value, 10);
      currentEpPage = calculateNewPageAnchor(currentEpPage, currentEpPageSize, newSize, 1000);
      currentEpPageSize = newSize;
      loadEndpointsGrid();
    });
  }

  const clearAllFilters = () => {
    if (searchInput) searchInput.value = '';
    if (statusSelect) statusSelect.value = '';
    activeEpSearch = '';
    activeEpStatus = '';
    activeEpVendor = '';
    activeEpFilterLabel = '';
    updateActiveFilterBanner();
    currentEpPage = 1;
    loadEndpointsGrid();
  };

  if (resetBtn) resetBtn.addEventListener('click', clearAllFilters);
  if (clearFilterBtn) clearFilterBtn.addEventListener('click', clearAllFilters);

  if (exportBtn) {
    exportBtn.addEventListener('click', async () => {
      const originalText = exportBtn.innerHTML;
      exportBtn.disabled = true;
      exportBtn.textContent = 'Preparing CSV…';
      try {
      const filters = {
        ...(activeEpSearch ? { search: activeEpSearch } : {}),
        ...(activeEpStatus ? { status: activeEpStatus } : {}),
        ...(activeEpVendor ? { vendor: activeEpVendor } : {}),
      };
      const exportDevices = await fetchAllFilteredRows(params => itomApi.getIntuneDevices(params), filters);
      if (!exportDevices.length) { window.alert('No devices match the active filters.'); return; }
      const headers = [
        { label: 'Device Name', key: 'name' },
        { label: 'Primary User', key: 'user' },
        { label: 'OS Version', key: 'os' },
        { label: 'Manufacturer', key: 'vendor' },
        { label: 'Compliance', key: 'status' },
        { label: 'Serial Number', key: 'serial_number' }
      ];
      const rows = exportDevices.map(d => ({
        name: d.name,
        user: d.attributes?.user_principal_name || d.attributes?.primary_user || 'Unavailable',
        os: d.operating_system || d.ci_type || 'Unavailable',
        vendor: d.vendor || 'Unavailable',
        status: d.status || 'Unknown',
        serial_number: d.serial_number || 'N/A'
      }));
      exportToCsv('Intune_Endpoints_Filtered', headers, rows);
      } catch (error) {
        console.error('Intune CSV export failed:', error);
        window.alert(`CSV export failed: ${error.message}`);
      } finally {
        exportBtn.disabled = false;
        exportBtn.innerHTML = originalText;
      }
    });
  }
}
