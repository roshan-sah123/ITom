/**
 * Module 3: Digital Workplace Experience (DEX) / Endpoints (Microsoft Intune Cloud Mirror)
 * 4 KPI cards, 5 visualizations, interactive chart slice filtering, true full pagination across 27,412 devices
 */
import { itomApi } from '../api.js';
import { formatNumber, formatPercent, escapeHtml, calculateNewPageAnchor, debounce, exportToCsv, destroyChartSafe, generatePaginationControls } from '../utils.js';
import { openCiDrawer } from './drawer.js';

let osChartInstance = null;
let complianceChartInstance = null;
let mfgChartInstance = null;

let currentEpPage = 1;
let currentEpPageSize = 25;
let activeEpSearch = '';
let activeEpStatus = '';
let activeEpFilterLabel = '';

let allFetchedDevices = [];
let cachedTotalRecords = 0;

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

function renderStorageMetrics(metrics) {
  const coverage = document.getElementById('epAging7Val');
  const median = document.getElementById('epAging30Val');
  const average = document.getElementById('epAgingStaleVal');

  if (coverage) coverage.textContent = percentageText(metrics.storage_coverage_pct);
  if (median) median.textContent = percentageText(metrics.median_device_storage_used_pct);
  if (average) average.textContent = percentageText(metrics.avg_storage_used_pct);
}

function renderEndpointsUnavailable() {
  const values = ['epTotalVal', 'epCompRateVal', 'epOsDiversityVal', 'epZeroTrustVal', 'epAging7Val', 'epAging30Val', 'epAgingStaleVal'];
  values.forEach((id) => {
    const element = document.getElementById(id);
    if (element) element.textContent = '—';
  });

  const totalSub = document.getElementById('epTotalSub');
  const compSub = document.getElementById('epCompRateSub');
  const recordCount = document.getElementById('epRecordCount');
  if (totalSub) totalSub.textContent = 'Intune data unavailable';
  if (compSub) compSub.textContent = 'No verified compliance result';
  if (recordCount) recordCount.textContent = 'Intune data unavailable';
}

export async function renderEndpoints() {
  await loadEndpointsKpisAndCharts();
  await loadEndpointsGrid();
  initEndpointsFilters();
}

async function loadEndpointsKpisAndCharts() {
  try {
    const summary = await itomApi.getIntuneSummary();
    const metrics = summary.metrics || {};
    const total = asNumber(metrics.total_managed_devices);
    const compliant = asNumber(metrics.compliant_devices);
    const compRate = asNumber(metrics.compliance_rate_pct);

    cachedTotalRecords = total ?? 0;

    const totalEl = document.getElementById('epTotalVal');
    const totalSub = document.getElementById('epTotalSub');
    const compEl = document.getElementById('epCompRateVal');
    const compSub = document.getElementById('epCompRateSub');
    const osDivEl = document.getElementById('epOsDiversityVal');
    const zeroTrustEl = document.getElementById('epZeroTrustVal');

    if (totalEl) totalEl.textContent = metricText(total);
    if (totalSub) totalSub.textContent = compliant === null ? 'Compliant count not reported' : `${formatNumber(compliant)} compliant devices`;
    if (compEl) compEl.textContent = percentageText(compRate);
    if (compSub) compSub.textContent = 'Authoritative Intune telemetry';
    if (osDivEl) osDivEl.textContent = Object.keys(summary.os_distribution || summary.os_breakdown || {}).join(' / ') || 'Not reported';
    if (zeroTrustEl) zeroTrustEl.textContent = percentageText(metrics.median_device_storage_used_pct);

    // 1. OS Distribution (with click filtering)
    renderOsChart(summary.os_distribution || summary.os_breakdown || {});

    // 2. Compliance Chart (with click filtering)
    renderComplianceChart(summary.compliance_breakdown || summary.status_breakdown || {});

    // 3. Manufacturer Chart (with click filtering)
    renderMfgChart(summary.vendor_distribution || summary.manufacturer_breakdown || {});

    // 4. Device storage analytics. The API does not supply device-aging buckets.
    renderStorageMetrics(metrics);

  } catch (err) {
    console.error('Failed to load endpoints summary:', err);
    renderEndpointsUnavailable();
  }
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
          activeEpSearch = selectedMfg;
          activeEpFilterLabel = `Manufacturer: ${selectedMfg}`;
          const searchInput = document.getElementById('epSearchInput');
          if (searchInput) searchInput.value = selectedMfg;
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
    };

    const res = await itomApi.getIntuneDevices(params);
    const data = res.data || res;
    allFetchedDevices = data.items || [];

    // Correctly resolve total records from backend response
    const totalRecords = asNumber(data.total) ?? asNumber(data.pagination?.total_records) ?? cachedTotalRecords;
    const totalPages = Math.max(1, Math.ceil(totalRecords / currentEpPageSize));

    currentEpPage = Math.min(currentEpPage, totalPages);
    const startRecord = totalRecords ? (currentEpPage - 1) * currentEpPageSize + 1 : 0;
    const endRecord = Math.min(startRecord + allFetchedDevices.length - 1, totalRecords);

    if (recordCountEl) {
      recordCountEl.textContent = `Showing ${formatNumber(startRecord)}–${formatNumber(endRecord)} of ${formatNumber(totalRecords)} Managed Devices`;
    }

    if (!allFetchedDevices.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 32px; color: #6B7280;">No devices match the active search or filter criteria.</td></tr>`;
      if (paginationControls) paginationControls.innerHTML = '';
      return;
    }

    tbody.innerHTML = allFetchedDevices.map(dev => {
      const isCompliant = (dev.status || '').toLowerCase() === 'compliant';
      const statusClass = isCompliant ? 'healthy' : (dev.status || '').toLowerCase() === 'noncompliant' ? 'critical' : 'warning';

      return `
        <tr>
          <td><strong>${escapeHtml(dev.name)}</strong></td>
          <td>${escapeHtml(dev.attributes?.user_principal_name || dev.attributes?.primary_user || '—')}</td>
          <td>${escapeHtml(dev.operating_system || dev.ci_type || '—')}</td>
          <td>${escapeHtml(dev.vendor || '—')}</td>
          <td><span class="status-pill status-${statusClass}">${escapeHtml(dev.status || 'Unknown')}</span></td>
          <td class="font-mono">${escapeHtml(dev.serial_number || '—')}</td>
          <td>
            <button class="btn-action btn-inspect-ep" data-id="${escapeHtml(dev.id || '')}" style="height: 28px; padding: 0 10px; font-size: 11px;">
              Inspect
            </button>
          </td>
        </tr>
      `;
    }).join('');

    tbody.querySelectorAll('.btn-inspect-ep').forEach(btn => {
      btn.addEventListener('click', () => {
        const found = allFetchedDevices.find(d => (d.id || '') === btn.dataset.id);
        if (found) openCiDrawer(found);
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
    tbody.innerHTML = `<tr><td colspan="7" class="inline-error">Unable to fetch endpoint devices. Upstream Graph API offline.</td></tr>`;
  }
}

function initEndpointsFilters() {
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
    activeEpFilterLabel = '';
    updateActiveFilterBanner();
    currentEpPage = 1;
    loadEndpointsGrid();
  };

  if (resetBtn) resetBtn.addEventListener('click', clearAllFilters);
  if (clearFilterBtn) clearFilterBtn.addEventListener('click', clearAllFilters);

  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      if (!allFetchedDevices.length) return;
      const headers = [
        { label: 'Device Name', key: 'name' },
        { label: 'Primary User', key: 'user' },
        { label: 'OS Version', key: 'os' },
        { label: 'Manufacturer', key: 'vendor' },
        { label: 'Compliance', key: 'status' },
        { label: 'Serial Number', key: 'serial_number' }
      ];
      const rows = allFetchedDevices.map(d => ({
        name: d.name,
        user: d.attributes?.user_principal_name || d.attributes?.primary_user || '—',
        os: d.operating_system || d.ci_type || '—',
        vendor: d.vendor || '—',
        status: d.status || 'Unknown',
        serial_number: d.serial_number || '—'
      }));
      exportToCsv(`Intune_Endpoints_Page_${currentEpPage}`, headers, rows);
    });
  }
}
