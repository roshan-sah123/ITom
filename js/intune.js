/**
 * ITOM OPS Analytics - Microsoft Intune Domain Module
 *
 * Loads live device telemetry from the FastAPI + PostgreSQL REST API
 * (`/api/v1/intune/summary`, `/api/v1/intune/devices`), with a static JSON
 * snapshot fallback if the API is unreachable. Renders KPI cards, the three
 * interactive Chart.js visualizations, and the searchable/paginated device
 * table, then registers itself with the shared tab router.
 */
(function () {
  'use strict';

  const SHARED = window.ITOM_SHARED;
  const CONSTANTS = window.ITOM_CONSTANTS || {};
  const escapeHtml = SHARED.escapeHtml;
  const ENDPOINTS = CONSTANTS.ENDPOINTS || {};

  let intuneData = null;
  let allIntuneDevices = [];
  let intuneFilteredDevices = [];
  let intuneCurrentPage = 1;
  let intunePageSize = 50;
  let intuneAuthoritativeTotal = 25987;

  let osChartInstance = null;
  let compChartInstance = null;
  let mfgChartInstance = null;

  function normalizeCiRecord(ci) {
    const attrs = ci.attributes || {};
    const totalBytes = Number(attrs.total_storage_bytes || 0);
    const freeBytes = Number(attrs.free_storage_bytes || 0);
    let usedPct = 0;
    let freeGB = 0;
    if (totalBytes > 0) {
      usedPct = Math.round(((totalBytes - freeBytes) / totalBytes) * 100);
      freeGB = Math.round(freeBytes / (1024 * 1024 * 1024));
    }
    return {
      id: ci.id || '',
      deviceName: ci.name || 'Unknown Host',
      operatingSystem: ci.ci_type || 'Windows',
      osVersion: attrs.os_version || '',
      userPrincipalName: attrs.user_principal_name || 'N/A',
      manufacturer: ci.vendor || 'Other',
      model: ci.model || 'Corporate Device',
      serialNumber: ci.serial_number || 'N/A',
      complianceState: ci.status || 'Compliant',
      usedStoragePct: usedPct,
      freeStorageGB: freeGB,
      lastSync: ci.last_sync_time || '',
    };
  }

  // Legacy static-snapshot shape normalizer (fallback path only)
  function normalizeLegacyDevice(d) {
    const totalBytes = Number(d.totalStorageSpaceInBytes || 0);
    const freeBytes = Number(d.freeStorageSpaceInBytes || 0);
    let usedPct = 0;
    let freeGB = 0;
    if (totalBytes > 0) {
      usedPct = Math.round(((totalBytes - freeBytes) / totalBytes) * 100);
      freeGB = Math.round(freeBytes / (1024 * 1024 * 1024));
    }
    return {
      id: d.id || '',
      deviceName: d.deviceName || 'Unknown Host',
      operatingSystem: d.operatingSystem || 'Windows',
      osVersion: d.osVersion || '',
      userPrincipalName: d.userPrincipalName || 'N/A',
      manufacturer: d.manufacturer || 'Dell Inc.',
      model: d.model || 'Corporate Device',
      serialNumber: d.serialNumber || 'N/A',
      complianceState: d.complianceState || 'Compliant',
      usedStoragePct: usedPct,
      freeStorageGB: freeGB,
      lastSync: d.lastSyncDateTime || d.lastSync || '',
    };
  }

  async function loadIntuneTelemetry() {
    try {
      const summaryRes = await fetch(ENDPOINTS.API_INTUNE_SUMMARY);
      if (!summaryRes.ok) throw new Error(`HTTP ${summaryRes.status}`);
      intuneData = await summaryRes.json();
      intuneAuthoritativeTotal = intuneData?.metrics?.total_managed_devices || intuneAuthoritativeTotal;
      renderIntuneDashboard(intuneData);

      const { items } = await SHARED.fetchAllPages(ENDPOINTS.API_INTUNE_DEVICES, { pageSize: 100 });
      allIntuneDevices = items.map(normalizeCiRecord);
      intuneFilteredDevices = [...allIntuneDevices];
      applyActiveIntuneSearch();
      renderIntuneTable();
      if (SHARED.getActiveTab() === 'intune') SHARED.updateHeaderStat('intune');
      return;
    } catch (err) {
      console.warn('Live Intune API unavailable, falling back to static snapshot:', err);
    }

    // Fallback: static JSON snapshot (resilience only, not the authoritative source)
    const ts = Date.now();
    for (const path of [ENDPOINTS.INTUNE_SUMMARY, `/${ENDPOINTS.INTUNE_SUMMARY}`]) {
      try {
        const res = await fetch(`${path}?t=${ts}`);
        if (res.ok) {
          intuneData = await res.json();
          if (allIntuneDevices.length === 0 && intuneData.sample_devices) {
            allIntuneDevices = intuneData.sample_devices.map(normalizeLegacyDevice);
            intuneFilteredDevices = [...allIntuneDevices];
          }
          renderIntuneDashboard(intuneData);
          break;
        }
      } catch { /* try next fallback path */ }
    }
    for (const path of ['data/intune_ops_analytics.json', '/data/intune_ops_analytics.json']) {
      try {
        const res = await fetch(`${path}?t=${ts}`);
        if (res.ok) {
          const fullData = await res.json();
          if (fullData.devices && fullData.devices.length > 0) {
            allIntuneDevices = fullData.devices.map(normalizeLegacyDevice);
            applyActiveIntuneSearch();
            renderIntuneTable();
            if (SHARED.getActiveTab() === 'intune') SHARED.updateHeaderStat('intune');
          }
          break;
        }
      } catch { /* try next fallback path */ }
    }
  }

  function applyActiveIntuneSearch() {
    const searchInput = document.getElementById('deviceSearchInput');
    const q = searchInput ? searchInput.value.toLowerCase().trim() : '';
    intuneFilteredDevices = q ? filterIntuneDevices(q) : [...allIntuneDevices];
  }

  function filterIntuneDevices(q) {
    return allIntuneDevices.filter((d) =>
      (d.deviceName || '').toLowerCase().includes(q) ||
      (d.userPrincipalName || '').toLowerCase().includes(q) ||
      (d.serialNumber || '').toLowerCase().includes(q) ||
      (d.model || '').toLowerCase().includes(q) ||
      (d.operatingSystem || '').toLowerCase().includes(q) ||
      (d.complianceState || '').toLowerCase().includes(q) ||
      (d.manufacturer || '').toLowerCase().includes(q)
    );
  }

  function renderIntuneDashboard(data) {
    const metrics = data.metrics || {};
    const setElemText = (id, text) => {
      const elem = document.getElementById(id);
      if (elem) elem.textContent = text;
    };

    setElemText('kpiTotalDevices', Number(metrics.total_managed_devices || 25987).toLocaleString());
    setElemText('kpiCompliantCount', Number(metrics.compliant_devices || 21589).toLocaleString());
    setElemText('kpiNonCompliantCount', Number(metrics.noncompliant_devices ?? metrics.non_compliant_devices ?? 3422).toLocaleString());
    const compBreakdown = data.compliance_breakdown || {};
    setElemText('kpiCoManagedCount', Number(compBreakdown.configManager || 976).toLocaleString());

    const compTag = document.getElementById('kpiComplianceTag');
    if (compTag) compTag.textContent = `${metrics.compliance_rate_pct ?? '83.08'}%`;

    const storageElem = document.getElementById('kpiStoragePct');
    if (storageElem) storageElem.textContent = `${metrics.avg_storage_used_pct ?? '36.6'}%`;

    SHARED.updateHeaderStat(SHARED.getActiveTab());

    renderOsChart(data.os_breakdown || data.os_distribution || {});
    renderComplianceChart(compBreakdown);
    renderMfgChart(data.manufacturer_breakdown || data.vendor_distribution || {});

    renderIntuneTable();
  }

  function renderOsChart(osData) {
    const canvas = document.getElementById('osChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const filtered = Object.entries(osData || {}).filter(([k, v]) => k.trim() !== '' && v > 0);
    const labels = filtered.map(([k]) => k);
    const values = filtered.map(([, v]) => v);

    SHARED.destroyChartSafe(osChartInstance, canvas);
    osChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: { labels, datasets: [{ data: values, backgroundColor: ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6'], borderColor: '#141414', borderWidth: 2 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (event, elements) => {
          if (elements && elements.length > 0) {
            const selectedOS = labels[elements[0].index];
            const searchInput = document.getElementById('deviceSearchInput');
            if (searchInput && selectedOS) {
              searchInput.value = selectedOS;
              intuneCurrentPage = 1;
              intuneFilteredDevices = allIntuneDevices.filter((d) => (d.operatingSystem || '').toLowerCase().includes(selectedOS.toLowerCase()));
              renderIntuneTable();
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

  function renderComplianceChart(compData) {
    const canvas = document.getElementById('complianceChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const colorMap = { compliant: '#10B981', noncompliant: '#EF4444', configmanager: '#F59E0B', unknown: '#6B7280', ingraceperiod: '#3B82F6' };
    const orderedKeys = ['compliant', 'noncompliant', 'configManager', 'unknown', 'inGracePeriod'].filter((k) => k in (compData || {}));
    const labels = orderedKeys.map((k) => (k === 'configManager' ? 'ConfigManager' : k === 'inGracePeriod' ? 'InGracePeriod' : k.charAt(0).toUpperCase() + k.slice(1)));
    const values = orderedKeys.map((k) => compData[k]);
    const bgColors = orderedKeys.map((k) => colorMap[k.toLowerCase()] || '#6B7280');

    SHARED.destroyChartSafe(compChartInstance, canvas);
    compChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: { labels, datasets: [{ label: 'Devices', data: values, backgroundColor: bgColors, borderRadius: 6 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (event, elements) => {
          if (elements && elements.length > 0) {
            const selectedStatus = orderedKeys[elements[0].index];
            const searchInput = document.getElementById('deviceSearchInput');
            if (searchInput && selectedStatus) {
              searchInput.value = selectedStatus;
              intuneCurrentPage = 1;
              intuneFilteredDevices = allIntuneDevices.filter((d) => (d.complianceState || '').toLowerCase() === selectedStatus.toLowerCase());
              renderIntuneTable();
              searchInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
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

  function renderMfgChart(mfgData) {
    const canvas = document.getElementById('mfgChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const labels = Object.keys(mfgData);
    const values = Object.values(mfgData);

    SHARED.destroyChartSafe(mfgChartInstance, canvas);
    mfgChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'pie',
      data: { labels, datasets: [{ data: values, backgroundColor: ['#3B82F6', '#F97316', '#10B981', '#A855F7', '#6B7280'], borderColor: '#141414', borderWidth: 2 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (event, elements) => {
          if (elements && elements.length > 0) {
            const selectedVendor = labels[elements[0].index];
            const searchInput = document.getElementById('deviceSearchInput');
            if (searchInput && selectedVendor) {
              searchInput.value = selectedVendor;
              intuneCurrentPage = 1;
              intuneFilteredDevices = allIntuneDevices.filter((d) => (d.manufacturer || '').toLowerCase().includes(selectedVendor.toLowerCase()));
              renderIntuneTable();
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

  function renderIntuneTable() {
    const tbody = document.getElementById('deviceTableBody');
    const countSpan = document.getElementById('tableRecordCount');
    const paginationContainer = document.getElementById('intunePagination');
    if (!tbody) return;

    const totalCount = intuneFilteredDevices.length;
    if (totalCount === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-6">No matching endpoints found.</td></tr>`;
      if (countSpan) countSpan.textContent = 'Showing 0 matching endpoints';
      if (paginationContainer) paginationContainer.innerHTML = '';
      return;
    }

    const totalPages = Math.max(1, Math.ceil(totalCount / intunePageSize));
    if (intuneCurrentPage > totalPages) intuneCurrentPage = totalPages;
    if (intuneCurrentPage < 1) intuneCurrentPage = 1;

    const startIndex = (intuneCurrentPage - 1) * intunePageSize;
    const displayDevices = intuneFilteredDevices.slice(startIndex, Math.min(startIndex + intunePageSize, totalCount));

    tbody.innerHTML = displayDevices.map((d) => {
      const compLower = (d.complianceState || '').toLowerCase();
      const compClass = compLower === 'compliant' ? 'badge-success' : compLower === 'noncompliant' ? 'badge-danger' : 'badge-neutral';
      const usedPct = Number(d.usedStoragePct || 0);
      const progressColor = usedPct > 85 ? '#EF4444' : usedPct > 70 ? '#F59E0B' : '#10B981';
      const syncDate = d.lastSync ? new Date(d.lastSync).toLocaleString() : 'N/A';
      const devIdShort = (d.id || '').length > 8 ? `${d.id.substring(0, 8)}...` : (d.id || 'N/A');

      return `
        <tr>
          <td><div class="device-cell"><span class="device-name font-semibold text-white">${escapeHtml(d.deviceName)}</span><span class="device-id text-muted">${escapeHtml(devIdShort)}</span></div></td>
          <td><div class="os-badge"><span>${escapeHtml(d.operatingSystem)}</span><span class="text-muted text-xs">${escapeHtml(d.osVersion || 'N/A')}</span></div></td>
          <td class="text-light">${escapeHtml(d.userPrincipalName)}</td>
          <td><div class="mfg-cell"><span>${escapeHtml(d.manufacturer)}</span><span class="text-muted text-xs">${escapeHtml(d.model || 'N/A')}</span></div></td>
          <td class="font-mono text-xs">${escapeHtml(d.serialNumber || 'N/A')}</td>
          <td><span class="badge ${compClass}">${escapeHtml(d.complianceState)}</span></td>
          <td><div class="storage-progress"><div class="progress-bar-bg"><div class="progress-bar-fill" style="width: ${Math.min(usedPct, 100)}%; background-color: ${progressColor}"></div></div><span class="text-xs text-muted">${usedPct}% (${d.freeStorageGB || 0} GB free)</span></div></td>
          <td class="text-muted text-xs">${escapeHtml(syncDate)}</td>
        </tr>
      `;
    }).join('');

    SHARED.renderEnterprisePagination({
      container: paginationContainer,
      countLabel: countSpan,
      totalItems: totalCount,
      pageSize: intunePageSize,
      currentPage: intuneCurrentPage,
      pageSizeOptions: [10, 25, 50, 100],
      itemName: 'Endpoints',
      totalAuthoritative: allIntuneDevices.length,
      onPageChange: (newPage) => {
        intuneCurrentPage = newPage;
        renderIntuneTable();
        SHARED.resetTableScroll('view-intune');
      },
      onPageSizeChange: (newSize, newPage) => {
        intunePageSize = newSize;
        intuneCurrentPage = newPage;
        renderIntuneTable();
        SHARED.resetTableScroll('view-intune');
      },
    });
  }

  function initSearch() {
    const searchInput = document.getElementById('deviceSearchInput');
    if (!searchInput) return;
    searchInput.addEventListener('input', SHARED.debounce((e) => {
      const q = e.target.value.toLowerCase().trim();
      intuneCurrentPage = 1;
      intuneFilteredDevices = q ? filterIntuneDevices(q) : [...allIntuneDevices];
      renderIntuneTable();
    }, 200));
  }

  function exportCsv() {
    const link = document.createElement('a');
    link.setAttribute('href', 'exports/intune_devices_complete.csv');
    link.setAttribute('download', `intune_devices_complete_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  SHARED.registerDomain('intune', {
    pillElementId: 'tabPillIntune',
    pillSuffix: 'Endpoints',
    headerLabel: 'Total Verified Endpoints',
    getTotal: () => intuneData?.metrics?.total_managed_devices || (allIntuneDevices.length > 0 ? allIntuneDevices.length : intuneAuthoritativeTotal),
    isRendered: () => !!osChartInstance,
    getData: () => intuneData,
    renderDashboard: renderIntuneDashboard,
    renderTable: renderIntuneTable,
    resizeCharts: () => {
      if (osChartInstance) osChartInstance.resize();
      if (compChartInstance) compChartInstance.resize();
      if (mfgChartInstance) mfgChartInstance.resize();
    },
  });

  window.ITOM_INTUNE = { loadIntuneTelemetry, initSearch, exportCsv };
})();
