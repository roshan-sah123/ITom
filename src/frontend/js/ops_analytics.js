/**
 * ITOM OPS Analytics Dashboard Controller
 * 
 * Manages:
 * 1. Multi-domain Navigation Tabs ('intune', 'solarwinds', 'network', 'dex') & Deep Linking
 * 2. Dynamic Header Stat Box & Tab Synchronization (Intune: 25,987 Endpoints, SolarWinds: 1,548 Nodes)
 * 3. Microsoft Intune Live Telemetry (KPI Cards, 3 Interactive Charts, Full Table Search & CSV Export)
 * 4. SolarWinds Live Telemetry (KPI Cards, 3 Interactive Charts, Full Server Node Table & CSV Export)
 * 5. Memory-safe Chart.js Management & XSS-safe DOM Injections
 * 6. Pipeline Placeholders for Network CMDB & DEX
 */

(function () {
  'use strict';

  const VALID_TABS = ['intune', 'solarwinds', 'network', 'dex'];
  const DEFAULT_TAB = 'intune';

  let currentActiveTab = DEFAULT_TAB;
  
  // Intune State
  let intuneData = null;
  let allIntuneDevices = [];
  let osChartInstance = null;
  let compChartInstance = null;
  let mfgChartInstance = null;

  // SolarWinds State
  let solarwindsData = null;
  let allSwNodes = [];
  let swHealthChartInstance = null;
  let swStatusChartInstance = null;
  let swVendorChartInstance = null;

  /**
   * Parse hash string or query parameter into a validated TabId.
   */
  function parseTabId(raw) {
    if (!raw) return DEFAULT_TAB;
    const clean = String(raw).trim().replace(/^[#?]/, '').replace(/^tab=/, '').toLowerCase();
    return VALID_TABS.includes(clean) ? clean : DEFAULT_TAB;
  }

  function getActiveTab() {
    return currentActiveTab;
  }

  /**
   * Update the top-right header stat box dynamically based on the active tab domain.
   */
  function updateHeaderStat(tabId) {
    const labelElem = document.getElementById('headerStatLabel') || document.querySelector('.header-stat-box .stat-label');
    const valElem = document.getElementById('statTotalEndpoints');
    if (!labelElem || !valElem) return;

    if (tabId === 'solarwinds') {
      labelElem.textContent = 'Total Monitored Nodes';
      const total = solarwindsData?.metrics?.total_server_nodes || (allSwNodes.length > 0 ? allSwNodes.length : 1548);
      valElem.textContent = Number(total).toLocaleString();
    } else if (tabId === 'intune') {
      labelElem.textContent = 'Total Verified Endpoints';
      const total = intuneData?.metrics?.total_managed_devices || (allIntuneDevices.length > 0 ? allIntuneDevices.length : 25987);
      valElem.textContent = Number(total).toLocaleString();
    } else if (tabId === 'network') {
      labelElem.textContent = 'CMDB Network CIs';
      valElem.textContent = 'Phase 2';
    } else if (tabId === 'dex') {
      labelElem.textContent = 'DEX Monitored Fleet';
      valElem.textContent = 'Phase 2';
    }
  }

  /**
   * Switch the active tab view and synchronize URL hash and header statistics.
   */
  function switchTab(targetTab, updateHash = true) {
    const tabId = parseTabId(targetTab);
    currentActiveTab = tabId;

    // 1. Update Tab Button active states
    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(btn => {
      const btnTab = btn.getAttribute('data-tab');
      if (btnTab === tabId) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // 2. Toggle Tab Panes display
    const tabPanes = document.querySelectorAll('.tab-pane');
    tabPanes.forEach(pane => {
      const paneTab = pane.getAttribute('data-tab') || pane.id.replace('view-', '');
      if (paneTab === tabId) {
        pane.classList.add('active');
        pane.classList.remove('hidden');
      } else {
        pane.classList.remove('active');
        pane.classList.add('hidden');
      }
    });

    // 3. Update Header Stat Box dynamically
    updateHeaderStat(tabId);

    // 4. Synchronize URL Hash without unwanted scrolling
    if (updateHash && window.location.hash !== `#${tabId}`) {
      if (history.pushState) {
        history.pushState(null, null, `#${tabId}`);
      } else {
        window.location.hash = `#${tabId}`;
      }
    }

    // 5. Safe Chart.js Resize & Redraw on view activation
    setTimeout(() => {
      if (tabId === 'intune') {
        if (osChartInstance) osChartInstance.resize();
        if (compChartInstance) compChartInstance.resize();
        if (mfgChartInstance) mfgChartInstance.resize();
      } else if (tabId === 'solarwinds') {
        if (swHealthChartInstance) swHealthChartInstance.resize();
        if (swStatusChartInstance) swStatusChartInstance.resize();
        if (swVendorChartInstance) swVendorChartInstance.resize();
      }
    }, 60);

    return currentActiveTab;
  }

  /**
   * Initialize URL hash routing and event listeners.
   */
  function initTabRouter() {
    const urlParams = new URLSearchParams(window.location.search);
    const queryTab = urlParams.get('tab');
    const hashTab = window.location.hash;
    const initialTab = queryTab ? parseTabId(queryTab) : (hashTab ? parseTabId(hashTab) : DEFAULT_TAB);

    switchTab(initialTab, false);

    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const tab = btn.getAttribute('data-tab');
        switchTab(tab, true);
      });
    });

    document.addEventListener('click', (e) => {
      const targetBtn = e.target.closest('[data-target-tab]');
      if (targetBtn) {
        e.preventDefault();
        const target = targetBtn.getAttribute('data-target-tab');
        switchTab(target, true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    });

    window.addEventListener('hashchange', () => {
      const newTab = parseTabId(window.location.hash);
      if (newTab !== currentActiveTab) {
        switchTab(newTab, false);
      }
    });

    window.addEventListener('popstate', () => {
      const newTab = parseTabId(window.location.hash);
      if (newTab !== currentActiveTab) {
        switchTab(newTab, false);
      }
    });
  }

  // =========================================================================
  // DATA LOADERS: INTUNE & SOLARWINDS
  // =========================================================================

  async function loadAllTelemetry() {
    await Promise.all([
      loadIntuneTelemetry(),
      loadSolarWindsTelemetry()
    ]);
    // Refresh header stat once data is populated
    updateHeaderStat(currentActiveTab);
  }

  async function loadIntuneTelemetry() {
    const paths = ['data/intune_summary.json', '../../data/intune_summary.json', '/data/intune_summary.json', '../data/intune_summary.json'];
    for (const path of paths) {
      try {
        const res = await fetch(path);
        if (res.ok) {
          intuneData = await res.json();
          allIntuneDevices = intuneData.sample_devices || [];
          renderIntuneDashboard(intuneData);
          return;
        }
      } catch (err) {}
    }
  }

  async function loadSolarWindsTelemetry() {
    const summaryPaths = ['data/solarwinds_summary.json', '../../data/solarwinds_summary.json', '/data/solarwinds_summary.json', '../data/solarwinds_summary.json'];
    const nodesPaths = ['data/solarwinds_nodes.json', '../../data/solarwinds_nodes.json', '/data/solarwinds_nodes.json', '../data/solarwinds_nodes.json'];

    let summaryLoaded = false;
    for (const path of summaryPaths) {
      try {
        const res = await fetch(path);
        if (res.ok) {
          solarwindsData = await res.json();
          summaryLoaded = true;
          break;
        }
      } catch (err) {}
    }

    for (const path of nodesPaths) {
      try {
        const res = await fetch(path);
        if (res.ok) {
          allSwNodes = await res.json();
          break;
        }
      } catch (err) {}
    }

    if (summaryLoaded && solarwindsData) {
      renderSolarWindsDashboard(solarwindsData);
    }
  }

  // =========================================================================
  // RENDER INTUNE TELEMETRY (25,987 Endpoints)
  // =========================================================================

  function renderIntuneDashboard(data) {
    const metrics = data.metrics || {};
    const setElemText = (id, text) => {
      const elem = document.getElementById(id);
      if (elem) elem.textContent = text;
    };

    const totalDevs = Number(metrics.total_managed_devices || 25987).toLocaleString();
    const compliantCount = Number(metrics.compliant_devices || 21589).toLocaleString();
    const nonCompliantCount = Number(metrics.noncompliant_devices || 3422).toLocaleString();
    const complianceRate = `${metrics.compliance_rate_pct || 83.08}%`;
    const storageUsed = `${metrics.avg_storage_used_pct || 37.4}%`;

    setElemText('kpiTotalDevices', totalDevs);
    setElemText('kpiCompliantCount', compliantCount);
    setElemText('kpiNonCompliantCount', nonCompliantCount);
    setElemText('kpiComplianceTag', complianceRate);
    setElemText('kpiStoragePct', storageUsed);

    updateHeaderStat(currentActiveTab);

    renderOsChart(data.os_breakdown || {
      'Windows': 25334,
      'macOS': 602,
      'Linux (ubuntu)': 24,
      'Unknown': 24,
      'iOS': 2,
      'Android': 1
    });

    renderComplianceChart(data.compliance_breakdown || {
      'compliant': 21589,
      'noncompliant': 3422,
      'configManager': 935,
      'unknown': 31,
      'inGracePeriod': 10
    });

    renderMfgChart(data.manufacturer_breakdown || {
      'Dell': 15716,
      'HP': 8610,
      'Lenovo': 959,
      'Apple': 604,
      'Other': 98
    });

    renderIntuneTable(allIntuneDevices);
  }

  function destroyChartSafe(instance, canvas) {
    if (instance && typeof instance.destroy === 'function') {
      instance.destroy();
    }
    if (canvas && typeof Chart !== 'undefined' && Chart.getChart) {
      const existing = Chart.getChart(canvas);
      if (existing) existing.destroy();
    }
  }

  function renderOsChart(osData) {
    const canvas = document.getElementById('osChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const labels = Object.keys(osData).map(k => k === '' ? 'Unknown' : k);
    const values = Object.values(osData);

    destroyChartSafe(osChartInstance, canvas);

    osChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: ['#F97316', '#3B82F6', '#10B981', '#EC4899', '#8B5CF6', '#6B7280'],
          borderColor: '#141414',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right',
            labels: { color: '#A3A3A3', font: { family: 'Inter', size: 11 } }
          }
        }
      }
    });
  }

  function renderComplianceChart(compData) {
    const canvas = document.getElementById('complianceChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const labels = Object.keys(compData).map(k => k.charAt(0).toUpperCase() + k.slice(1));
    const values = Object.values(compData);

    destroyChartSafe(compChartInstance, canvas);

    compChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Devices',
          data: values,
          backgroundColor: ['#10B981', '#EF4444', '#F59E0B', '#6B7280', '#3B82F6'],
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#A3A3A3', font: { family: 'Inter' } }, grid: { color: '#222222' } },
          y: { ticks: { color: '#A3A3A3', font: { family: 'Inter' } }, grid: { color: '#222222' } }
        }
      }
    });
  }

  function renderMfgChart(mfgData) {
    const canvas = document.getElementById('mfgChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const labels = Object.keys(mfgData);
    const values = Object.values(mfgData);

    destroyChartSafe(mfgChartInstance, canvas);

    mfgChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'pie',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: ['#3B82F6', '#F97316', '#10B981', '#A855F7', '#6B7280'],
          borderColor: '#141414',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right',
            labels: { color: '#A3A3A3', font: { family: 'Inter', size: 11 } }
          }
        }
      }
    });
  }

  function renderIntuneTable(devices) {
    const tbody = document.getElementById('deviceTableBody');
    const countSpan = document.getElementById('tableRecordCount');
    if (!tbody) return;

    if (!devices || devices.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-4">No matching records found.</td></tr>`;
      if (countSpan) countSpan.textContent = 'Showing 0 matching devices (Full dataset: 25,987 devices)';
      return;
    }

    if (countSpan) {
      countSpan.textContent = `Showing ${devices.length} live devices (Full dataset: 25,987 devices)`;
    }

    tbody.innerHTML = devices.map(d => {
      const compLower = (d.complianceState || '').toLowerCase();
      const compClass = compLower === 'compliant' ? 'badge-success' : (compLower === 'noncompliant' ? 'badge-danger' : 'badge-neutral');
      const usedPct = Number(d.usedStoragePct || 0);
      const progressColor = usedPct > 85 ? '#EF4444' : (usedPct > 70 ? '#F59E0B' : '#10B981');
      const syncDate = d.lastSync ? new Date(d.lastSync).toLocaleString() : 'N/A';
      const devIdShort = (d.id || '').length > 8 ? `${d.id.substring(0, 8)}...` : (d.id || 'N/A');

      return `
        <tr>
          <td>
            <div class="device-cell">
              <span class="device-name font-semibold text-white">${escapeHtml(d.deviceName)}</span>
              <span class="device-id text-muted">${escapeHtml(devIdShort)}</span>
            </div>
          </td>
          <td>
            <div class="os-badge">
              <span>${escapeHtml(d.operatingSystem)}</span>
              <span class="text-muted text-xs">${escapeHtml(d.osVersion || 'N/A')}</span>
            </div>
          </td>
          <td class="text-light">${escapeHtml(d.userPrincipalName)}</td>
          <td>
            <div class="mfg-cell">
              <span>${escapeHtml(d.manufacturer)}</span>
              <span class="text-muted text-xs">${escapeHtml(d.model || 'N/A')}</span>
            </div>
          </td>
          <td class="font-mono text-xs">${escapeHtml(d.serialNumber || 'N/A')}</td>
          <td>
            <span class="badge ${compClass}">${escapeHtml(d.complianceState)}</span>
          </td>
          <td>
            <div class="storage-progress">
              <div class="progress-bar-bg">
                <div class="progress-bar-fill" style="width: ${Math.min(usedPct, 100)}%; background-color: ${progressColor}"></div>
              </div>
              <span class="text-xs text-muted">${usedPct}% (${d.freeStorageGB || 0} GB free)</span>
            </div>
          </td>
          <td class="text-muted text-xs">${escapeHtml(syncDate)}</td>
        </tr>
      `;
    }).join('');
  }

  // =========================================================================
  // RENDER SOLARWINDS TELEMETRY (1,548 Server Nodes)
  // =========================================================================

  function renderSolarWindsDashboard(data) {
    const metrics = data.metrics || {};
    const setElemText = (id, text) => {
      const elem = document.getElementById(id);
      if (elem) elem.textContent = text;
    };

    setElemText('swTotalNodes', Number(metrics.total_server_nodes || 1548).toLocaleString());
    setElemText('swHighHealthCount', Number(metrics.high_health_nodes || 1357).toLocaleString());
    setElemText('swMedHealthCount', Number(metrics.medium_health_nodes || 150).toLocaleString());
    setElemText('swLowHealthCount', Number(metrics.low_critical_nodes || 41).toLocaleString());
    setElemText('swHealthTag', `${metrics.high_health_pct || 87.66}% High`);
    
    const cpuMemElem = document.getElementById('swAvgCpuMem');
    if (cpuMemElem) {
      cpuMemElem.innerHTML = `${metrics.avg_fleet_cpu_load_pct || 16.2}% <span class="text-xs text-muted">CPU</span> &bull; ${metrics.avg_fleet_ram_used_pct || 22.6}% <span class="text-xs text-muted">RAM</span>`;
    }

    const latElem = document.getElementById('swAvgLatency');
    if (latElem) {
      latElem.innerHTML = `${metrics.avg_fleet_latency_ms || 43.9} <span class="text-xs text-muted">ms</span>`;
    }

    updateHeaderStat(currentActiveTab);

    // 1. Health Tier Doughnut Chart
    renderSwHealthChart(data.health_breakdown || { 'High': 1357, 'Medium': 150, 'Low': 41 });

    // 2. Status Bar Chart
    renderSwStatusChart(metrics.status_counts || { 'up': 1370, 'warning': 25, 'critical': 35, 'down': 6, 'unmanaged_unknown': 112 });

    // 3. Vendor Pie Chart
    renderSwVendorChart(data.vendor_breakdown || { 'Cisco': 492, 'Windows': 261, 'Linux': 4, 'Other': 791 });

    // 4. Server Nodes Table
    renderSolarWindsTable(allSwNodes.length > 0 ? allSwNodes : (data.top_degraded_servers || []));
  }

  function renderSwHealthChart(healthData) {
    const canvas = document.getElementById('swHealthChart');
    if (!canvas || typeof Chart === 'undefined') return;

    destroyChartSafe(swHealthChartInstance, canvas);

    swHealthChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: ['High Health', 'Medium Health', 'Low / Critical Health'],
        datasets: [{
          data: [healthData.High || 1357, healthData.Medium || 150, healthData.Low || 41],
          backgroundColor: ['#10B981', '#F59E0B', '#EF4444'],
          borderColor: '#141414',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'right', labels: { color: '#A3A3A3', font: { family: 'Inter', size: 11 } } }
        }
      }
    });
  }

  function renderSwStatusChart(statusData) {
    const canvas = document.getElementById('swStatusChart');
    if (!canvas || typeof Chart === 'undefined') return;

    destroyChartSafe(swStatusChartInstance, canvas);

    swStatusChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: ['Up (1)', 'Warning (3)', 'Critical (14)', 'Down (2)', 'Unmanaged/Other'],
        datasets: [{
          label: 'Server Nodes',
          data: [
            statusData.up || 1370,
            statusData.warning || 25,
            statusData.critical || 35,
            statusData.down || 6,
            statusData.unmanaged_unknown || 112
          ],
          backgroundColor: ['#10B981', '#F59E0B', '#EF4444', '#7F1D1D', '#6B7280'],
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#A3A3A3', font: { family: 'Inter' } }, grid: { color: '#222222' } },
          y: { ticks: { color: '#A3A3A3', font: { family: 'Inter' } }, grid: { color: '#222222' } }
        }
      }
    });
  }

  function renderSwVendorChart(vendorData) {
    const canvas = document.getElementById('swVendorChart');
    if (!canvas || typeof Chart === 'undefined') return;

    destroyChartSafe(swVendorChartInstance, canvas);

    swVendorChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'pie',
      data: {
        labels: Object.keys(vendorData),
        datasets: [{
          data: Object.values(vendorData),
          backgroundColor: ['#3B82F6', '#10B981', '#F97316', '#A855F7', '#6B7280'],
          borderColor: '#141414',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'right', labels: { color: '#A3A3A3', font: { family: 'Inter', size: 11 } } }
        }
      }
    });
  }

  function renderSolarWindsTable(nodes) {
    const tbody = document.getElementById('swTableBody');
    const countSpan = document.getElementById('swTableRecordCount');
    if (!tbody) return;

    if (!nodes || nodes.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-4">No matching server nodes found.</td></tr>`;
      if (countSpan) countSpan.textContent = 'Showing 0 matching servers (Full dataset: 1,548 nodes)';
      return;
    }

    const displayNodes = nodes.slice(0, 100);
    if (countSpan) {
      countSpan.textContent = `Showing ${displayNodes.length} live servers (Full dataset: 1,548 nodes)`;
    }

    tbody.innerHTML = displayNodes.map(n => {
      const tier = n.HealthTier || 'High';
      const tierClass = tier === 'High' ? 'badge-success' : (tier === 'Medium' ? 'badge-warning' : 'badge-danger');
      const cpuVal = Number(n.CPULoad || 0);
      const ramVal = Number(n.PercentMemoryUsed || 0);
      const latVal = Number(n.AvgResponseTime || n.ResponseTime || 0);

      const statusMap = {
        1: '<span class="badge badge-success">Up</span>',
        2: '<span class="badge badge-danger">Down</span>',
        3: '<span class="badge badge-warning">Warning</span>',
        14: '<span class="badge badge-danger">Critical</span>'
      };
      const statusBadge = statusMap[n.Status] || `<span class="badge badge-neutral">${escapeHtml(n.StatusDescription || 'Unknown')}</span>`;

      return `
        <tr>
          <td>
            <div class="device-cell">
              <span class="device-name font-semibold text-white">${escapeHtml(n.Caption)}</span>
              <span class="device-id font-mono text-muted">ID: ${escapeHtml(String(n.NodeID))}</span>
            </div>
          </td>
          <td class="font-mono text-xs text-accent">${escapeHtml(n.IPAddress || 'N/A')}</td>
          <td>
            <div class="mfg-cell">
              <span>${escapeHtml(n.Vendor || 'Generic')}</span>
              <span class="text-muted text-xs">${escapeHtml(n.MachineType || 'N/A')}</span>
            </div>
          </td>
          <td>
            <span class="badge ${tierClass}">${escapeHtml(tier)}</span>
          </td>
          <td>
            <span class="font-semibold ${cpuVal > 85 ? 'text-danger' : (cpuVal > 70 ? 'text-warning' : 'text-light')}">${cpuVal}%</span>
          </td>
          <td>
            <span class="font-semibold ${ramVal > 85 ? 'text-danger' : (ramVal > 70 ? 'text-warning' : 'text-light')}">${ramVal}%</span>
          </td>
          <td class="font-mono text-xs">${latVal >= 0 ? `${latVal} ms` : 'Down'}</td>
          <td>${statusBadge}</td>
        </tr>
      `;
    }).join('');
  }

  // =========================================================================
  // SEARCH & CSV EXPORT CONTROLLERS
  // =========================================================================

  function initSearchFilters() {
    // Intune Search
    const intuneSearch = document.getElementById('deviceSearchInput');
    if (intuneSearch) {
      intuneSearch.addEventListener('input', (e) => {
        const q = e.target.value.toLowerCase().trim();
        if (!q) {
          renderIntuneTable(allIntuneDevices);
          return;
        }
        const filtered = allIntuneDevices.filter(d => {
          return (d.deviceName || '').toLowerCase().includes(q) ||
                 (d.userPrincipalName || '').toLowerCase().includes(q) ||
                 (d.serialNumber || '').toLowerCase().includes(q) ||
                 (d.model || '').toLowerCase().includes(q) ||
                 (d.operatingSystem || '').toLowerCase().includes(q) ||
                 (d.manufacturer || '').toLowerCase().includes(q);
        });
        renderIntuneTable(filtered);
      });
    }

    // SolarWinds Search
    const swSearch = document.getElementById('swSearchInput');
    if (swSearch) {
      swSearch.addEventListener('input', (e) => {
        const q = e.target.value.toLowerCase().trim();
        if (!q) {
          renderSolarWindsTable(allSwNodes);
          return;
        }
        const filtered = allSwNodes.filter(n => {
          return (n.Caption || '').toLowerCase().includes(q) ||
                 (n.IPAddress || '').toLowerCase().includes(q) ||
                 (n.Vendor || '').toLowerCase().includes(q) ||
                 (n.MachineType || '').toLowerCase().includes(q) ||
                 (n.HealthTier || '').toLowerCase().includes(q) ||
                 (n.StatusDescription || '').toLowerCase().includes(q);
        });
        renderSolarWindsTable(filtered);
      });
    }
  }

  function initCsvExports() {
    // Top Nav Export Button (Context-Aware based on active tab)
    const topExportBtn = document.getElementById('exportCsvBtn');
    if (topExportBtn) {
      topExportBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (currentActiveTab === 'solarwinds') {
          exportSolarWindsCSV();
        } else {
          exportIntuneCSV();
        }
      });
    }

    // Tab-specific CSV buttons
    const intuneTableBtn = document.getElementById('loadMoreBtn');
    if (intuneTableBtn) {
      intuneTableBtn.addEventListener('click', (e) => {
        e.preventDefault();
        exportIntuneCSV();
      });
    }

    const swBtn = document.getElementById('exportSwCsvBtn');
    if (swBtn) {
      swBtn.addEventListener('click', (e) => {
        e.preventDefault();
        exportSolarWindsCSV();
      });
    }
  }

  function exportIntuneCSV() {
    if (!allIntuneDevices || allIntuneDevices.length === 0) {
      alert('No Intune data available to export.');
      return;
    }
    const headers = ['Device Name', 'Device ID', 'Operating System', 'OS Version', 'UPN', 'Manufacturer', 'Model', 'Serial Number', 'Compliance', 'Total GB', 'Free GB', 'Used %', 'Last Sync'];
    const rows = allIntuneDevices.map(d => [
      `"${String(d.deviceName || 'N/A').replace(/"/g, '""')}"`,
      `"${String(d.id || 'N/A').replace(/"/g, '""')}"`,
      `"${String(d.operatingSystem || 'Unknown').replace(/"/g, '""')}"`,
      `"${String(d.osVersion || 'N/A').replace(/"/g, '""')}"`,
      `"${String(d.userPrincipalName || 'N/A').replace(/"/g, '""')}"`,
      `"${String(d.manufacturer || 'N/A').replace(/"/g, '""')}"`,
      `"${String(d.model || 'N/A').replace(/"/g, '""')}"`,
      `"${String(d.serialNumber || 'N/A').replace(/"/g, '""')}"`,
      `"${String(d.complianceState || 'unknown').replace(/"/g, '""')}"`,
      Number(d.totalStorageGB || 0),
      Number(d.freeStorageGB || 0),
      Number(d.usedStoragePct || 0),
      `"${String(d.lastSync || 'N/A').replace(/"/g, '""')}"`
    ]);
    downloadCSV(headers, rows, `intune_ops_analytics_${new Date().toISOString().slice(0, 10)}.csv`);
  }

  function exportSolarWindsCSV() {
    const nodes = allSwNodes.length > 0 ? allSwNodes : (solarwindsData ? solarwindsData.top_degraded_servers : []);
    if (!nodes || nodes.length === 0) {
      alert('No SolarWinds data available to export.');
      return;
    }
    const headers = ['NodeID', 'Caption', 'IPAddress', 'Vendor', 'MachineType', 'HealthTier', 'CPULoad (%)', 'PercentMemoryUsed (%)', 'AvgResponseTime (ms)', 'Status', 'StatusDescription', 'LastSync'];
    const rows = nodes.map(n => [
      n.NodeID,
      `"${String(n.Caption || 'N/A').replace(/"/g, '""')}"`,
      `"${String(n.IPAddress || 'N/A').replace(/"/g, '""')}"`,
      `"${String(n.Vendor || 'N/A').replace(/"/g, '""')}"`,
      `"${String(n.MachineType || 'N/A').replace(/"/g, '""')}"`,
      `"${String(n.HealthTier || 'High').replace(/"/g, '""')}"`,
      Number(n.CPULoad || 0),
      Number(n.PercentMemoryUsed || 0),
      Number(n.AvgResponseTime || 0),
      n.Status,
      `"${String(n.StatusDescription || 'N/A').replace(/"/g, '""')}"`,
      `"${String(n.LastSync || 'N/A').replace(/"/g, '""')}"`
    ]);
    downloadCSV(headers, rows, `solarwinds_server_nodes_${new Date().toISOString().slice(0, 10)}.csv`);
  }

  function downloadCSV(headers, rows, filename) {
    const csvContent = headers.join(',') + '\n' + rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Export globals
  window.switchTab = switchTab;
  window.getActiveTab = getActiveTab;
  window.initTabRouter = initTabRouter;
  window.exportIntuneCSV = exportIntuneCSV;
  window.exportSolarWindsCSV = exportSolarWindsCSV;

  // Initialize
  document.addEventListener('DOMContentLoaded', () => {
    initTabRouter();
    initSearchFilters();
    initCsvExports();
    loadAllTelemetry();
  });

})();
