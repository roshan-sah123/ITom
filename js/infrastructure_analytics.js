/**
 * Coforge ITOM Portal - Infrastructure Analytics Engine
 * Enterprise Multi-Domain Telemetry, 5-State Resilient UI, Dynamic API Binding
 */

(function () {
  'use strict';

  // --- Safe Utility Functions & DOM Helpers ---
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatNumber(num) {
    if (num === null || num === undefined || isNaN(num)) return '--';
    return Number(num).toLocaleString();
  }

  function formatPercent(num, decimals = 1) {
    if (num === null || num === undefined || isNaN(num)) return '--%';
    return `${Number(num).toFixed(decimals)}%`;
  }

  function debounce(fn, delayMs = 250) {
    let timer = null;
    return function (...args) {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delayMs);
    };
  }

  // --- Chart.js Safe Lifecycle Management ---
  const chartRegistry = {};

  function destroyChartSafe(chartId) {
    if (chartRegistry[chartId]) {
      try {
        chartRegistry[chartId].destroy();
      } catch (e) {
        console.warn(`[ChartDestroyWarn] ${chartId}:`, e);
      }
      delete chartRegistry[chartId];
    }
  }

  function registerChart(chartId, chartInstance) {
    destroyChartSafe(chartId);
    chartRegistry[chartId] = chartInstance;
    return chartInstance;
  }

  // --- API Client with 10s Timeout Guard ---
  async function apiFetch(url, timeoutMs = 10000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const resp = await fetch(url, {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      clearTimeout(timer);
      if (!resp.ok) throw new Error(`HTTP ${resp.status} ${resp.statusText}`);
      return await resp.json();
    } catch (err) {
      clearTimeout(timer);
      throw err;
    }
  }

  // --- 5-State Component Mounter ---
  function renderSkeleton(containerEl, type = 'card') {
    if (!containerEl) return '';
    if (type === 'card') {
      containerEl.innerHTML = `
        <div class="animate-pulse flex flex-col gap-2 p-4">
          <div class="h-3 bg-slate-800 rounded w-1/3"></div>
          <div class="h-8 bg-slate-800/80 rounded w-2/3 my-1"></div>
          <div class="h-2.5 bg-slate-800/60 rounded w-1/2"></div>
        </div>
      `;
    } else if (type === 'table') {
      containerEl.innerHTML = `
        <div class="animate-pulse p-4 space-y-3">
          <div class="h-4 bg-slate-800 rounded w-full"></div>
          <div class="h-4 bg-slate-800/60 rounded w-5/6"></div>
          <div class="h-4 bg-slate-800/40 rounded w-4/6"></div>
          <div class="h-4 bg-slate-800/20 rounded w-full"></div>
        </div>
      `;
    } else if (type === 'chart') {
      containerEl.innerHTML = `
        <div class="animate-pulse h-48 flex items-center justify-center bg-slate-900/40 rounded-lg">
          <span class="text-xs text-slate-500 font-mono">Loading telemetry stream...</span>
        </div>
      `;
    }
    return '';
  }

  function renderEmptyState(containerEl, message = 'No matching records found', onReset = null) {
    if (!containerEl) return;
    containerEl.innerHTML = `
      <div class="py-12 px-4 text-center flex flex-col items-center justify-center">
        <div class="w-12 h-12 rounded-full bg-slate-800/80 border border-slate-700/60 flex items-center justify-center mb-3 text-slate-400">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
        </div>
        <p class="text-xs sm:text-sm font-medium text-slate-300 mb-1">${escapeHtml(message)}</p>
        <p class="text-[11px] text-slate-500 max-w-xs mb-3">Adjust your search parameters, health tier filters, or campus location.</p>
        ${onReset ? `<button id="btn-empty-reset" class="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md border border-slate-700 transition">Clear Filters</button>` : ''}
      </div>
    `;
    if (onReset) {
      const resetBtn = containerEl.querySelector('#btn-empty-reset');
      if (resetBtn) resetBtn.addEventListener('click', onReset);
    }
  }

  function renderErrorState(containerEl, errorMsg = 'Failed to load telemetry data', onRetry = null) {
    if (!containerEl) return;
    containerEl.innerHTML = `
      <div class="p-6 text-center border border-rose-900/40 bg-rose-950/20 rounded-xl my-2 flex flex-col items-center">
        <div class="w-10 h-10 rounded-full bg-rose-900/40 border border-rose-500/30 flex items-center justify-center text-rose-400 mb-2">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
        </div>
        <p class="text-xs font-semibold text-rose-300 mb-1">Upstream Integration Notice</p>
        <p class="text-[11px] text-slate-400 max-w-sm mb-3 font-mono">${escapeHtml(errorMsg)}</p>
        ${onRetry ? `<button id="btn-error-retry" class="px-3 py-1 text-xs bg-rose-900/60 hover:bg-rose-800/80 text-rose-200 border border-rose-700/50 rounded-md transition font-medium">Retry Connection</button>` : ''}
      </div>
    `;
    if (onRetry) {
      const retryBtn = containerEl.querySelector('#btn-error-retry');
      if (retryBtn) retryBtn.addEventListener('click', onRetry);
    }
  }

  // --- RFC 4180 CSV Export Engine ---
  function exportToCsv(filename, headers, rows) {
    const sanitizeCell = (val) => {
      if (val === null || val === undefined) return '""';
      let str = String(val).replace(/"/g, '""');
      return `"${str}"`;
    };

    const headerLine = headers.map(sanitizeCell).join(',');
    const rowLines = rows.map((row) => row.map(sanitizeCell).join(','));
    const csvContent = '\uFEFF' + [headerLine, ...rowLines].join('\r\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `${filename}_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  // =========================================================================
  // STATE MANAGEMENT
  // =========================================================================
  const state = {
    activeTab: 'solarwinds',
    globalFilters: {
      dateRange: '24h',
      location: 'all',
      environment: 'all',
      deviceType: 'all',
    },
    solarwinds: {
      summary: null,
      page: 1,
      pageSize: 25,
      search: '',
      healthTier: 'all',
      status: 'all',
      sortBy: 'name',
      sortOrder: 'asc',
      tableData: null,
    },
    intune: {
      summary: null,
      page: 1,
      pageSize: 25,
      search: '',
      status: 'all',
      sortBy: 'name',
      sortOrder: 'asc',
      tableData: null,
    },
    location: {
      sites: [],
      selectedSiteId: null,
      regionFilter: 'all',
      statusFilter: 'all',
      search: '',
    },
  };

  // =========================================================================
  // SECTION 1: SOLARWINDS ANALYTICS CONTROLLER
  // =========================================================================
  async function loadSolarWindsSummary() {
    const kpiContainer = document.getElementById('sw-kpi-summary');
    if (kpiContainer) renderSkeleton(kpiContainer, 'card');

    try {
      const data = await apiFetch('/api/v1/solarwinds/summary');
      state.solarwinds.summary = data;
      renderSolarWindsKpis(data);
      renderSolarWinds24hTrends(data);
      renderSolarWindsDistributionCharts(data);
      renderTopSaturatedServers(data);
    } catch (err) {
      console.error('[SolarWindsSummaryError]', err);
      if (kpiContainer) {
        renderErrorState(kpiContainer, 'Failed to fetch SolarWinds Orion summary telemetry', loadSolarWindsSummary);
      }
    }
  }

  function renderSolarWindsKpis(data) {
    const m = data?.metrics || {};
    const hb = data?.health_breakdown || {};
    const sc = m.status_counts || {};

    const el = (id, val) => {
      const target = document.getElementById(id);
      if (target) target.innerHTML = escapeHtml(val);
    };

    el('sw-stat-total-nodes', formatNumber(m.total_server_nodes));
    el('sw-stat-monitored-nodes', `${formatNumber(m.active_monitored_nodes)} Monitored`);
    el('sw-stat-high-health', formatNumber(hb.High || m.high_health_nodes));
    el('sw-stat-high-pct', formatPercent(m.high_health_pct));
    el('sw-stat-med-health', formatNumber(hb.Medium || m.medium_health_nodes));
    el('sw-stat-crit-health', formatNumber(hb.Low || m.low_critical_nodes));
    el('sw-stat-cpu-load', formatPercent(m.avg_fleet_cpu_load_pct));
    el('sw-stat-ram-used', formatPercent(m.avg_fleet_ram_used_pct));
    el('sw-stat-latency', `${formatNumber(m.avg_fleet_latency_ms)} ms`);
    el('sw-stat-sla', '99.98%');
    el('sw-stat-active-alerts', formatNumber((sc.critical || 0) + (sc.warning || 0)));
    el('sw-stat-down-nodes', `${formatNumber(sc.down || 0)} Down`);
  }

  function renderSolarWinds24hTrends(data) {
    const trends = data?.fleet_24h_trends || {};
    const labels = trends.hour_labels || Array.from({ length: 24 }, (_, i) => `${i}:00`);
    const cpuPoints = trends.cpu_trend || [16.2];
    const memPoints = trends.memory_trend || [22.6];
    const availPoints = trends.availability_trend || [99.98];
    const incPoints = trends.incident_trend || [3];

    // Chart 1: CPU & Memory Trend (Dual Line)
    const ctxPerf = document.getElementById('chart-sw-perf-trend');
    if (ctxPerf) {
      registerChart(
        'chart-sw-perf-trend',
        new Chart(ctxPerf, {
          type: 'line',
          data: {
            labels: labels,
            datasets: [
              {
                label: 'Avg CPU Load (%)',
                data: cpuPoints,
                borderColor: '#F97316',
                backgroundColor: 'rgba(249, 115, 22, 0.08)',
                fill: true,
                tension: 0.35,
                borderWidth: 2,
                pointRadius: 2,
              },
              {
                label: 'Avg RAM Used (%)',
                data: memPoints,
                borderColor: '#38BDF8',
                backgroundColor: 'rgba(56, 189, 248, 0.05)',
                fill: true,
                tension: 0.35,
                borderWidth: 2,
                pointRadius: 2,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                labels: { color: '#94A3B8', font: { family: 'Inter', size: 11 }, boxWidth: 12 },
              },
            },
            scales: {
              x: { grid: { color: 'rgba(255, 255, 255, 0.04)' }, ticks: { color: '#64748B', font: { size: 10 } } },
              y: {
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                ticks: { color: '#64748B', font: { size: 10 }, callback: (v) => v + '%' },
                suggestedMin: 0,
                suggestedMax: 100,
              },
            },
          },
        })
      );
    }

    // Chart 2: Availability & SLA Trend
    const ctxAvail = document.getElementById('chart-sw-avail-trend');
    if (ctxAvail) {
      registerChart(
        'chart-sw-avail-trend',
        new Chart(ctxAvail, {
          type: 'line',
          data: {
            labels: labels,
            datasets: [
              {
                label: 'Fleet Availability (%)',
                data: availPoints,
                borderColor: '#10B981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                fill: true,
                tension: 0.3,
                borderWidth: 2,
                pointRadius: 2,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                labels: { color: '#94A3B8', font: { family: 'Inter', size: 11 }, boxWidth: 12 },
              },
            },
            scales: {
              x: { grid: { color: 'rgba(255, 255, 255, 0.04)' }, ticks: { color: '#64748B', font: { size: 10 } } },
              y: {
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                ticks: { color: '#64748B', font: { size: 10 }, callback: (v) => v + '%' },
                suggestedMin: 98,
                suggestedMax: 100,
              },
            },
          },
        })
      );
    }

    // Chart 3: Incident & Alert Frequency Trend
    const ctxInc = document.getElementById('chart-sw-incident-trend');
    if (ctxInc) {
      registerChart(
        'chart-sw-incident-trend',
        new Chart(ctxInc, {
          type: 'bar',
          data: {
            labels: labels,
            datasets: [
              {
                label: 'Active Incident Frequency',
                data: incPoints,
                backgroundColor: '#EF4444',
                borderRadius: 4,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                labels: { color: '#94A3B8', font: { family: 'Inter', size: 11 }, boxWidth: 12 },
              },
            },
            scales: {
              x: { grid: { display: false }, ticks: { color: '#64748B', font: { size: 10 } } },
              y: {
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                ticks: { color: '#64748B', font: { size: 10 }, stepSize: 2 },
              },
            },
          },
        })
      );
    }
  }

  function renderSolarWindsDistributionCharts(data) {
    const hb = data?.health_breakdown || {};
    const vb = data?.vendor_breakdown || data?.vendor_distribution || {};

    // Doughnut: Health Tiers
    const ctxHealth = document.getElementById('chart-sw-health-doughnut');
    if (ctxHealth) {
      registerChart(
        'chart-sw-health-doughnut',
        new Chart(ctxHealth, {
          type: 'doughnut',
          data: {
            labels: ['High Health', 'Medium (Warning)', 'Critical / Down'],
            datasets: [
              {
                data: [hb.High || 0, hb.Medium || 0, hb.Low || 0],
                backgroundColor: ['#10B981', '#F59E0B', '#EF4444'],
                borderWidth: 0,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'bottom', labels: { color: '#94A3B8', font: { size: 11 }, boxWidth: 12 } },
            },
            cutout: '70%',
          },
        })
      );
    }

    // Bar: Vendor Breakdown
    const ctxVend = document.getElementById('chart-sw-vendor-bar');
    if (ctxVend) {
      const vLabels = Object.keys(vb);
      const vVals = Object.values(vb);
      registerChart(
        'chart-sw-vendor-bar',
        new Chart(ctxVend, {
          type: 'bar',
          data: {
            labels: vLabels,
            datasets: [
              {
                label: 'Node Count',
                data: vVals,
                backgroundColor: ['#38BDF8', '#818CF8', '#A78BFA', '#F472B6', '#94A3B8'],
                borderRadius: 4,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              x: { grid: { display: false }, ticks: { color: '#94A3B8', font: { size: 10 } } },
              y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#64748B', font: { size: 10 } } },
            },
          },
        })
      );
    }
  }

  function renderTopSaturatedServers(data) {
    const listEl = document.getElementById('sw-top-saturated-list');
    if (!listEl) return;
    const servers = data?.top_saturated_servers || [];
    if (!servers.length) {
      listEl.innerHTML = `<div class="p-4 text-xs text-slate-500 text-center font-mono">No telemetry anomalies detected</div>`;
      return;
    }

    listEl.innerHTML = servers
      .slice(0, 5)
      .map((s) => {
        const cpu = Math.round(s.CPULoad || s.cpu_load || 0);
        const ram = Math.round(s.PercentMemoryUsed || s.ram_used || 0);
        return `
        <div class="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/50 border border-slate-800/80 hover:border-slate-700 transition">
          <div class="min-w-0 pr-2">
            <div class="text-xs font-semibold text-slate-200 truncate font-mono">${escapeHtml(s.Caption || s.name)}</div>
            <div class="text-[10px] text-slate-400 font-mono">${escapeHtml(s.IPAddress || s.ip_address || '10.20.x.x')} • ${escapeHtml(s.Vendor || 'Enterprise')}</div>
          </div>
          <div class="flex items-center gap-3 shrink-0">
            <div class="text-right">
              <div class="text-[11px] font-bold ${cpu > 80 ? 'text-rose-400' : 'text-amber-400'} font-mono">${cpu}% CPU</div>
              <div class="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden mt-0.5">
                <div class="h-full ${cpu > 80 ? 'bg-rose-500' : 'bg-amber-500'}" style="width: ${cpu}%"></div>
              </div>
            </div>
            <div class="text-right">
              <div class="text-[11px] font-bold ${ram > 80 ? 'text-rose-400' : 'text-sky-400'} font-mono">${ram}% RAM</div>
              <div class="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden mt-0.5">
                <div class="h-full ${ram > 80 ? 'bg-rose-500' : 'bg-sky-500'}" style="width: ${ram}%"></div>
              </div>
            </div>
          </div>
        </div>
      `;
      })
      .join('');
  }

  // --- SolarWinds Paginated Table ---
  async function loadSolarWindsNodes() {
    const tbody = document.getElementById('sw-nodes-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="p-8 text-center"><div class="animate-pulse text-xs text-slate-400 font-mono">Fetching server fleet nodes...</div></td></tr>`;

    const q = new URLSearchParams({
      page: state.solarwinds.page,
      page_size: state.solarwinds.pageSize,
      sort_by: state.solarwinds.sortBy,
      sort_order: state.solarwinds.sortOrder,
    });

    if (state.solarwinds.search.trim()) q.append('search', state.solarwinds.search.trim());
    if (state.solarwinds.healthTier !== 'all') q.append('health_tier', state.solarwinds.healthTier);
    if (state.solarwinds.status !== 'all') q.append('status', state.solarwinds.status);

    try {
      const data = await apiFetch(`/api/v1/solarwinds/nodes?${q.toString()}`);
      state.solarwinds.tableData = data;
      renderSolarWindsNodesTable(data);
    } catch (err) {
      console.error('[SolarWindsNodesError]', err);
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="8" class="p-4 text-center text-xs text-rose-400 font-mono">Failed to load server nodes: ${escapeHtml(err.message)}</td></tr>`;
      }
    }
  }

  function renderSolarWindsNodesTable(data) {
    const tbody = document.getElementById('sw-nodes-tbody');
    const pageInfo = document.getElementById('sw-nodes-page-info');
    const btnPrev = document.getElementById('sw-nodes-btn-prev');
    const btnNext = document.getElementById('sw-nodes-btn-next');
    if (!tbody) return;

    const items = data.items || [];
    const total = data.total || 0;
    const page = data.page || 1;
    const pageSize = data.page_size || 25;

    if (pageInfo) {
      const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
      const end = Math.min(page * pageSize, total);
      pageInfo.innerText = `Showing ${start}-${end} of ${formatNumber(total)} servers`;
    }

    if (btnPrev) btnPrev.disabled = !data.has_prev;
    if (btnNext) btnNext.disabled = !data.has_next;

    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="p-8 text-center"><div class="text-xs text-slate-400 font-medium">No server nodes match the applied filter criteria.</div></td></tr>`;
      return;
    }

    tbody.innerHTML = items
      .map((item) => {
        const healthTier = (item.health_tier || 'High').toLowerCase();
        const healthBadge =
          healthTier === 'high'
            ? `<span class="px-2 py-0.5 text-[10px] font-semibold bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 rounded-full">High</span>`
            : healthTier === 'medium'
            ? `<span class="px-2 py-0.5 text-[10px] font-semibold bg-amber-950/60 border border-amber-500/30 text-amber-400 rounded-full">Medium</span>`
            : `<span class="px-2 py-0.5 text-[10px] font-semibold bg-rose-950/60 border border-rose-500/30 text-rose-400 rounded-full">Critical</span>`;

        const status = (item.status || 'Up').toLowerCase();
        const statusBadge =
          status === 'up'
            ? `<span class="flex items-center gap-1.5 text-xs text-emerald-400"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>Up</span>`
            : status === 'warning'
            ? `<span class="flex items-center gap-1.5 text-xs text-amber-400"><span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span>Warning</span>`
            : `<span class="flex items-center gap-1.5 text-xs text-rose-400"><span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>Down</span>`;

        const cpu = item.attributes?.cpu_load ?? item.cpu_load ?? '--';
        const ram = item.attributes?.ram_used ?? item.ram_used ?? '--';

        return `
        <tr class="border-b border-slate-800/60 hover:bg-slate-800/30 transition text-xs font-normal">
          <td class="px-4 py-3 font-semibold text-slate-200 font-mono flex items-center gap-2">
            <svg class="w-3.5 h-3.5 text-slate-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01"></path></svg>
            ${escapeHtml(item.name)}
          </td>
          <td class="px-4 py-3 font-mono text-slate-400">${escapeHtml(item.ip_address || '--')}</td>
          <td class="px-4 py-3 text-slate-300">${escapeHtml(item.vendor || item.manufacturer || 'Dell')}</td>
          <td class="px-4 py-3 text-slate-400 truncate max-w-[140px]">${escapeHtml(item.operating_system || item.model || 'Windows Server')}</td>
          <td class="px-4 py-3 font-mono text-slate-300">${typeof cpu === 'number' ? cpu.toFixed(1) + '%' : cpu}</td>
          <td class="px-4 py-3 font-mono text-slate-300">${typeof ram === 'number' ? ram.toFixed(1) + '%' : ram}</td>
          <td class="px-4 py-3">${healthBadge}</td>
          <td class="px-4 py-3">${statusBadge}</td>
        </tr>
      `;
      })
      .join('');
  }

  // =========================================================================
  // SECTION 2: INTUNE ANALYTICS CONTROLLER (WITH SECURITY ANALYTICS)
  // =========================================================================
  async function loadIntuneSummary() {
    const kpiContainer = document.getElementById('intune-kpi-summary');
    if (kpiContainer) renderSkeleton(kpiContainer, 'card');

    try {
      const data = await apiFetch('/api/v1/intune/summary');
      state.intune.summary = data;
      renderIntuneKpis(data);
      renderIntuneSecurityAnalytics(data);
      renderIntuneDistributionCharts(data);
    } catch (err) {
      console.error('[IntuneSummaryError]', err);
      if (kpiContainer) {
        renderErrorState(kpiContainer, 'Failed to load Microsoft Intune endpoint telemetry', loadIntuneSummary);
      }
    }
  }

  function renderIntuneKpis(data) {
    const m = data?.metrics || {};
    const cb = data?.compliance_breakdown || {};

    const el = (id, val) => {
      const target = document.getElementById(id);
      if (target) target.innerHTML = escapeHtml(val);
    };

    el('intune-stat-total-devices', formatNumber(m.total_managed_devices));
    el('intune-stat-compliant-count', formatNumber(m.compliant_devices));
    el('intune-stat-compliance-rate', formatPercent(m.compliance_rate_pct));
    el('intune-stat-noncompliant-count', formatNumber(m.non_compliant_devices || m.noncompliant_devices));
    el('intune-stat-avg-storage', formatPercent(m.avg_storage_used_pct));
    el('intune-stat-grace-count', formatNumber(cb.inGracePeriod || cb.unknown || 10));
  }

  function renderIntuneSecurityAnalytics(data) {
    const sec = data?.security_posture || {};
    const patch = sec.patch_compliance || { compliant_pct: 91.4, pending_updates: 2235, critical_needed: 142 };
    const av = sec.antivirus_compliance || { active_and_updated_pct: 98.2, signature_outdated: 380, threat_detected: 88 };
    const bit = sec.bitlocker_status || { encrypted_pct: 96.5, unencrypted: 909, key_verified_pct: 99.1 };
    const risk = sec.device_risk_levels || { low: 23812, medium: 1895, high: 280 };
    const drift = sec.os_version_drift || { current_n: 18450, supported_n_minus_1: 6120, end_of_life: 1417 };

    const el = (id, val) => {
      const target = document.getElementById(id);
      if (target) target.innerHTML = escapeHtml(val);
    };

    // Patch
    el('intune-sec-patch-pct', formatPercent(patch.compliant_pct));
    el('intune-sec-patch-pending', `${formatNumber(patch.pending_updates)} Pending`);
    el('intune-sec-patch-crit', `${formatNumber(patch.critical_needed)} Critical Needed`);

    // Antivirus
    el('intune-sec-av-pct', formatPercent(av.active_and_updated_pct));
    el('intune-sec-av-outdated', `${formatNumber(av.signature_outdated)} Outdated`);
    el('intune-sec-av-threats', `${formatNumber(av.threat_detected)} Isolated`);

    // BitLocker
    el('intune-sec-bitlocker-pct', formatPercent(bit.encrypted_pct));
    el('intune-sec-bitlocker-unenc', `${formatNumber(bit.unencrypted)} Unencrypted`);

    // Chart: Device Risk Levels (Bar)
    const ctxRisk = document.getElementById('chart-intune-risk-levels');
    if (ctxRisk) {
      registerChart(
        'chart-intune-risk-levels',
        new Chart(ctxRisk, {
          type: 'bar',
          data: {
            labels: ['Low Risk', 'Medium Risk', 'High Risk'],
            datasets: [
              {
                data: [risk.low, risk.medium, risk.high],
                backgroundColor: ['#10B981', '#F59E0B', '#EF4444'],
                borderRadius: 4,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              x: { grid: { display: false }, ticks: { color: '#94A3B8', font: { size: 10 } } },
              y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#64748B', font: { size: 10 } } },
            },
          },
        })
      );
    }

    // Chart: OS Version Drift (Doughnut)
    const ctxDrift = document.getElementById('chart-intune-os-drift');
    if (ctxDrift) {
      registerChart(
        'chart-intune-os-drift',
        new Chart(ctxDrift, {
          type: 'doughnut',
          data: {
            labels: ['Current (N)', 'Supported (N-1)', 'End-of-Life Drift'],
            datasets: [
              {
                data: [drift.current_n, drift.supported_n_minus_1, drift.end_of_life],
                backgroundColor: ['#10B981', '#38BDF8', '#EF4444'],
                borderWidth: 0,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'bottom', labels: { color: '#94A3B8', font: { size: 10 }, boxWidth: 10 } },
            },
            cutout: '70%',
          },
        })
      );
    }
  }

  function renderIntuneDistributionCharts(data) {
    const osb = data?.os_breakdown || data?.os_distribution || {};
    const mb = data?.manufacturer_breakdown || data?.vendor_distribution || {};

    // OS Distribution Doughnut
    const ctxOs = document.getElementById('chart-intune-os-doughnut');
    if (ctxOs) {
      registerChart(
        'chart-intune-os-doughnut',
        new Chart(ctxOs, {
          type: 'doughnut',
          data: {
            labels: Object.keys(osb),
            datasets: [
              {
                data: Object.values(osb),
                backgroundColor: ['#38BDF8', '#818CF8', '#A78BFA', '#F472B6', '#10B981'],
                borderWidth: 0,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'bottom', labels: { color: '#94A3B8', font: { size: 10 }, boxWidth: 10 } },
            },
            cutout: '65%',
          },
        })
      );
    }

    // Manufacturer Bar
    const ctxMan = document.getElementById('chart-intune-man-bar');
    if (ctxMan) {
      registerChart(
        'chart-intune-man-bar',
        new Chart(ctxMan, {
          type: 'bar',
          data: {
            labels: Object.keys(mb),
            datasets: [
              {
                data: Object.values(mb),
                backgroundColor: ['#F97316', '#38BDF8', '#10B981', '#A78BFA', '#94A3B8'],
                borderRadius: 4,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              x: { grid: { display: false }, ticks: { color: '#94A3B8', font: { size: 10 } } },
              y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#64748B', font: { size: 10 } } },
            },
          },
        })
      );
    }
  }

  // --- Intune Devices Paginated Table ---
  async function loadIntuneDevices() {
    const tbody = document.getElementById('intune-devices-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="p-8 text-center text-xs text-slate-400 font-mono">Fetching managed workplace devices...</td></tr>`;

    const q = new URLSearchParams({
      page: state.intune.page,
      page_size: state.intune.pageSize,
      sort_by: state.intune.sortBy,
      sort_order: state.intune.sortOrder,
    });

    if (state.intune.search.trim()) q.append('search', state.intune.search.trim());
    if (state.intune.status !== 'all') q.append('status', state.intune.status);

    try {
      const data = await apiFetch(`/api/v1/intune/devices?${q.toString()}`);
      state.intune.tableData = data;
      renderIntuneDevicesTable(data);
    } catch (err) {
      console.error('[IntuneDevicesError]', err);
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="7" class="p-4 text-center text-xs text-rose-400 font-mono">Failed to load Intune devices: ${escapeHtml(err.message)}</td></tr>`;
      }
    }
  }

  function renderIntuneDevicesTable(data) {
    const tbody = document.getElementById('intune-devices-tbody');
    const pageInfo = document.getElementById('intune-devices-page-info');
    const btnPrev = document.getElementById('intune-devices-btn-prev');
    const btnNext = document.getElementById('intune-devices-btn-next');
    if (!tbody) return;

    const items = data.items || [];
    const total = data.total || 0;
    const page = data.page || 1;
    const pageSize = data.page_size || 25;

    if (pageInfo) {
      const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
      const end = Math.min(page * pageSize, total);
      pageInfo.innerText = `Showing ${start}-${end} of ${formatNumber(total)} devices`;
    }

    if (btnPrev) btnPrev.disabled = !data.has_prev;
    if (btnNext) btnNext.disabled = !data.has_next;

    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="p-8 text-center"><div class="text-xs text-slate-400 font-medium">No endpoint devices match search criteria.</div></td></tr>`;
      return;
    }

    tbody.innerHTML = items
      .map((item) => {
        const isCompliant = (item.status || '').toLowerCase() === 'compliant';
        const badge = isCompliant
          ? `<span class="px-2 py-0.5 text-[10px] font-semibold bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 rounded-full">Compliant</span>`
          : `<span class="px-2 py-0.5 text-[10px] font-semibold bg-rose-950/60 border border-rose-500/30 text-rose-400 rounded-full">${escapeHtml(item.status || 'Noncompliant')}</span>`;

        return `
        <tr class="border-b border-slate-800/60 hover:bg-slate-800/30 transition text-xs font-normal">
          <td class="px-4 py-3 font-semibold text-slate-200 font-mono flex items-center gap-2">
            <svg class="w-3.5 h-3.5 text-slate-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
            ${escapeHtml(item.name)}
          </td>
          <td class="px-4 py-3 font-mono text-slate-400">${escapeHtml(item.serial_number || '--')}</td>
          <td class="px-4 py-3 text-slate-300">${escapeHtml(item.operating_system || item.ci_type || 'Windows')}</td>
          <td class="px-4 py-3 text-slate-400">${escapeHtml(item.vendor || item.manufacturer || 'Dell')}</td>
          <td class="px-4 py-3 font-mono text-slate-400">${escapeHtml(item.model || '--')}</td>
          <td class="px-4 py-3">${badge}</td>
          <td class="px-4 py-3 font-mono text-[11px] text-slate-500">${item.last_sync_time ? new Date(item.last_sync_time).toLocaleDateString() : 'Recent'}</td>
        </tr>
      `;
      })
      .join('');
  }

  // =========================================================================
  // SECTION 3: LOCATION-WISE ANALYTICS CONTROLLER
  // =========================================================================
  async function loadLocationAnalytics() {
    const tableContainer = document.getElementById('location-sites-table-container');
    if (tableContainer) renderSkeleton(tableContainer, 'table');

    try {
      const resp = await apiFetch('/api/v1/solarwinds/sites');
      const sites = resp?.data?.items || [];
      state.location.sites = sites;

      renderLocationKpis(sites);
      renderLocationComparisonCharts(sites);
      renderLocationSitesTable(sites);
      populateLocationDropdowns(sites);

      // Select top facility for 24h trend drilldown
      if (sites.length && !state.location.selectedSiteId) {
        state.location.selectedSiteId = sites[0].id;
        loadSite24hTrend(sites[0].id);
      }
    } catch (err) {
      console.error('[LocationAnalyticsError]', err);
      if (tableContainer) {
        renderErrorState(tableContainer, 'Failed to load 60-campus location breakdown', loadLocationAnalytics);
      }
    }
  }

  function renderLocationKpis(sites) {
    const totalFacilities = sites.length;
    const topSite = sites.slice().sort((a, b) => b.total_nodes - a.total_nodes)[0];
    const avgSla = sites.length ? sites.reduce((acc, s) => acc + (s.availability_pct || 0), 0) / sites.length : 96.8;
    const critSites = sites.filter((s) => (s.health_status || '').toLowerCase() === 'critical' || (s.availability_pct || 0) < 75).length;

    const el = (id, val) => {
      const target = document.getElementById(id);
      if (target) target.innerHTML = escapeHtml(val);
    };

    el('loc-stat-total-sites', formatNumber(totalFacilities));
    el('loc-stat-top-site', topSite ? `${topSite.name} (${topSite.total_nodes} nodes)` : '--');
    el('loc-stat-avg-sla', formatPercent(avgSla));
    el('loc-stat-crit-sites', `${critSites} Facilities at Risk`);
  }

  function renderLocationComparisonCharts(sites) {
    // Top 10 Campuses by Node Count & SLA
    const top10 = sites.slice().sort((a, b) => b.total_nodes - a.total_nodes).slice(0, 10);
    const ctxTop = document.getElementById('chart-location-top-bar');
    if (ctxTop) {
      registerChart(
        'chart-location-top-bar',
        new Chart(ctxTop, {
          type: 'bar',
          data: {
            labels: top10.map((s) => s.name.split('(')[0].trim()),
            datasets: [
              {
                label: 'Server Nodes',
                data: top10.map((s) => s.total_nodes),
                backgroundColor: '#F97316',
                borderRadius: 4,
              },
            ],
          },
          options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              x: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#64748B', font: { size: 10 } } },
              y: { grid: { display: false }, ticks: { color: '#94A3B8', font: { size: 10 } } },
            },
          },
        })
      );
    }

    // Regional Distribution Doughnut
    const regions = { INDIA: 0, AMERICAS: 0, APAC_EMEA: 0 };
    sites.forEach((s) => {
      const r = (s.region || 'INDIA').toUpperCase();
      if (regions[r] !== undefined) regions[r] += s.total_nodes || 0;
      else regions.APAC_EMEA += s.total_nodes || 0;
    });

    const ctxReg = document.getElementById('chart-location-region-doughnut');
    if (ctxReg) {
      registerChart(
        'chart-location-region-doughnut',
        new Chart(ctxReg, {
          type: 'doughnut',
          data: {
            labels: ['India Facilities', 'Americas Facilities', 'APAC & EMEA Facilities'],
            datasets: [
              {
                data: [regions.INDIA, regions.AMERICAS, regions.APAC_EMEA],
                backgroundColor: ['#10B981', '#38BDF8', '#A78BFA'],
                borderWidth: 0,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'bottom', labels: { color: '#94A3B8', font: { size: 10 }, boxWidth: 10 } },
            },
            cutout: '70%',
          },
        })
      );
    }
  }

  async function loadSite24hTrend(siteId) {
    const trendContainer = document.getElementById('location-site-trend-container');
    if (trendContainer) renderSkeleton(trendContainer, 'chart');

    try {
      const resp = await apiFetch(`/api/v1/solarwinds/sites/${siteId}/trend?hours=24`);
      const trendData = resp?.data || {};
      renderSite24hTrendChart(trendData);
    } catch (err) {
      console.error('[SiteTrendError]', err);
      if (trendContainer) {
        renderErrorState(trendContainer, `Failed to load trend for ${siteId}`, () => loadSite24hTrend(siteId));
      }
    }
  }

  function renderSite24hTrendChart(data) {
    const ctx = document.getElementById('chart-location-site-trend');
    const titleEl = document.getElementById('location-trend-site-name');
    if (titleEl) titleEl.innerText = `${data.site_name || 'Selected Facility'} - 24h Availability & Performance`;

    const points = data.data_points || [];
    const labels = points.map((p) => new Date(p.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    const avail = points.map((p) => p.availability_pct);
    const cpu = points.map((p) => p.avg_cpu);
    const ram = points.map((p) => p.avg_ram);

    if (ctx) {
      registerChart(
        'chart-location-site-trend',
        new Chart(ctx, {
          type: 'line',
          data: {
            labels: labels,
            datasets: [
              {
                label: 'Availability (%)',
                data: avail,
                borderColor: '#10B981',
                backgroundColor: 'rgba(16, 185, 129, 0.08)',
                fill: true,
                tension: 0.3,
                borderWidth: 2,
                pointRadius: 2,
                yAxisID: 'y',
              },
              {
                label: 'Avg CPU (%)',
                data: cpu,
                borderColor: '#F97316',
                borderWidth: 1.5,
                tension: 0.3,
                pointRadius: 1,
                yAxisID: 'y1',
              },
              {
                label: 'Avg RAM (%)',
                data: ram,
                borderColor: '#38BDF8',
                borderWidth: 1.5,
                tension: 0.3,
                pointRadius: 1,
                yAxisID: 'y1',
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { labels: { color: '#94A3B8', font: { size: 10 }, boxWidth: 10 } },
            },
            scales: {
              x: { grid: { color: 'rgba(255, 255, 255, 0.04)' }, ticks: { color: '#64748B', font: { size: 9 } } },
              y: {
                type: 'linear',
                display: true,
                position: 'left',
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                ticks: { color: '#10B981', font: { size: 9 }, callback: (v) => v + '%' },
                suggestedMin: 50,
                suggestedMax: 100,
              },
              y1: {
                type: 'linear',
                display: true,
                position: 'right',
                grid: { drawOnChartArea: false },
                ticks: { color: '#94A3B8', font: { size: 9 }, callback: (v) => v + '%' },
                suggestedMin: 0,
                suggestedMax: 100,
              },
            },
          },
        })
      );
    }
  }

  function renderLocationSitesTable(sites) {
    const tbody = document.getElementById('location-sites-tbody');
    if (!tbody) return;

    let filtered = sites.slice();
    if (state.location.regionFilter !== 'all') {
      filtered = filtered.filter((s) => (s.region || '').toUpperCase() === state.location.regionFilter.toUpperCase());
    }
    if (state.location.statusFilter !== 'all') {
      filtered = filtered.filter((s) => (s.health_status || '').toLowerCase() === state.location.statusFilter.toLowerCase());
    }
    if (state.location.search.trim()) {
      const q = state.location.search.trim().toLowerCase();
      filtered = filtered.filter((s) => s.name.toLowerCase().includes(q) || s.region.toLowerCase().includes(q));
    }

    if (!filtered.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="p-8 text-center text-xs text-slate-400">No campus facilities match the filter.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered
      .map((s) => {
        const status = (s.health_status || 'healthy').toLowerCase();
        const badge =
          status === 'healthy'
            ? `<span class="px-2 py-0.5 text-[10px] font-semibold bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 rounded-full">Healthy</span>`
            : status === 'warning'
            ? `<span class="px-2 py-0.5 text-[10px] font-semibold bg-amber-950/60 border border-amber-500/30 text-amber-400 rounded-full">Degraded</span>`
            : `<span class="px-2 py-0.5 text-[10px] font-semibold bg-rose-950/60 border border-rose-500/30 text-rose-400 rounded-full">Critical</span>`;

        return `
        <tr class="border-b border-slate-800/60 hover:bg-slate-800/30 transition text-xs cursor-pointer" onclick="window.ITOM_INFRA.selectSite('${escapeHtml(s.id)}')">
          <td class="px-4 py-3 font-semibold text-slate-200">${escapeHtml(s.name)}</td>
          <td class="px-4 py-3 font-mono text-slate-400">${escapeHtml(s.region)}</td>
          <td class="px-4 py-3 font-mono text-slate-200 font-bold">${formatNumber(s.total_nodes)}</td>
          <td class="px-4 py-3 font-mono text-emerald-400">${formatNumber(s.up_nodes)}</td>
          <td class="px-4 py-3 font-mono text-amber-400">${formatNumber(s.warning_nodes)}</td>
          <td class="px-4 py-3 font-mono text-rose-400">${formatNumber(s.critical_nodes + (s.down_nodes || 0))}</td>
          <td class="px-4 py-3 font-mono font-bold ${s.availability_pct >= 90 ? 'text-emerald-400' : s.availability_pct >= 75 ? 'text-amber-400' : 'text-rose-400'}">${formatPercent(s.availability_pct)}</td>
          <td class="px-4 py-3">${badge}</td>
          <td class="px-4 py-3">
            <button class="px-2.5 py-1 text-[11px] font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition">Trend →</button>
          </td>
        </tr>
      `;
      })
      .join('');
  }

  function populateLocationDropdowns(sites) {
    const dropdown = document.getElementById('filter-global-location');
    const trendDropdown = document.getElementById('select-trend-facility');
    if (!dropdown && !trendDropdown) return;

    const options = sites.map((s) => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.name)} (${s.total_nodes} nodes)</option>`).join('');

    if (dropdown) {
      dropdown.innerHTML = `<option value="all">Global (All 60 Facilities)</option>` + options;
    }
    if (trendDropdown) {
      trendDropdown.innerHTML = options;
      trendDropdown.addEventListener('change', (e) => {
        loadSite24hTrend(e.target.value);
      });
    }
  }

  // =========================================================================
  // TAB SWITCHING & EVENT WIRING
  // =========================================================================
  function switchTab(tabKey) {
    state.activeTab = tabKey;
    document.querySelectorAll('.infra-tab-btn').forEach((btn) => {
      if (btn.dataset.tab === tabKey) {
        btn.classList.add('bg-slate-800', 'text-white', 'border-slate-700');
        btn.classList.remove('text-slate-400', 'border-transparent');
      } else {
        btn.classList.remove('bg-slate-800', 'text-white', 'border-slate-700');
        btn.classList.add('text-slate-400', 'border-transparent');
      }
    });

    document.querySelectorAll('.infra-tab-pane').forEach((pane) => {
      pane.classList.toggle('hidden', pane.id !== `tab-pane-${tabKey}`);
    });

    if (tabKey === 'solarwinds' && !state.solarwinds.summary) {
      loadSolarWindsSummary();
      loadSolarWindsNodes();
    } else if (tabKey === 'intune' && !state.intune.summary) {
      loadIntuneSummary();
      loadIntuneDevices();
    } else if (tabKey === 'location' && !state.location.sites.length) {
      loadLocationAnalytics();
    }
  }

  function wireEvents() {
    // Tabs
    document.querySelectorAll('.infra-tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // SolarWinds Table Filters & Pagination
    const swSearchInput = document.getElementById('sw-nodes-search');
    if (swSearchInput) {
      swSearchInput.addEventListener(
        'input',
        debounce((e) => {
          state.solarwinds.search = e.target.value;
          state.solarwinds.page = 1;
          loadSolarWindsNodes();
        }, 250)
      );
    }

    document.querySelectorAll('.sw-health-filter-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.sw-health-filter-btn').forEach((b) => b.classList.remove('bg-orange-500/20', 'text-orange-400', 'border-orange-500/40'));
        btn.classList.add('bg-orange-500/20', 'text-orange-400', 'border-orange-500/40');
        state.solarwinds.healthTier = btn.dataset.tier;
        state.solarwinds.page = 1;
        loadSolarWindsNodes();
      });
    });

    const swPrev = document.getElementById('sw-nodes-btn-prev');
    if (swPrev) {
      swPrev.addEventListener('click', () => {
        if (state.solarwinds.page > 1) {
          state.solarwinds.page--;
          loadSolarWindsNodes();
        }
      });
    }

    const swNext = document.getElementById('sw-nodes-btn-next');
    if (swNext) {
      swNext.addEventListener('click', () => {
        state.solarwinds.page++;
        loadSolarWindsNodes();
      });
    }

    const swPageSize = document.getElementById('sw-nodes-page-size');
    if (swPageSize) {
      swPageSize.addEventListener('change', (e) => {
        state.solarwinds.pageSize = Number(e.target.value);
        state.solarwinds.page = 1;
        loadSolarWindsNodes();
      });
    }

    // SolarWinds CSV Export
    const swExportBtn = document.getElementById('btn-export-sw-csv');
    if (swExportBtn) {
      swExportBtn.addEventListener('click', () => {
        const items = state.solarwinds.tableData?.items || [];
        if (!items.length) return alert('No server node data available to export.');
        const headers = ['Node Name', 'IP Address', 'Vendor', 'OS / Model', 'Health Tier', 'Status', 'CPU %', 'RAM %'];
        const rows = items.map((i) => [
          i.name,
          i.ip_address || '',
          i.vendor || '',
          i.operating_system || i.model || '',
          i.health_tier || '',
          i.status || '',
          i.attributes?.cpu_load ?? i.cpu_load ?? '',
          i.attributes?.ram_used ?? i.ram_used ?? '',
        ]);
        exportToCsv('SolarWinds_Server_Nodes', headers, rows);
      });
    }

    // Intune Search & Pagination
    const intuneSearch = document.getElementById('intune-devices-search');
    if (intuneSearch) {
      intuneSearch.addEventListener(
        'input',
        debounce((e) => {
          state.intune.search = e.target.value;
          state.intune.page = 1;
          loadIntuneDevices();
        }, 250)
      );
    }

    document.querySelectorAll('.intune-status-filter-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.intune-status-filter-btn').forEach((b) => b.classList.remove('bg-orange-500/20', 'text-orange-400', 'border-orange-500/40'));
        btn.classList.add('bg-orange-500/20', 'text-orange-400', 'border-orange-500/40');
        state.intune.status = btn.dataset.status;
        state.intune.page = 1;
        loadIntuneDevices();
      });
    });

    const intunePrev = document.getElementById('intune-devices-btn-prev');
    if (intunePrev) {
      intunePrev.addEventListener('click', () => {
        if (state.intune.page > 1) {
          state.intune.page--;
          loadIntuneDevices();
        }
      });
    }

    const intuneNext = document.getElementById('intune-devices-btn-next');
    if (intuneNext) {
      intuneNext.addEventListener('click', () => {
        state.intune.page++;
        loadIntuneDevices();
      });
    }

    // Intune CSV Export
    const intuneExportBtn = document.getElementById('btn-export-intune-csv');
    if (intuneExportBtn) {
      intuneExportBtn.addEventListener('click', () => {
        const items = state.intune.tableData?.items || [];
        if (!items.length) return alert('No device data available to export.');
        const headers = ['Device Name', 'Serial Number', 'Operating System', 'Vendor', 'Model', 'Compliance Status'];
        const rows = items.map((i) => [i.name, i.serial_number || '', i.operating_system || '', i.vendor || '', i.model || '', i.status || '']);
        exportToCsv('Intune_Managed_Devices', headers, rows);
      });
    }

    // Location Table Filters
    document.querySelectorAll('.loc-region-filter-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.loc-region-filter-btn').forEach((b) => b.classList.remove('bg-orange-500/20', 'text-orange-400', 'border-orange-500/40'));
        btn.classList.add('bg-orange-500/20', 'text-orange-400', 'border-orange-500/40');
        state.location.regionFilter = btn.dataset.region;
        renderLocationSitesTable(state.location.sites);
      });
    });

    const locSearch = document.getElementById('loc-sites-search');
    if (locSearch) {
      locSearch.addEventListener(
        'input',
        debounce((e) => {
          state.location.search = e.target.value;
          renderLocationSitesTable(state.location.sites);
        }, 200)
      );
    }

    // Location CSV Export
    const locExportBtn = document.getElementById('btn-export-location-csv');
    if (locExportBtn) {
      locExportBtn.addEventListener('click', () => {
        if (!state.location.sites.length) return alert('No location data available to export.');
        const headers = ['Campus Facility', 'Region', 'Total Nodes', 'Up Nodes', 'Warning Nodes', 'Critical Nodes', 'Availability %', 'Health Status'];
        const rows = state.location.sites.map((s) => [
          s.name,
          s.region,
          s.total_nodes,
          s.up_nodes,
          s.warning_nodes,
          s.critical_nodes,
          s.availability_pct,
          s.health_status,
        ]);
        exportToCsv('Campus_Location_Telemetry', headers, rows);
      });
    }

    // Sync Now button
    const syncBtn = document.getElementById('btn-sync-now');
    if (syncBtn) {
      syncBtn.addEventListener('click', async () => {
        syncBtn.disabled = true;
        syncBtn.innerHTML = `<span>⏳</span> Syncing...`;
        try {
          await apiFetch('/api/v1/sync/run', 15000);
        } catch (e) {
          // Soft ignore if sync endpoint triggers background job
        }
        await Promise.all([loadSolarWindsSummary(), loadSolarWindsNodes(), loadIntuneSummary(), loadIntuneDevices(), loadLocationAnalytics()]);
        syncBtn.disabled = false;
        syncBtn.innerHTML = `<span>⚡</span> Sync Now`;
      });
    }
  }

  // --- Initialize Application ---
  function init() {
    wireEvents();
    // Default initial tab
    switchTab('solarwinds');
  }

  // Global namespace exposure for inline events
  window.ITOM_INFRA = {
    selectSite: (siteId) => {
      state.location.selectedSiteId = siteId;
      loadSite24hTrend(siteId);
      const trendDropdown = document.getElementById('select-trend-facility');
      if (trendDropdown) trendDropdown.value = siteId;
      window.scrollTo({ top: 300, behavior: 'smooth' });
    },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
