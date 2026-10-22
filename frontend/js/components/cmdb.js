/**
 * Source-record inventory with verified Intune and SolarWinds accounting.
 */
import { itomApi } from '../api.js?v=6';
import { formatNumber, formatPercent, escapeHtml, calculateNewPageAnchor, debounce, exportToCsv, fetchAllFilteredRows, generatePaginationControls } from '../utils.js';
import { openCiDrawer } from './drawer.js?v=4';

let currentCmdbPage = 1;
let currentCmdbPageSize = 25;
let activeCmdbSearch = '';
let activeCmdbSource = '';
let activeCmdbHealth = '';
let activeCmdbLocation = '';
let activeCmdbFilterLabel = '';

let allFetchedCis = [];
let cachedTotalCis = 0;
let globalSearchInitialized = false;
let cmdbFiltersInitialized = false;
const healthLabel = tier => ['High', 'Medium', 'Low'].find(label => label.toLowerCase() === String(tier || '').toLowerCase()) || 'Unknown';

export async function renderCmdb() {
  await loadCmdbKpis();
  await loadCmdbGrid();
  initCmdbFilters();
  initCmdbGlobalSearch();
}

function initCmdbGlobalSearch() {
  if (globalSearchInitialized) return;
  globalSearchInitialized = true;
  document.addEventListener('itom:global-search', (e) => {
    const query = e.detail?.query || '';
    activeCmdbSearch = query.trim();
    const searchInput = document.getElementById('cmdbSearchInput');
    if (searchInput) searchInput.value = activeCmdbSearch;
    activeCmdbFilterLabel = activeCmdbSearch ? `Search: "${activeCmdbSearch}"` : '';
    updateCmdbFilterBanner();
    currentCmdbPage = 1;
    loadCmdbGrid();
  });
}

async function loadCmdbKpis() {
  try {
    const summary = await itomApi.getCmdbSummary();
    setCmdbCounts(renderCmdbProvenance(summary));
  } catch (err) {
    console.error('Failed to load CMDB summary:', err);
    renderCmdbProvenance(null);
    setCmdbCounts(null);
  }
}

function setCmdbCounts(counts) {
  cachedTotalCis = counts?.total ?? 0;
  for (const [id, value] of [
    ['cmdbTotalCisVal', counts?.total],
    ['cmdbIntuneProvVal', counts?.intune],
    ['cmdbSwProvVal', counts?.solarwinds],
  ]) {
    const element = document.getElementById(id);
    if (element) element.textContent = value == null ? 'Unavailable' : formatNumber(value);
  }
}

function sourceCounts(summary) {
  if (!summary || summary.data_available === false) return null;
  const values = [summary.total_cis, summary.total_endpoints, summary.total_servers,
    summary.total_network_devices, summary.total_unclassified];
  // Null and omitted counts are not evidence of zero records.
  if (!values.every(value => Number.isSafeInteger(value) && value >= 0)) return null;
  const [total, intune, servers, network, unclassified] = values;
  const solarwinds = servers + network + unclassified;
  return intune + solarwinds === total ? { total, intune, solarwinds } : null;
}

function renderCmdbProvenance(summary) {
  const bar = document.getElementById('cmdbProvenanceBar');
  const intuneBar = document.getElementById('cmdbProvenanceIntuneBar');
  const solarWindsBar = document.getElementById('cmdbProvenanceSolarWindsBar');
  const intuneLabel = document.getElementById('cmdbProvenanceIntuneLabel');
  const solarWindsLabel = document.getElementById('cmdbProvenanceSolarWindsLabel');
  const status = document.getElementById('cmdbProvenanceStatus');
  const counts = sourceCounts(summary);
  if (!bar || !intuneBar || !solarWindsBar || !intuneLabel || !solarWindsLabel || !status) return counts;

  if (!counts) {
    bar.dataset.status = 'unavailable';
    bar.setAttribute('aria-label', 'Source distribution unavailable');
    intuneBar.style.width = '0%';
    solarWindsBar.style.width = '0%';
    intuneLabel.textContent = 'Microsoft Intune: Unavailable';
    solarWindsLabel.textContent = 'SolarWinds Orion: Unavailable';
    status.textContent = 'Source counts could not be verified. Reload snapshot to try again.';
    return null;
  }

  const intunePct = counts.total ? (counts.intune / counts.total) * 100 : 0;
  const solarWindsPct = counts.total ? (counts.solarwinds / counts.total) * 100 : 0;
  bar.dataset.status = counts.total ? 'snapshot' : 'empty';
  bar.setAttribute('aria-label', counts.total
    ? `Stored source distribution: ${formatNumber(counts.total)} records; Microsoft Intune ${formatPercent(intunePct, 1)}; SolarWinds Orion ${formatPercent(solarWindsPct, 1)}`
    : 'No stored source records');
  intuneBar.style.width = `${intunePct}%`;
  solarWindsBar.style.width = `${solarWindsPct}%`;
  intuneLabel.textContent = `Microsoft Intune: ${formatNumber(counts.intune)} records (${formatPercent(intunePct, 1)})`;
  solarWindsLabel.textContent = `SolarWinds Orion: ${formatNumber(counts.solarwinds)} records (${formatPercent(solarWindsPct, 1)})`;
  status.textContent = counts.total
    ? `Source totals verified: ${formatNumber(counts.intune)} Intune + ${formatNumber(counts.solarwinds)} SolarWinds = ${formatNumber(counts.total)} source records.`
    : 'No stored source records in this snapshot.';
  return counts;
}

function updateCmdbFilterBanner() {
  const banner = document.getElementById('cmdbActiveFilterBanner');
  const labelEl = document.getElementById('cmdbActiveFilterLabel');
  if (!banner || !labelEl) return;

  if (activeCmdbFilterLabel) {
    labelEl.textContent = activeCmdbFilterLabel;
    banner.style.display = 'flex';
  } else {
    banner.style.display = 'none';
  }
}

async function loadCmdbGrid() {
  const tbody = document.getElementById('cmdbTableBody');
  const countEl = document.getElementById('cmdbRecordCount');
  const tableContainer = document.querySelector('#view-cmdb .grid-scroll');
  const paginationControls = document.getElementById('cmdbPaginationControls');
  if (!tbody) return;

  try {
    const params = {
      page: currentCmdbPage,
      page_size: currentCmdbPageSize,
      ...(activeCmdbSearch ? { search: activeCmdbSearch } : {}),
      ...(activeCmdbSource ? { source_system: activeCmdbSource } : {}),
      ...(activeCmdbHealth ? { health_tier: activeCmdbHealth } : {}),
      ...(activeCmdbLocation ? { location: activeCmdbLocation } : {}),
    };

    const res = await itomApi.getCmdbCis(params);
    const data = res.data || res;
    allFetchedCis = data.items || [];

    const totalRecords = data.total !== undefined ? data.total : (data.pagination?.total_records || cachedTotalCis);
    const totalPages = Math.max(1, Math.ceil(totalRecords / currentCmdbPageSize));

    currentCmdbPage = Math.min(currentCmdbPage, totalPages);
    const startRecord = totalRecords > 0 ? (currentCmdbPage - 1) * currentCmdbPageSize + 1 : 0;
    const endRecord = totalRecords > 0 ? Math.min(startRecord + allFetchedCis.length - 1, totalRecords) : 0;

    if (countEl) {
      countEl.textContent = `Showing ${formatNumber(startRecord)}–${formatNumber(endRecord)} of ${formatNumber(totalRecords)} Configuration Items`;
    }

    if (!allFetchedCis.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 32px; color: #6B7280;">No Configuration Items matching query criteria.</td></tr>`;
      if (paginationControls) paginationControls.innerHTML = '';
      return;
    }

    tbody.innerHTML = allFetchedCis.map((ci, idx) => {
      const healthTier = healthLabel(ci.health_tier);
      const healthClass = { High: 'healthy', Medium: 'warning', Low: 'critical' }[healthTier] || 'unknown';
      const isSw = (ci.source_system || '').toUpperCase() === 'SOLARWINDS';

      return `
        <tr>
          <td><button type="button" class="ci-name-link" data-ci-idx="${idx}" title="Open CI details drawer">${escapeHtml(ci.name)}</button></td>
          <td>
            <span class="status-pill" style="background: ${isSw ? 'rgba(245, 158, 11, 0.1)' : 'rgba(59, 130, 246, 0.1)'}; color: ${isSw ? '#F59E0B' : '#3B82F6'}; border: 1px solid ${isSw ? 'rgba(245, 158, 11, 0.3)' : 'rgba(59, 130, 246, 0.3)'};">
              ${escapeHtml(ci.source_system)}
            </span>
          </td>
          <td class="source-name">${escapeHtml(isSw ? ci.source_category ?? 'Unclassified' : ci.ci_type || 'Unavailable')}</td>
          <td>${escapeHtml(ci.vendor || 'Unavailable')}</td>
          <td>${escapeHtml(ci.location || 'Unassigned')}</td>
          <td><span class="status-pill status-${healthClass}">${escapeHtml(healthTier)}</span></td>
          <td class="font-mono">${escapeHtml(ci.serial_number || 'N/A')}</td>
        </tr>
      `;
    }).join('');

    tbody.querySelectorAll('.ci-name-link').forEach(link => {
      link.addEventListener('click', () => {
        const idx = parseInt(link.dataset.ciIdx, 10);
        if (allFetchedCis[idx]) {
          openCiDrawer(allFetchedCis[idx]);
        }
      });
    });

    if (tableContainer) tableContainer.scrollTop = 0;

    // Smart pagination controls
    generatePaginationControls(paginationControls, currentCmdbPage, totalPages, (newPage) => {
      currentCmdbPage = newPage;
      loadCmdbGrid();
    });

  } catch (err) {
    console.error('Failed to load CMDB grid:', err);
    tbody.innerHTML = `<tr><td colspan="7" class="inline-error">Assets Analytics inventory unavailable.</td></tr>`;
  }
}

function initCmdbFilters() {
  if (cmdbFiltersInitialized) return;
  cmdbFiltersInitialized = true;
  const sourceSelect = document.getElementById('cmdbFilterSource');
  const healthSelect = document.getElementById('cmdbFilterHealth');
  const searchInput = document.getElementById('cmdbSearchInput');
  const locationSelect = document.getElementById('cmdbLocationSelect');
  const pageSizeSelect = document.getElementById('cmdbPageSizeSelect');
  const resetBtn = document.getElementById('cmdbResetFilters');
  const clearFilterBtn = document.getElementById('cmdbClearActiveFilterBtn');
  const exportBtn = document.getElementById('cmdbExportCsv');

  if (sourceSelect) {
    sourceSelect.value = activeCmdbSource;
    sourceSelect.addEventListener('change', (e) => {
      activeCmdbSource = e.target.value;
      activeCmdbFilterLabel = activeCmdbSource ? `Source: ${activeCmdbSource}` : '';
      updateCmdbFilterBanner();
      currentCmdbPage = 1;
      loadCmdbGrid();
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', debounce((e) => {
      activeCmdbSearch = e.target.value.trim();
      activeCmdbFilterLabel = activeCmdbSearch ? `Search: "${activeCmdbSearch}"` : '';
      updateCmdbFilterBanner();
      currentCmdbPage = 1;
      loadCmdbGrid();
    }, 250));
  }

  if (healthSelect) {
    healthSelect.addEventListener('change', (e) => {
      activeCmdbHealth = e.target.value;
      activeCmdbFilterLabel = activeCmdbHealth ? `Health: ${activeCmdbHealth}` : '';
      updateCmdbFilterBanner();
      currentCmdbPage = 1;
      loadCmdbGrid();
    });
  }

  if (locationSelect) {
    itomApi.getSolarWindsSites().then(response => {
      const sites = response?.data?.items || [];
      locationSelect.innerHTML = '<option value="">Location (All)</option>' + sites
        .map(site => `<option value="${escapeHtml(site.name)}">${escapeHtml(site.name)} (${site.total_nodes ?? 0})</option>`)
        .join('');
      locationSelect.value = activeCmdbLocation;
    }).catch(() => {});
    locationSelect.addEventListener('change', (e) => {
      activeCmdbLocation = e.target.value;
      activeCmdbFilterLabel = activeCmdbLocation ? `Location: ${activeCmdbLocation}` : '';
      updateCmdbFilterBanner();
      currentCmdbPage = 1;
      loadCmdbGrid();
    });
  }

  if (pageSizeSelect) {
    pageSizeSelect.addEventListener('change', (e) => {
      const newSize = parseInt(e.target.value, 10);
      currentCmdbPage = calculateNewPageAnchor(currentCmdbPage, currentCmdbPageSize, newSize, 1000);
      currentCmdbPageSize = newSize;
      loadCmdbGrid();
    });
  }

  const clearAllFilters = () => {
    if (searchInput) searchInput.value = '';
    if (sourceSelect) sourceSelect.value = '';
    if (healthSelect) healthSelect.value = '';
    if (locationSelect) locationSelect.value = '';
    activeCmdbSearch = '';
    activeCmdbSource = '';
    activeCmdbHealth = '';
    activeCmdbLocation = '';
    activeCmdbFilterLabel = '';
    updateCmdbFilterBanner();
    currentCmdbPage = 1;
    loadCmdbGrid();
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
        ...(activeCmdbSearch ? { search: activeCmdbSearch } : {}),
        ...(activeCmdbSource ? { source_system: activeCmdbSource } : {}),
        ...(activeCmdbHealth ? { health_tier: activeCmdbHealth } : {}),
        ...(activeCmdbLocation ? { location: activeCmdbLocation } : {}),
      };
      const exportCis = await fetchAllFilteredRows(params => itomApi.getCmdbCis(params), filters);
      if (!exportCis.length) { window.alert('No configuration items match the active filters.'); return; }
      const headers = [
        { label: 'Configuration Item', key: 'name' },
        { label: 'Source System', key: 'source_system' },
        { label: 'Hardware / CI Type', key: 'ci_type' },
        { label: 'Source category', key: 'source_category' }, { label: 'Source type', key: 'source_type' },
        { label: 'Vendor', key: 'vendor' },
        { label: 'Location', key: 'location' },
        { label: 'Health Tier', key: 'health_tier' },
        { label: 'Serial Number', key: 'serial_number' }
      ];
      exportToCsv('CMDB_Configuration_Items_Filtered', headers, exportCis.map(ci => ({ ...ci, health_tier: healthLabel(ci.health_tier) })));
      } catch (error) {
        console.error('CMDB CSV export failed:', error);
        window.alert(`CSV export failed: ${error.message}`);
      } finally {
        exportBtn.disabled = false;
        exportBtn.innerHTML = originalText;
      }
    });
  }
}
