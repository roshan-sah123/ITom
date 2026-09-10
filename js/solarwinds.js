/**
 * ITOM OPS Analytics - SolarWinds Orion Domain Module
 *
 * Loads live server node telemetry from the FastAPI + PostgreSQL REST API
 * (`/api/v1/solarwinds/summary`, `/api/v1/solarwinds/nodes`), with a static
 * JSON snapshot fallback if the API is unreachable. Renders KPI cards, the
 * three interactive Chart.js visualizations, the saturated-server triage
 * list, and the searchable/paginated node table.
 */
(function () {
  'use strict';

  const SHARED = window.ITOM_SHARED;
  const CONSTANTS = window.ITOM_CONSTANTS || {};
  const escapeHtml = SHARED.escapeHtml;
  const ENDPOINTS = CONSTANTS.ENDPOINTS || {};

  const STATUS_TO_CODE = { Up: 1, Down: 2, Warning: 3, Critical: 14 };

  let solarwindsData = null;
  let allSwNodes = [];
  let swFilteredNodes = [];
  let swCurrentPage = 1;
  let swPageSize = 50;
  let swAuthoritativeTotal = 1548;

  let swHealthChartInstance = null;
  let swStatusChartInstance = null;
  let swVendorChartInstance = null;

  function normalizeCiRecord(ci) {
    const attrs = ci.attributes || {};
    return {
      NodeID: (ci.source_id || '').replace(/^SW-NODE-/, '') || ci.source_id,
      Caption: ci.name || 'Node',
      IPAddress: ci.ip_address || 'N/A',
      Vendor: ci.vendor || 'Generic',
      MachineType: ci.model || 'Unknown',
      HealthClassification: ci.health_tier || 'High',
      HealthTier: ci.health_tier || 'High',
      CPULoad: attrs.cpu_load ?? 0,
      PercentMemoryUsed: attrs.memory_used ?? 0,
      AvgResponseTime: attrs.latency_ms ?? 0,
      Status: STATUS_TO_CODE[ci.status] || undefined,
      StatusDescription: attrs.status_description || ci.status || 'Unknown',
      City: ci.location || 'Default Location',
    };
  }

  async function loadSolarWindsTelemetry() {
    try {
      const summaryRes = await fetch(ENDPOINTS.API_SOLARWINDS_SUMMARY);
      if (!summaryRes.ok) throw new Error(`HTTP ${summaryRes.status}`);
      solarwindsData = await summaryRes.json();
      swAuthoritativeTotal = solarwindsData?.metrics?.total_server_nodes || swAuthoritativeTotal;
      renderSolarWindsDashboard(solarwindsData);

      const { items } = await SHARED.fetchAllPages(ENDPOINTS.API_SOLARWINDS_NODES, { pageSize: 100 });
      allSwNodes = items.map(normalizeCiRecord);
      applyActiveSwSearch();
      renderSolarWindsTable();
      if (SHARED.getActiveTab() === 'solarwinds') SHARED.updateHeaderStat('solarwinds');
      return;
    } catch (err) {
      console.warn('Live SolarWinds API unavailable, falling back to static snapshot:', err);
    }

    // Fallback: static JSON snapshot (resilience only, not the authoritative source)
    const ts = Date.now();
    for (const path of [ENDPOINTS.SOLARWINDS_SUMMARY, `/${ENDPOINTS.SOLARWINDS_SUMMARY}`]) {
      try {
        const res = await fetch(`${path}?t=${ts}`);
        if (res.ok) {
          solarwindsData = await res.json();
          if (allSwNodes.length === 0) {
            allSwNodes = solarwindsData.sample_nodes || solarwindsData.top_degraded_servers || [];
            swFilteredNodes = [...allSwNodes];
          }
          renderSolarWindsDashboard(solarwindsData);
          break;
        }
      } catch { /* try next fallback path */ }
    }
    for (const path of ['data/solarwinds_nodes.json', '/data/solarwinds_nodes.json']) {
      try {
        const res = await fetch(`${path}?t=${ts}`);
        if (res.ok) {
          const nodesData = await res.json();
          const nodesList = nodesData.nodes || nodesData.sample_nodes || [];
          if (nodesList.length > 0) {
            allSwNodes = nodesList;
            applyActiveSwSearch();
            renderSolarWindsTable();
            if (SHARED.getActiveTab() === 'solarwinds') SHARED.updateHeaderStat('solarwinds');
          }
          break;
        }
      } catch { /* try next fallback path */ }
    }
  }

  function applyActiveSwSearch() {
    const searchInput = document.getElementById('swSearchInput');
    const q = searchInput ? searchInput.value.toLowerCase().trim() : '';
    swFilteredNodes = q ? filterSwNodes(q) : [...allSwNodes];
  }

  function filterSwNodes(q) {
    return allSwNodes.filter((n) =>
      String(n.NodeID || '').includes(q) ||
      (n.Caption || '').toLowerCase().includes(q) ||
      (n.IPAddress || '').toLowerCase().includes(q) ||
      (n.Vendor || '').toLowerCase().includes(q) ||
      (n.MachineType || '').toLowerCase().includes(q) ||
      (n.HealthClassification || n.HealthTier || '').toLowerCase().includes(q) ||
      (n.City || '').toLowerCase().includes(q) ||
      (n.StatusDescription || '').toLowerCase().includes(q)
    );
  }

  function renderSolarWindsDashboard(data) {
    const metrics = data.metrics || {};
    const setElemText = (id, text) => {
      const elem = document.getElementById(id);
      if (elem) elem.textContent = text;
    };

    const lowHealth = Number(metrics.low_critical_nodes ?? metrics.low_health_nodes ?? 50);
    setElemText('swTotalNodes', Number(metrics.total_server_nodes || 1548).toLocaleString());
    setElemText('swHighHealthCount', Number(metrics.high_health_nodes || 1362).toLocaleString());
    setElemText('swMedHealthCount', Number(metrics.medium_health_nodes || 136).toLocaleString());
    setElemText('swLowHealthCount', lowHealth.toLocaleString());
    setElemText('swCriticalBadge', `${lowHealth.toLocaleString()} Critical Nodes`);

    const healthTag = document.getElementById('swHealthTag');
    if (healthTag) healthTag.textContent = `${metrics.high_health_pct || 90.73}% High`;

    const cpuMemElem = document.getElementById('swAvgCpuMem');
    if (cpuMemElem) {
      cpuMemElem.innerHTML = `${metrics.avg_fleet_cpu_load_pct ?? 14.9}% <span class="text-xs text-muted">CPU</span> &bull; ${metrics.avg_fleet_ram_used_pct ?? 22.0}% <span class="text-xs text-muted">RAM</span>`;
    }

    const latElem = document.getElementById('swAvgLatency');
    if (latElem) latElem.innerHTML = `${metrics.avg_fleet_latency_ms || 43.9} <span class="text-xs text-muted">ms</span>`;

    SHARED.updateHeaderStat(SHARED.getActiveTab());

    renderSwHealthChart(data.health_breakdown || {});
    renderSwStatusChart(metrics.status_counts || {});
    renderSwVendorChart(data.vendor_breakdown || data.vendor_distribution || {});
    renderSwSaturatedList(data.top_saturated_servers || data.top_degraded_servers || []);
    renderSolarWindsTable();
  }

  function renderSwSaturatedList(servers) {
    const container = document.getElementById('swSaturatedList');
    if (!container) return;

    if (!servers || servers.length === 0) {
      container.innerHTML = `<div class="text-xs text-muted py-2 text-center">No degraded servers currently reporting.</div>`;
      return;
    }

    container.innerHTML = servers.slice(0, 10).map((s) => {
      const cpu = Number(s.CPULoad || 0);
      const ram = Number(s.PercentMemoryUsed || 0);
      return `
        <div class="saturated-item" data-caption="${escapeHtml(s.Caption || 'Server')}" title="Click to filter table by ${escapeHtml(s.Caption || 'Server')}">
          <div class="saturated-info">
            <span class="saturated-name">${escapeHtml(s.Caption || 'Server')}</span>
            <span class="saturated-ip">${escapeHtml(s.IPAddress || 'N/A')} &bull; ${escapeHtml(s.Vendor || 'Hardware')}</span>
          </div>
          <div class="saturated-metrics">
            <span class="saturated-pill ${cpu > 90 ? 'crit' : 'warn'}">CPU ${cpu}%</span>
            <span class="saturated-pill ${ram > 90 ? 'crit' : 'warn'}">RAM ${ram}%</span>
          </div>
        </div>
      `;
    }).join('');

    container.querySelectorAll('.saturated-item').forEach((item) => {
      item.addEventListener('click', () => {
        const filterTerm = item.getAttribute('data-caption');
        const searchInput = document.getElementById('swSearchInput');
        if (searchInput && filterTerm) {
          searchInput.value = filterTerm;
          swCurrentPage = 1;
          swFilteredNodes = filterSwNodes(filterTerm.toLowerCase().trim());
          renderSolarWindsTable();
          searchInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      });
    });
  }

  function renderSwHealthChart(healthData) {
    const canvas = document.getElementById('swHealthChart');
    if (!canvas || typeof Chart === 'undefined') return;
    SHARED.destroyChartSafe(swHealthChartInstance, canvas);

    const tiers = ['High', 'Medium', 'Low'];
    swHealthChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: ['High Health (Healthy)', 'Medium Health (Warning)', 'Low Health (Critical)'],
        datasets: [{ data: [Number(healthData.High || 0), Number(healthData.Medium || 0), Number(healthData.Low || 0)], backgroundColor: ['#10B981', '#F59E0B', '#EF4444'], borderColor: '#141414', borderWidth: 2 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (event, elements) => {
          if (elements && elements.length > 0) {
            const selectedTier = tiers[elements[0].index];
            const swSearch = document.getElementById('swSearchInput');
            if (swSearch && selectedTier) {
              swSearch.value = selectedTier;
              swCurrentPage = 1;
              swFilteredNodes = allSwNodes.filter((n) => (n.HealthClassification || n.HealthTier || '').toLowerCase() === selectedTier.toLowerCase());
              renderSolarWindsTable();
              swSearch.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
          }
        },
        plugins: {
          legend: { position: 'right', labels: { color: '#A3A3A3', font: { family: 'Inter', size: 11 } } },
          tooltip: { callbacks: { afterLabel: () => '\ud83d\udca1 Click tier to filter table' } },
        },
      },
    });
  }

  function renderSwStatusChart(statusData) {
    const canvas = document.getElementById('swStatusChart');
    if (!canvas || typeof Chart === 'undefined') return;
    SHARED.destroyChartSafe(swStatusChartInstance, canvas);

    const statusKeys = ['up', 'warning', 'critical', 'down', 'unmanaged_unknown'];
    const statusLabels = ['Up (Active)', 'Warning', 'Critical', 'Down', 'Unmanaged'];
    const values = statusKeys.map((k) => Number(statusData[k] || 0));

    swStatusChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: { labels: statusLabels, datasets: [{ label: 'Server Nodes', data: values, backgroundColor: ['#10B981', '#F59E0B', '#EF4444', '#DC2626', '#6B7280'], borderRadius: 6 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (event, elements) => {
          if (elements && elements.length > 0) {
            const selectedStatus = statusKeys[elements[0].index];
            const swSearch = document.getElementById('swSearchInput');
            if (swSearch) {
              const termMap = { up: 'Up', warning: 'Warning', critical: 'Critical', down: 'Down', unmanaged_unknown: 'Unmanaged' };
              swSearch.value = termMap[selectedStatus];
              swCurrentPage = 1;
              swFilteredNodes = allSwNodes.filter((n) => {
                const s = Number(n.Status);
                const sDesc = (n.StatusDescription || '').toLowerCase();
                if (selectedStatus === 'up') return s === 1 || sDesc.includes('up');
                if (selectedStatus === 'warning') return s === 3 || sDesc.includes('warn');
                if (selectedStatus === 'critical') return s === 14 || sDesc.includes('crit');
                if (selectedStatus === 'down') return s === 2 || sDesc.includes('down');
                if (selectedStatus === 'unmanaged_unknown') return s === 0 || s === 9 || sDesc.includes('unmanaged') || sDesc.includes('unknown');
                return true;
              });
              renderSolarWindsTable();
              swSearch.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
          }
        },
        plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: () => '\ud83d\udca1 Click bar to filter table' } } },
        scales: {
          x: { ticks: { color: '#A3A3A3', font: { family: 'Inter' } }, grid: { color: '#222222' } },
          y: { ticks: { color: '#A3A3A3', font: { family: 'Inter' } }, grid: { color: '#222222' } },
        },
      },
    });
  }

  function renderSwVendorChart(vendorData) {
    const canvas = document.getElementById('swVendorChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const filtered = Object.entries(vendorData || {}).filter(([, v]) => v > 0);
    const labels = filtered.map(([k]) => k);
    const values = filtered.map(([, v]) => v);

    SHARED.destroyChartSafe(swVendorChartInstance, canvas);
    swVendorChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'pie',
      data: { labels, datasets: [{ data: values, backgroundColor: ['#3B82F6', '#F97316', '#10B981', '#A855F7', '#6B7280', '#EC4899'], borderColor: '#141414', borderWidth: 2 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (event, elements) => {
          if (elements && elements.length > 0) {
            const selectedVendor = labels[elements[0].index];
            const swSearch = document.getElementById('swSearchInput');
            if (swSearch && selectedVendor) {
              swSearch.value = selectedVendor;
              swCurrentPage = 1;
              swFilteredNodes = allSwNodes.filter((n) => (n.Vendor || '').toLowerCase().includes(selectedVendor.toLowerCase()));
              renderSolarWindsTable();
              swSearch.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
          }
        },
        plugins: {
          legend: { position: 'right', labels: { color: '#A3A3A3', font: { family: 'Inter', size: 11 } } },
          tooltip: { callbacks: { afterLabel: () => '\ud83d\udca1 Click slice to filter table' } },
        },
      },
    });
  }

  function renderSolarWindsTable() {
    const tbody = document.getElementById('swTableBody');
    const countSpan = document.getElementById('swTableRecordCount');
    const paginationContainer = document.getElementById('swPagination');
    if (!tbody) return;

    const totalCount = swFilteredNodes.length;
    if (totalCount === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-6">No matching server nodes found.</td></tr>`;
      if (countSpan) countSpan.textContent = 'Showing 0 matching server nodes';
      if (paginationContainer) paginationContainer.innerHTML = '';
      return;
    }

    const totalPages = Math.max(1, Math.ceil(totalCount / swPageSize));
    if (swCurrentPage > totalPages) swCurrentPage = totalPages;
    if (swCurrentPage < 1) swCurrentPage = 1;

    const startIndex = (swCurrentPage - 1) * swPageSize;
    const displayNodes = swFilteredNodes.slice(startIndex, Math.min(startIndex + swPageSize, totalCount));

    const statusMap = {
      1: '<span class="badge badge-success">Up</span>',
      2: '<span class="badge badge-danger">Down</span>',
      3: '<span class="badge badge-warning">Warning</span>',
      14: '<span class="badge badge-danger">Critical</span>',
    };

    tbody.innerHTML = displayNodes.map((n) => {
      const tier = n.HealthClassification || n.HealthTier || 'High';
      const tierClass = tier === 'High' ? 'badge-success' : tier === 'Medium' ? 'badge-warning' : 'badge-danger';
      const cpuVal = Number(n.CPULoad || 0);
      const ramVal = Number(n.PercentMemoryUsed || 0);
      const latVal = Number(n.AvgResponseTime || n.ResponseTime || 0);
      const statusBadge = statusMap[n.Status] || `<span class="badge badge-neutral">${escapeHtml(n.StatusDescription || 'Unknown')}</span>`;

      return `
        <tr>
          <td><div class="device-cell"><span class="device-name font-semibold text-white">${escapeHtml(n.Caption)}</span><span class="device-id font-mono text-muted">ID: ${escapeHtml(String(n.NodeID))}</span></div></td>
          <td class="font-mono text-xs text-accent">${escapeHtml(n.IPAddress || 'N/A')}</td>
          <td><div class="mfg-cell"><span>${escapeHtml(n.Vendor || 'Generic')}</span><span class="text-muted text-xs">${escapeHtml(n.MachineType || 'N/A')}</span></div></td>
          <td><span class="badge ${tierClass}">${escapeHtml(tier)}</span></td>
          <td><span class="font-semibold ${cpuVal > 85 ? 'text-danger' : cpuVal > 70 ? 'text-warning' : 'text-light'}">${cpuVal}%</span></td>
          <td><span class="font-semibold ${ramVal > 85 ? 'text-danger' : ramVal > 70 ? 'text-warning' : 'text-light'}">${ramVal}%</span></td>
          <td class="font-mono text-xs">${latVal >= 0 ? `${latVal} ms` : 'Down'}</td>
          <td>${statusBadge}</td>
        </tr>
      `;
    }).join('');

    SHARED.renderEnterprisePagination({
      container: paginationContainer,
      countLabel: countSpan,
      totalItems: totalCount,
      pageSize: swPageSize,
      currentPage: swCurrentPage,
      pageSizeOptions: [10, 25, 50, 100],
      itemName: 'Server Nodes',
      totalAuthoritative: allSwNodes.length,
      onPageChange: (newPage) => {
        swCurrentPage = newPage;
        renderSolarWindsTable();
        SHARED.resetTableScroll('view-solarwinds');
      },
      onPageSizeChange: (newSize, newPage) => {
        swPageSize = newSize;
        swCurrentPage = newPage;
        renderSolarWindsTable();
        SHARED.resetTableScroll('view-solarwinds');
      },
    });
  }

  function initSearch() {
    const swSearch = document.getElementById('swSearchInput');
    if (!swSearch) return;
    swSearch.addEventListener('input', SHARED.debounce((e) => {
      const q = e.target.value.toLowerCase().trim();
      swCurrentPage = 1;
      swFilteredNodes = q ? filterSwNodes(q) : [...allSwNodes];
      renderSolarWindsTable();
    }, 200));
  }

  function exportCsv() {
    const link = document.createElement('a');
    link.setAttribute('href', 'exports/solarwinds_nodes_complete.csv');
    link.setAttribute('download', `solarwinds_nodes_complete_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  SHARED.registerDomain('solarwinds', {
    pillElementId: 'tabPillSolarwinds',
    pillSuffix: 'Server Nodes',
    headerLabel: 'Total Monitored Nodes',
    getTotal: () => solarwindsData?.metrics?.total_server_nodes || (allSwNodes.length > 0 ? allSwNodes.length : swAuthoritativeTotal),
    isRendered: () => !!swHealthChartInstance,
    getData: () => solarwindsData,
    renderDashboard: renderSolarWindsDashboard,
    renderTable: renderSolarWindsTable,
    resizeCharts: () => {
      if (swHealthChartInstance) swHealthChartInstance.resize();
      if (swStatusChartInstance) swStatusChartInstance.resize();
      if (swVendorChartInstance) swVendorChartInstance.resize();
    },
  });

  window.ITOM_SOLARWINDS = { loadSolarWindsTelemetry, initSearch, exportCsv };
})();
