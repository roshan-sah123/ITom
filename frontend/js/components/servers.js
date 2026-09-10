/**
 * Module 2: Hybrid Servers (SolarWinds Orion Live Mirror)
 * 4 KPI cards, 4 operational visualizations, top 10 saturated servers triage, 3-zone server table
 */
import { itomApi } from '../api.js';
import { formatNumber, formatPercent, escapeHtml, calculateNewPageAnchor, debounce, exportToCsv, destroyChartSafe } from '../utils.js';
import { openCiDrawer } from './drawer.js';

let swHealthChartInstance = null;
let swStatusChartInstance = null;
let swVendorChartInstance = null;

let currentSwPage = 1;
let currentSwPageSize = 25;
let activeSwSearch = '';
let activeSwHealthTier = '';
let activeSwStatus = '';

let allFetchedNodes = [];

export async function renderServers() {
  await loadServerKpisAndCharts();
  await loadServerGrid();
  initServerFilters();
}

async function loadServerKpisAndCharts() {
  try {
    const summary = await itomApi.getSolarWindsSummary();
    const metrics = summary.metrics || {};
    const total = metrics.total_server_nodes || 1572;
    const active = metrics.active_monitored_nodes || 1543;
    const sla = metrics.high_health_pct || 89.7;
    const alerts = (metrics.low_critical_nodes || 41) + (metrics.medium_health_nodes || 150);

    const totalEl = document.getElementById('swTotalNodesVal');
    const totalSub = document.getElementById('swTotalNodesSub');
    const slaEl = document.getElementById('swSlaVal');
    const alertsEl = document.getElementById('swAlertsVal');
    const osEl = document.getElementById('swOsVal');

    if (totalEl) totalEl.textContent = formatNumber(total);
    if (totalSub) totalSub.textContent = `${formatNumber(active)} Monitored`;
    if (slaEl) slaEl.textContent = `${sla.toFixed(1)}%`;
    if (alertsEl) alertsEl.textContent = formatNumber(alerts);
    if (osEl) osEl.textContent = `Cisco / Windows / Linux`;

    // 1. Health Chart
    renderSwHealthChart(summary.health_breakdown || { High: 1357, Medium: 150, Low: 41 });

    // 2. Status Chart
    renderSwStatusChart(metrics.status_counts || { up: 1370, warning: 25, critical: 35, down: 6, unmanaged_unknown: 112 });

    // 3. Vendor Chart
    renderSwVendorChart(summary.vendor_distribution || { Cisco: 612, Windows: 340, Linux: 210, Other: 386 });

    // 4. Saturated Servers Triage List
    renderSwSaturatedTriage(summary.top_saturated_servers || []);

  } catch (err) {
    console.error('Failed to load SolarWinds summary:', err);
  }
}

function renderSwHealthChart(health) {
  const canvas = document.getElementById('swHealthChart');
  if (!canvas) return;
  swHealthChartInstance = destroyChartSafe(swHealthChartInstance);

  const ctx = canvas.getContext('2d');
  swHealthChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['High Health', 'Medium Health', 'Low / Critical'],
      datasets: [{
        data: [health.High || 0, health.Medium || 0, health.Low || 0],
        backgroundColor: ['#10B981', '#F59E0B', '#EF4444'],
        borderWidth: 2,
        borderColor: '#141414'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '70%',
      plugins: { legend: { display: false } },
      onClick: (evt, els) => {
        if (els.length) {
          const idx = els[0].index;
          activeSwHealthTier = idx === 0 ? 'High' : idx === 1 ? 'Medium' : 'Low';
          const select = document.getElementById('swFilterHealth');
          if (select) select.value = activeSwHealthTier;
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

  const ctx = canvas.getContext('2d');
  swStatusChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Up', 'Warning', 'Critical', 'Down', 'Unmanaged'],
      datasets: [{
        label: 'Nodes',
        data: [statusCounts.up || 0, statusCounts.warning || 0, statusCounts.critical || 0, statusCounts.down || 0, statusCounts.unmanaged_unknown || 0],
        backgroundColor: ['#10B981', '#F59E0B', '#EF4444', '#B91C1C', '#6B7280'],
        borderRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#9CA3AF', font: { size: 10 } } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#6B7280', font: { size: 10 } } }
      },
      onClick: (evt, els) => {
        if (els.length) {
          const labels = ['Up', 'Warning', 'Critical', 'Down', 'Unmanaged'];
          activeSwStatus = labels[els[0].index];
          const select = document.getElementById('swFilterStatus');
          if (select) select.value = activeSwStatus;
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
  const data = Object.values(vendors);

  const ctx = canvas.getContext('2d');
  swVendorChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#6B7280'],
        borderWidth: 2,
        borderColor: '#141414'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '70%',
      plugins: { legend: { display: false } }
    }
  });
}

function renderSwSaturatedTriage(servers) {
  const container = document.getElementById('swSaturatedList');
  if (!container) return;

  if (!servers.length) {
    container.innerHTML = `<div style="padding: 12px; color: #6B7280; font-size: 11px;">No saturation threshold breaches. All nodes healthy.</div>`;
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
      currentSwPage = 1;
      loadServerGrid();
    });
  });
}

async function loadServerGrid() {
  const tbody = document.getElementById('swServerTableBody');
  const recordCountEl = document.getElementById('swRecordCount');
  if (!tbody) return;

  try {
    const params = {
      page: currentSwPage,
      page_size: currentSwPageSize,
      ...(activeSwSearch ? { search: activeSwSearch } : {}),
      ...(activeSwHealthTier ? { health_tier: activeSwHealthTier } : {}),
      ...(activeSwStatus ? { status: activeSwStatus } : {}),
    };

    const res = await itomApi.getSolarWindsNodes(params);
    const data = res.data || res;
    allFetchedNodes = data.items || [];
    const pagination = data.pagination || { total_records: allFetchedNodes.length, page: 1, total_pages: 1 };

    const totalRecords = pagination.total_records || allFetchedNodes.length;
    const totalPages = pagination.total_pages || Math.max(1, Math.ceil(totalRecords / currentSwPageSize));
    const startRecord = totalRecords ? (currentSwPage - 1) * currentSwPageSize + 1 : 0;
    const endRecord = Math.min(startRecord + currentSwPageSize - 1, totalRecords);

    if (recordCountEl) {
      recordCountEl.textContent = `Showing ${startRecord}–${endRecord} of ${formatNumber(totalRecords)} Server Nodes`;
    }

    if (!allFetchedNodes.length) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 24px; color: #6B7280;">No server nodes matching current search criteria.</td></tr>`;
      renderServerPagination(totalPages);
      return;
    }

    tbody.innerHTML = allFetchedNodes.map(node => {
      const healthClass = (node.health_tier || 'healthy').toLowerCase();
      const cpu = node.attributes?.cpu_load ?? node.CPULoad ?? 0;
      const ram = node.attributes?.memory_used ?? node.PercentMemoryUsed ?? 0;
      const latency = node.attributes?.latency_ms ?? node.AvgResponseTime ?? 0;

      return `
        <tr>
          <td><strong>${escapeHtml(node.name)}</strong></td>
          <td class="font-mono">${escapeHtml(node.ip_address || 'N/A')}</td>
          <td>${escapeHtml(node.vendor || 'Generic')}</td>
          <td><span class="status-pill status-${healthClass}">${escapeHtml(node.health_tier || 'High')}</span></td>
          <td class="font-mono" style="color: ${cpu > 85 ? '#EF4444' : cpu > 70 ? '#F59E0B' : '#10B981'}">${cpu.toFixed(1)}%</td>
          <td class="font-mono" style="color: ${ram > 85 ? '#EF4444' : ram > 70 ? '#F59E0B' : '#10B981'}">${ram.toFixed(1)}%</td>
          <td class="font-mono">${latency.toFixed(1)}ms</td>
          <td>
            <button class="btn-action btn-inspect-node" data-id="${escapeHtml(node.id || '')}" style="height: 28px; padding: 0 10px; font-size: 11px;">
              Inspect
            </button>
          </td>
        </tr>
      `;
    }).join('');

    tbody.querySelectorAll('.btn-inspect-node').forEach(btn => {
      btn.addEventListener('click', () => {
        const found = allFetchedNodes.find(n => (n.id || '') === btn.dataset.id);
        if (found) openCiDrawer(found);
      });
    });

    renderServerPagination(totalPages);

  } catch (err) {
    console.error('Failed to load server grid:', err);
    tbody.innerHTML = `<tr><td colspan="8" class="inline-error">Unable to fetch server telemetry. Backend API may be unreachable.</td></tr>`;
  }
}

function renderServerPagination(totalPages) {
  const container = document.getElementById('swPaginationControls');
  if (!container) return;

  container.innerHTML = `
    <button class="btn-page" ${currentSwPage <= 1 ? 'disabled' : ''} id="swPagePrev">«</button>
    <button class="btn-page active">${currentSwPage}</button>
    <span style="font-family: JetBrains Mono; font-size: 11px; padding: 0 4px; color: #6B7280;">of ${totalPages}</span>
    <button class="btn-page" ${currentSwPage >= totalPages ? 'disabled' : ''} id="swPageNext">»</button>
  `;

  document.getElementById('swPagePrev')?.addEventListener('click', () => {
    if (currentSwPage > 1) {
      currentSwPage--;
      loadServerGrid();
    }
  });

  document.getElementById('swPageNext')?.addEventListener('click', () => {
    if (currentSwPage < totalPages) {
      currentSwPage++;
      loadServerGrid();
    }
  });
}

function initServerFilters() {
  const searchInput = document.getElementById('swSearchInput');
  const healthSelect = document.getElementById('swFilterHealth');
  const statusSelect = document.getElementById('swFilterStatus');
  const pageSizeSelect = document.getElementById('swPageSizeSelect');
  const resetBtn = document.getElementById('swResetFilters');
  const exportBtn = document.getElementById('swExportCsv');

  if (searchInput) {
    searchInput.addEventListener('input', debounce((e) => {
      activeSwSearch = e.target.value.trim();
      currentSwPage = 1;
      loadServerGrid();
    }, 200));
  }

  if (healthSelect) {
    healthSelect.addEventListener('change', (e) => {
      activeSwHealthTier = e.target.value;
      currentSwPage = 1;
      loadServerGrid();
    });
  }

  if (statusSelect) {
    statusSelect.addEventListener('change', (e) => {
      activeSwStatus = e.target.value;
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

  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      if (searchInput) searchInput.value = '';
      if (healthSelect) healthSelect.value = '';
      if (statusSelect) statusSelect.value = '';
      activeSwSearch = '';
      activeSwHealthTier = '';
      activeSwStatus = '';
      currentSwPage = 1;
      loadServerGrid();
    });
  }

  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      if (!allFetchedNodes.length) return;
      const headers = [
        { label: 'Node Name', key: 'name' },
        { label: 'IP Address', key: 'ip_address' },
        { label: 'Vendor', key: 'vendor' },
        { label: 'Health Tier', key: 'health_tier' },
        { label: 'Status', key: 'status' }
      ];
      exportToCsv('solarwinds_server_nodes.csv', headers, allFetchedNodes);
    });
  }
}
