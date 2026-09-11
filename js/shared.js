/**
 * ITOM OPS Analytics - Shared Dashboard Runtime
 *
 * Provides the domain-agnostic tab router, header stat synchronization,
 * Chart.js lifecycle helpers, the unified enterprise pagination controller,
 * bounded-concurrency REST pagination fetcher, and the 10-minute auto-refresh
 * engine. Domain modules (intune.js, solarwinds.js, cmdb.js) register
 * themselves via `ITOM_SHARED.registerDomain()` instead of being hardcoded
 * here, so adding a new domain never requires editing this file.
 */
(function () {
  'use strict';

  const UTILS = window.ITOM_UTILS || {};
  const escapeHtml = UTILS.escapeHtml || function (s) { return s == null ? '' : String(s); };
  const debounce = UTILS.debounce || function (fn) { return fn; };

  const VALID_TABS = ['intune', 'solarwinds', 'cmdb'];
  const DEFAULT_TAB = 'intune';
  let currentActiveTab = DEFAULT_TAB;

  /** @type {Record<string, any>} tabId -> domain handler registered by intune.js/solarwinds.js/cmdb.js */
  const domains = {};

  function registerDomain(tabId, handlers) {
    domains[tabId] = handlers;
  }

  function parseTabId(raw) {
    if (!raw) return DEFAULT_TAB;
    const clean = String(raw).trim().replace(/^[#?]/, '').replace(/^tab=/, '').toLowerCase();
    return VALID_TABS.includes(clean) ? clean : DEFAULT_TAB;
  }

  function getActiveTab() {
    return currentActiveTab;
  }

  function updateHeaderStat(tabId) {
    // Refresh every registered domain's tab badge pill independently of the active tab.
    Object.keys(domains).forEach((id) => {
      const domain = domains[id];
      if (!domain.pillElementId) return;
      const pill = document.getElementById(domain.pillElementId);
      if (pill) pill.textContent = `${Number(domain.getTotal()).toLocaleString()} ${domain.pillSuffix}`;
    });

    const labelElem = document.getElementById('headerStatLabel') || document.querySelector('.header-stat-box .stat-label');
    const valElem = document.getElementById('statTotalEndpoints');
    if (!labelElem || !valElem) return;

    const domain = domains[tabId];
    if (domain) {
      labelElem.textContent = domain.headerLabel;
      valElem.textContent = Number(domain.getTotal()).toLocaleString();
    } else if (tabId === 'dex') {
      labelElem.textContent = 'DEX Monitored Fleet';
      valElem.textContent = 'Phase 2';
    }
  }

  function switchTab(targetTab, updateHash = true) {
    const tabId = parseTabId(targetTab);
    currentActiveTab = tabId;

    document.querySelectorAll('.tab-btn').forEach((btn) => {
      const isActive = btn.getAttribute('data-tab') === tabId;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', String(isActive));
    });

    document.querySelectorAll('.tab-pane').forEach((pane) => {
      const paneTab = pane.getAttribute('data-tab') || pane.id.replace('view-', '');
      const isActive = paneTab === tabId;
      pane.classList.toggle('active', isActive);
      pane.classList.toggle('hidden', !isActive);
    });

    updateHeaderStat(tabId);

    if (updateHash && window.location.hash !== `#${tabId}`) {
      history.replaceState(null, '', `#${tabId}`);
    }

    // Frictionless Chart.js activation/resize (zero layout shift, zero artificial delay)
    const domain = domains[tabId];
    if (domain) {
      if (!domain.isRendered() && domain.getData()) {
        domain.renderDashboard(domain.getData());
      } else {
        domain.resizeCharts();
        domain.renderTable();
      }
    }

    return currentActiveTab;
  }

  function initTabRouter() {
    document.querySelectorAll('.tab-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        switchTab(btn.getAttribute('data-tab'), true);
      });
    });

    const initialHash = window.location.hash.replace('#', '').trim();
    switchTab(initialHash || DEFAULT_TAB, false);

    window.addEventListener('hashchange', () => {
      const hash = window.location.hash.replace('#', '').trim();
      if (hash) switchTab(hash, false);
    });
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

  function renderEnterprisePagination({
    container,
    countLabel,
    totalItems,
    pageSize,
    currentPage,
    pageSizeOptions = [10, 25, 50, 100],
    itemName = 'records',
    totalAuthoritative = null,
    onPageChange,
    onPageSizeChange,
  }) {
    if (!container) return;

    const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const startIndex = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
    const endIndex = Math.min(currentPage * pageSize, totalItems);

    if (countLabel) {
      if (totalItems === 0) {
        countLabel.textContent = `Showing 0 matching ${itemName}`;
      } else if (totalAuthoritative && totalAuthoritative > totalItems) {
        countLabel.textContent = `Showing ${startIndex}\u2013${endIndex} of ${totalItems.toLocaleString()} matching ${itemName} (filtered from ${totalAuthoritative.toLocaleString()} total)`;
      } else {
        countLabel.textContent = `Showing ${startIndex}\u2013${endIndex} of ${totalItems.toLocaleString()} ${itemName}`;
      }
    }

    if (totalItems <= 0) {
      container.innerHTML = '';
      return;
    }

    const pagesToShow = new Set([1, totalPages]);
    for (let i = Math.max(1, currentPage - 1); i <= Math.min(totalPages, currentPage + 1); i++) {
      pagesToShow.add(i);
    }
    const sortedPages = Array.from(pagesToShow).sort((a, b) => a - b);

    let html = `
      <div class="pagination-footer-bar">
        <div class="page-size-selector">
          <label>Per page:</label>
          <select class="pagination-select" aria-label="Select rows per page">
            ${pageSizeOptions.map((sz) => `<option value="${sz}" ${sz === pageSize ? 'selected' : ''}>${sz}</option>`).join('')}
          </select>
        </div>
        <div class="pagination-wrapper" role="navigation" aria-label="Pagination">
          <button class="pagination-btn pagination-nav" data-action="first" ${currentPage === 1 ? 'disabled' : ''} title="First Page" aria-label="First Page">&laquo;</button>
          <button class="pagination-btn pagination-nav" data-action="prev" ${currentPage === 1 ? 'disabled' : ''} title="Previous Page" aria-label="Previous Page">&lsaquo;</button>
    `;

    let prevPageNum = 0;
    for (const p of sortedPages) {
      if (prevPageNum && p - prevPageNum > 1) {
        html += `<span class="pagination-ellipsis" aria-hidden="true">&bull;&bull;&bull;</span>`;
      }
      html += `<button class="pagination-btn ${p === currentPage ? 'active' : ''}" data-page="${p}" aria-label="Page ${p}" ${p === currentPage ? 'aria-current="page"' : ''}>${p}</button>`;
      prevPageNum = p;
    }

    html += `
          <button class="pagination-btn pagination-nav" data-action="next" ${currentPage === totalPages ? 'disabled' : ''} title="Next Page" aria-label="Next Page">&rsaquo;</button>
          <button class="pagination-btn pagination-nav" data-action="last" ${currentPage === totalPages ? 'disabled' : ''} title="Last Page" aria-label="Last Page">&raquo;</button>
        </div>
      </div>
    `;

    container.innerHTML = html;

    container.querySelectorAll('.pagination-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const action = btn.getAttribute('data-action');
        const targetPage = Number(btn.getAttribute('data-page'));

        let newPage = currentPage;
        if (action === 'first') newPage = 1;
        else if (action === 'prev') newPage = Math.max(1, currentPage - 1);
        else if (action === 'next') newPage = Math.min(totalPages, currentPage + 1);
        else if (action === 'last') newPage = totalPages;
        else if (targetPage) newPage = targetPage;

        if (newPage !== currentPage && newPage >= 1 && newPage <= totalPages && typeof onPageChange === 'function') {
          onPageChange(newPage);
        }
      });
    });

    const selectElem = container.querySelector('.pagination-select');
    if (selectElem) {
      selectElem.addEventListener('change', (e) => {
        const newSize = Number(e.target.value);
        if (newSize !== pageSize) {
          const firstItemIdx = (currentPage - 1) * pageSize;
          const newCurrentPage = Math.floor(firstItemIdx / newSize) + 1;
          if (typeof onPageSizeChange === 'function') onPageSizeChange(newSize, newCurrentPage);
        }
      });
    }
  }

  function resetTableScroll(tabId) {
    const pane = document.getElementById(tabId);
    if (!pane) return;
    const tableResponsive = pane.querySelector('.table-responsive');
    if (tableResponsive) tableResponsive.scrollTop = 0;
    const tableCard = pane.querySelector('.table-card');
    if (tableCard && tableCard.getBoundingClientRect().top < 0) {
      tableCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  /**
   * Fetch every page of a paginated REST envelope with bounded concurrency, preserving
   * page order. Falls back gracefully (returns whatever pages already succeeded) if a
   * later page request fails, so a single flaky request never blanks the whole table.
   */
  async function fetchAllPages(baseUrl, { pageSize = 100, maxConcurrent = 6, extraParams = '' } = {}) {
    const buildUrl = (page) => `${baseUrl}?page=${page}&page_size=${pageSize}${extraParams}`;

    const first = await fetch(buildUrl(1));
    if (!first.ok) throw new Error(`HTTP ${first.status} fetching ${baseUrl}`);
    const firstPayload = await first.json();
    const items = Array.isArray(firstPayload.items) ? [...firstPayload.items] : [];
    const totalPages = Number(firstPayload.total_pages || 1);
    const total = Number(firstPayload.total ?? items.length);

    if (totalPages <= 1) {
      return { items, total };
    }

    const remainingPages = [];
    for (let p = 2; p <= totalPages; p++) remainingPages.push(p);

    const pageResults = new Array(remainingPages.length);
    let cursor = 0;

    async function worker() {
      while (cursor < remainingPages.length) {
        const idx = cursor++;
        const page = remainingPages[idx];
        try {
          const res = await fetch(buildUrl(page));
          if (res.ok) {
            const payload = await res.json();
            pageResults[idx] = Array.isArray(payload.items) ? payload.items : [];
          } else {
            pageResults[idx] = [];
          }
        } catch {
          pageResults[idx] = [];
        }
      }
    }

    const workers = Array.from({ length: Math.min(maxConcurrent, remainingPages.length) }, () => worker());
    await Promise.all(workers);

    pageResults.forEach((pageItems) => items.push(...pageItems));
    return { items, total };
  }

  function initAutoRefreshTimer(onRefresh) {
    const AUTO_REFRESH_INTERVAL_SECONDS = 10 * 60;
    let remainingSeconds = AUTO_REFRESH_INTERVAL_SECONDS;
    let timerInterval = null;

    const countdownElem = document.getElementById('refreshCountdown');
    const refreshBtn = document.getElementById('manualRefreshBtn');

    function updateCountdownDisplay() {
      if (!countdownElem) return;
      const mins = Math.floor(remainingSeconds / 60);
      const secs = remainingSeconds % 60;
      countdownElem.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }

    async function triggerTelemetryRefresh() {
      const svgIcon = refreshBtn ? refreshBtn.querySelector('svg') : null;
      if (svgIcon) svgIcon.classList.add('spin');
      if (refreshBtn) refreshBtn.disabled = true;

      remainingSeconds = AUTO_REFRESH_INTERVAL_SECONDS;
      updateCountdownDisplay();
      if (countdownElem) countdownElem.textContent = 'Syncing...';

      try {
        await onRefresh();
      } catch (err) {
        console.error('Auto-refresh error:', err);
      } finally {
        if (svgIcon) svgIcon.classList.remove('spin');
        if (refreshBtn) refreshBtn.disabled = false;
        remainingSeconds = AUTO_REFRESH_INTERVAL_SECONDS;
        updateCountdownDisplay();
      }
    }

    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(() => {
      remainingSeconds--;
      if (remainingSeconds <= 0) triggerTelemetryRefresh();
      else updateCountdownDisplay();
    }, 1000);

    if (refreshBtn) {
      refreshBtn.addEventListener('click', (e) => {
        e.preventDefault();
        triggerTelemetryRefresh();
      });
    }

    updateCountdownDisplay();
  }

  // Responsive Chart.js resize across every registered domain (zero hardcoded chart list)
  let chartResizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(chartResizeTimer);
    chartResizeTimer = setTimeout(() => {
      Object.values(domains).forEach((domain) => domain.resizeCharts());
    }, 100);
  });

  window.ITOM_SHARED = {
    registerDomain,
    getActiveTab,
    switchTab,
    initTabRouter,
    updateHeaderStat,
    destroyChartSafe,
    renderEnterprisePagination,
    resetTableScroll,
    fetchAllPages,
    initAutoRefreshTimer,
    escapeHtml,
    debounce,
    VALID_TABS,
    DEFAULT_TAB,
  };
})();
