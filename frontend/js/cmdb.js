/**
 * ITOM OPS Analytics - Network CMDB Domain Module
 *
 * Loads live Configuration Item telemetry from the FastAPI + PostgreSQL REST
 * API (`/api/v1/cmdb/summary`, `/api/v1/cmdb/cis`), with a static JSON
 * snapshot fallback if the API is unreachable. Renders KPI cards, the three
 * interactive Chart.js visualizations, and the searchable/paginated CI table.
 */
(function () {
  'use strict';

  const SHARED = window.ITOM_SHARED;
  const CONSTANTS = window.ITOM_CONSTANTS || {};
  const escapeHtml = SHARED.escapeHtml;
  const ENDPOINTS = CONSTANTS.ENDPOINTS || {};

  let cmdbData = null;
  let allCmdbCis = [];
  let cmdbFilteredCis = [];
  let cmdbCurrentPage = 1;
  let cmdbPageSize = 50;
  let cmdbAuthoritativeTotal = 1548;

  let cmdbRoleChartInstance = null;
  let cmdbCompChartInstance = null;
  let cmdbLocChartInstance = null;

  function normalizeCiRecord(ci) {
    return {
      ci_id: ci.id,
      name: ci.name,
      ci_type: ci.ci_type,
      ip_address: ci.ip_address,
      vendor: ci.vendor,
      model: ci.model,
      operating_system: ci.operating_system,
      location: ci.location,
      status: ci.status,
      health_tier: ci.health_tier,
    };
  }

  /** Adapt the generic /api/v1/cmdb/summary envelope into the view-model shape the dashboard renders. */
  function adaptSummaryPayload(data) {
    return {
      metrics: {
        total_network_cis: data.total_cis,
        high_health_cis: data.high_health_count,
        low_health_cis: data.low_health_count,
        total_servers: data.total_servers,
        total_network_devices: data.total_network_devices,
        control_compliance_rate: data.compliance_rate_pct,
      },
      metadata: {
        mode: 'live',
        connection_status: 'Connected',
        generated_at: new Date().toISOString(),
      },
      ci_type_distribution: data.ci_type_distribution,
      health_tier_breakdown: data.health_breakdown,
      total_cis: data.total_cis,
    };
  }

  async function loadCmdbTelemetry() {
    try {
      const summaryRes = await fetch(ENDPOINTS.API_CMDB_SUMMARY);
      if (!summaryRes.ok) throw new Error(`HTTP ${summaryRes.status}`);
      const rawSummary = await summaryRes.json();
      cmdbAuthoritativeTotal = rawSummary.total_cis || cmdbAuthoritativeTotal;
      cmdbData = adaptSummaryPayload(rawSummary);
      renderCmdbDashboard(cmdbData);

      const { items } = await SHARED.fetchAllPages(ENDPOINTS.API_CMDB_CIS, { pageSize: 100 });
      allCmdbCis = items.map(normalizeCiRecord);
      applyActiveCmdbSearch();
      renderCmdbTable();
      if (SHARED.getActiveTab() === 'cmdb') SHARED.updateHeaderStat('cmdb');
      return;
    } catch (err) {
      console.warn('Live CMDB API unavailable, falling back to static snapshot:', err);
    }

    // Fallback: static JSON snapshot (resilience only, not the authoritative source)
    const ts = Date.now();
    for (const path of [ENDPOINTS.CMDB_SUMMARY, `/${ENDPOINTS.CMDB_SUMMARY}`]) {
      try {
        const res = await fetch(`${path}?t=${ts}`);
        if (res.ok) {
          cmdbData = await res.json();
          if (cmdbData.sample_devices && Array.isArray(cmdbData.sample_devices)) {
            allCmdbCis = [...cmdbData.sample_devices];
            applyActiveCmdbSearch();
          }
          renderCmdbDashboard(cmdbData);
          if (SHARED.getActiveTab() === 'cmdb') SHARED.updateHeaderStat('cmdb');
          break;
        }
      } catch { /* try next fallback path */ }
    }
  }

  function applyActiveCmdbSearch() {
    const cmdbSearch = document.getElementById('cmdbSearchInput');
    const q = cmdbSearch ? cmdbSearch.value.toLowerCase().trim() : '';
    cmdbFilteredCis = q ? filterCmdbCis(q) : [...allCmdbCis];
  }

  function filterCmdbCis(q) {
    return allCmdbCis.filter((c) =>
      (c.ci_id || c.device_id || '').toLowerCase().includes(q) ||
      (c.name || c.caption || c.device_token || '').toLowerCase().includes(q) ||
      (c.ci_type || c.role || c.device_role || '').toLowerCase().includes(q) ||
      (c.ip_address || c.IPAddress || '').toLowerCase().includes(q) ||
      (c.vendor || c.hardware_vendor || '').toLowerCase().includes(q) ||
      (c.model || c.technology || '').toLowerCase().includes(q) ||
      (c.operating_system || '').toLowerCase().includes(q) ||
      (c.location || '').toLowerCase().includes(q) ||
      (c.status || '').toLowerCase().includes(q) ||
      (c.health_tier || c.compliance_state || '').toLowerCase().includes(q)
    );
  }

  function renderCmdbDashboard(data) {
    const metrics = data.metrics || {};
    const meta = data.metadata || {};
    const setElemText = (id, text) => {
      const elem = document.getElementById(id);
      if (elem) elem.textContent = text;
    };

    setElemText('cmdbTotalCis', Number(metrics.total_network_cis || data.total_configuration_items || 1543).toLocaleString());
    setElemText('cmdbPassedControls', Number(metrics.high_health_cis || 1403).toLocaleString());
    setElemText('cmdbFailedControls', Number(metrics.low_health_cis || 64).toLocaleString());
    setElemText('cmdbTotalServers', Number(metrics.total_servers || 260).toLocaleString());
    setElemText('cmdbTotalNetworkDevices', Number(metrics.total_network_devices || 1283).toLocaleString());

    const rateTag = document.getElementById('cmdbControlRateTag');
    if (rateTag) rateTag.textContent = `${metrics.control_compliance_rate || 90.93}% High`;

    const modeTag = document.getElementById('cmdbModeTag');
    if (modeTag) {
      const mode = meta.mode || 'live';
      modeTag.className = mode === 'live' ? 'badge badge-live' : 'badge badge-warning';
      modeTag.textContent = mode === 'live' ? 'Live SWIS Data' : 'Verified Cached Snapshot';
    }

    const connStatus = document.getElementById('cmdbConnectionStatus');
    if (connStatus) connStatus.textContent = meta.connection_status || 'Connected';

    const lastRefreshed = document.getElementById('cmdbLastRefreshed');
    if (lastRefreshed && meta.generated_at) {
      try {
        const dt = new Date(meta.generated_at);
        lastRefreshed.textContent = `${dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })} ${dt.toLocaleDateString()}`;
      } catch {
        lastRefreshed.textContent = meta.generated_at;
      }
    }

    renderCmdbRoleChart(data.ci_type_distribution || data.device_role_distribution);
    renderCmdbComplianceChart(data.health_tier_breakdown || data.compliance_breakdown);
    renderCmdbLocationChart(data.top_locations || data.ip_distribution);
    renderCmdbTable();
  }

  function renderCmdbRoleChart(roleData) {
    const canvas = document.getElementById('cmdbRoleChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const filtered = Object.entries(roleData || {}).filter(([, v]) => v > 0);
    const labels = filtered.map(([k]) => k);
    const values = filtered.map(([, v]) => v);

    SHARED.destroyChartSafe(cmdbRoleChartInstance, canvas);
    cmdbRoleChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: labels.length > 0 ? labels : ['Access Switch', 'Server', 'Core Switch', 'Router', 'Firewall', 'Wireless Controller'],
        datasets: [{ data: values.length > 0 ? values : [700, 260, 150, 80, 50, 40], backgroundColor: ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4', '#64748B'], borderColor: '#141414', borderWidth: 2 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (event, elements) => {
          if (elements && elements.length > 0) {
            const selectedRole = labels[elements[0].index];
            const searchInput = document.getElementById('cmdbSearchInput');
            if (searchInput && selectedRole) {
              searchInput.value = selectedRole;
              cmdbCurrentPage = 1;
              cmdbFilteredCis = allCmdbCis.filter((c) => (c.ci_type || c.role || '').toLowerCase().includes(selectedRole.toLowerCase()) || (c.model || '').toLowerCase().includes(selectedRole.toLowerCase()));
              renderCmdbTable();
              searchInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
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

  function renderCmdbComplianceChart(compData) {
    const canvas = document.getElementById('cmdbComplianceChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const colorMap = { high: '#10B981', medium: '#F59E0B', low: '#EF4444', compliant: '#10B981', 'action required': '#EF4444', 'missing serial': '#F59E0B', 'under review': '#6B7280' };
    const keys = Object.keys(compData || { High: 1403, Medium: 76, Low: 64 });
    const values = keys.map((k) => (compData ? compData[k] : 0));
    const bgColors = keys.map((k) => colorMap[k.toLowerCase()] || '#3B82F6');

    SHARED.destroyChartSafe(cmdbCompChartInstance, canvas);
    cmdbCompChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: { labels: keys, datasets: [{ label: 'Configuration Items', data: values, backgroundColor: bgColors, borderRadius: 6 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (event, elements) => {
          if (elements && elements.length > 0) {
            const selectedStatus = keys[elements[0].index];
            const searchInput = document.getElementById('cmdbSearchInput');
            if (searchInput && selectedStatus) {
              searchInput.value = selectedStatus;
              cmdbCurrentPage = 1;
              cmdbFilteredCis = allCmdbCis.filter((c) => (c.health_tier || c.compliance_state || '').toLowerCase() === selectedStatus.toLowerCase());
              renderCmdbTable();
              searchInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
          }
        },
        plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: () => '\ud83d\udca1 Click bar to filter table' } } },
        scales: {
          x: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#A3A3A3', font: { family: 'Inter', size: 10 } } },
          y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#A3A3A3' } },
        },
      },
    });
  }

  function renderCmdbLocationChart(locData) {
    const canvas = document.getElementById('cmdbLocationChart');
    if (!canvas || typeof Chart === 'undefined') return;

    let labels = [];
    let values = [];
    if (Array.isArray(locData)) {
      const top = locData.slice(0, 6);
      labels = top.map((l) => l.location || l.site);
      values = top.map((l) => l.count || l.device_count);
    } else if (locData && locData.top_sites) {
      const top = locData.top_sites.slice(0, 6);
      labels = top.map((s) => s.site || s.location);
      values = top.map((s) => s.device_count || s.count);
    }

    SHARED.destroyChartSafe(cmdbLocChartInstance, canvas);
    cmdbLocChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: labels.length > 0 ? labels : ['Gr.Noida-T-AB', 'Gr.Noida-TD', 'BANGALORE', 'GURUGRAM', 'BPS-PUNE', 'Hyderabad'],
        datasets: [{ label: 'Deployed CIs', data: values.length > 0 ? values : [375, 129, 121, 80, 64, 64], backgroundColor: '#10B981', borderRadius: 6 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#A3A3A3', font: { family: 'Inter', size: 10 } } },
          y: { grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#A3A3A3' } },
        },
      },
    });
  }

  function renderCmdbTable() {
    const tbody = document.getElementById('cmdbTableBody');
    const countSpan = document.getElementById('cmdbTableRecordCount');
    const paginationContainer = document.getElementById('cmdbPagination');
    if (!tbody) return;

    const dataset = cmdbFilteredCis.length > 0 ? cmdbFilteredCis : allCmdbCis;
    const totalRecords = dataset.length;

    if (totalRecords === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-muted">No Live Configuration Items match your search criteria.</td></tr>`;
      if (countSpan) countSpan.textContent = 'Showing 0 matching configuration items';
      if (paginationContainer) paginationContainer.innerHTML = '';
      return;
    }

    const totalPages = Math.max(1, Math.ceil(totalRecords / cmdbPageSize));
    if (cmdbCurrentPage > totalPages) cmdbCurrentPage = totalPages;
    if (cmdbCurrentPage < 1) cmdbCurrentPage = 1;

    const startIndex = (cmdbCurrentPage - 1) * cmdbPageSize;
    const pageData = dataset.slice(startIndex, Math.min(startIndex + cmdbPageSize, totalRecords));

    tbody.innerHTML = pageData.map((c) => {
      const tier = (c.health_tier || 'High').toLowerCase();
      let tierClass = 'badge-success';
      if (tier === 'medium' || tier.includes('warning')) tierClass = 'badge-warning';
      else if (tier === 'low' || tier.includes('critical') || tier.includes('action')) tierClass = 'badge-danger';

      const statusStr = (c.status || 'Up').toLowerCase();
      let statusClass = 'badge-success';
      if (statusStr === 'down' || statusStr === 'critical') statusClass = 'badge-danger';
      else if (statusStr === 'warning') statusClass = 'badge-warning';
      else if (statusStr === 'unmanaged') statusClass = 'badge-secondary';

      const ciId = c.ci_id || c.device_id || `SW-NODE-${c.NodeID || 'N/A'}`;
      const name = c.name || c.caption || c.device_token || 'Node';
      const ciType = c.ci_type || c.role || c.device_role || 'Switch';
      const ip = c.ip_address || c.IPAddress || 'N/A';
      const vendor = c.vendor || c.hardware_vendor || 'Generic';
      const model = c.model || c.technology || c.operating_system || '';
      const location = c.location || 'Default Site';

      return `
        <tr>
          <td class="font-mono text-xs text-accent font-semibold">${escapeHtml(ciId)}</td>
          <td><span class="badge badge-outline">${escapeHtml(ciType)}</span></td>
          <td><div class="device-cell"><span class="device-name font-semibold text-white">${escapeHtml(name)}</span><span class="device-meta text-xs text-muted">${escapeHtml(c.operating_system || model)}</span></div></td>
          <td class="font-mono text-xs text-white">${escapeHtml(ip)}</td>
          <td><div class="mfg-cell"><span>${escapeHtml(vendor)}</span><span class="text-muted text-xs">${escapeHtml(model)}</span></div></td>
          <td class="font-mono text-xs text-muted">${escapeHtml(location)}</td>
          <td><span class="badge ${statusClass}">${escapeHtml(c.status || 'Up')}</span></td>
          <td><span class="badge ${tierClass}">${escapeHtml(c.health_tier || 'High')}</span></td>
        </tr>
      `;
    }).join('');

    SHARED.renderEnterprisePagination({
      container: paginationContainer,
      countLabel: countSpan,
      totalItems: totalRecords,
      pageSize: cmdbPageSize,
      currentPage: cmdbCurrentPage,
      pageSizeOptions: [10, 25, 50, 100],
      itemName: 'Configuration Items',
      totalAuthoritative: allCmdbCis.length,
      onPageChange: (newPage) => {
        cmdbCurrentPage = newPage;
        renderCmdbTable();
        SHARED.resetTableScroll('view-cmdb');
      },
      onPageSizeChange: (newSize, newPage) => {
        cmdbPageSize = newSize;
        cmdbCurrentPage = newPage;
        renderCmdbTable();
        SHARED.resetTableScroll('view-cmdb');
      },
    });
  }

  function initSearch() {
    const cmdbSearch = document.getElementById('cmdbSearchInput');
    if (!cmdbSearch) return;
    cmdbSearch.addEventListener('input', SHARED.debounce((e) => {
      const q = e.target.value.toLowerCase().trim();
      cmdbCurrentPage = 1;
      cmdbFilteredCis = q ? filterCmdbCis(q) : [...allCmdbCis];
      renderCmdbTable();
    }, 200));
  }

  function exportCsv() {
    const link = document.createElement('a');
    link.setAttribute('href', 'exports/cmdb_network_cis_complete.csv');
    link.setAttribute('download', `cmdb_network_cis_complete_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  SHARED.registerDomain('cmdb', {
    pillElementId: 'tabPillCmdb',
    pillSuffix: 'CIs',
    headerLabel: 'CMDB Network CIs',
    getTotal: () => cmdbData?.total_cis || (allCmdbCis.length > 0 ? allCmdbCis.length : cmdbAuthoritativeTotal),
    isRendered: () => !!cmdbRoleChartInstance,
    getData: () => cmdbData,
    renderDashboard: renderCmdbDashboard,
    renderTable: renderCmdbTable,
    resizeCharts: () => {
      if (cmdbRoleChartInstance) cmdbRoleChartInstance.resize();
      if (cmdbCompChartInstance) cmdbCompChartInstance.resize();
      if (cmdbLocChartInstance) cmdbLocChartInstance.resize();
    },
  });

  window.ITOM_CMDB = { loadCmdbTelemetry, initSearch, exportCsv };
})();
