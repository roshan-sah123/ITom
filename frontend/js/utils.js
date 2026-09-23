/**
 * Coforge ITOM Portal - Core Utilities
 * Strict XSS sanitization, deterministic pagination math, formatting, CSV export
 */

export function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export function formatNumber(num) {
  if (num === null || num === undefined || isNaN(num)) return '0';
  return Number(num).toLocaleString('en-US');
}

export function formatPercent(val, decimals = 1) {
  if (val === null || val === undefined || isNaN(val)) return '0.0%';
  return Number(val).toFixed(decimals) + '%';
}

export function formatLatency(ms) {
  if (ms === null || ms === undefined || isNaN(ms)) return '0ms';
  return Number(ms).toFixed(1) + 'ms';
}

export function formatRelativeTime(isoString) {
  if (!isoString) return 'Unknown';
  try {
    // Older SQLite-backed API responses may omit the UTC offset. All persisted
    // ITOM timestamps are UTC, so interpret a naive ISO value as UTC.
    const normalized = typeof isoString === 'string' && /T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(isoString)
      ? `${isoString}Z`
      : isoString;
    const date = new Date(normalized);
    const now = new Date();
    const diffSec = Math.max(0, Math.floor((now - date) / 1000));
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHours = Math.floor(diffMin / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  } catch {
    return 'Invalid Date';
  }
}

/**
 * Deterministic Anchor Pagination formula
 * When page size changes, retains current row anchor without jumping to blank screens
 */
export function calculateNewPageAnchor(currentPage, oldPageSize, newPageSize, totalPages) {
  if (!totalPages || totalPages < 1) return 1;
  const firstVisibleRecord = (currentPage - 1) * oldPageSize;
  const newPage = Math.floor(firstVisibleRecord / newPageSize) + 1;
  return Math.min(Math.max(1, newPage), totalPages);
}

/**
 * Debounce helper for instant, responsive search
 */
export function debounce(func, delay = 200) {
  let timer = null;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => func.apply(this, args), delay);
  };
}

/**
 * Client-side RFC-4180 CSV Export Streamer
 */
export function exportToCsv(filename, headers, rows) {
  const escapeCell = (cell) => {
    if (cell === null || cell === undefined) return '""';
    let str = String(cell);
    // Neutralize formula injection: if cell starts with =, +, -, @, \t, or \r
    if (/^[=+\-@\t\r]/.test(str)) {
      str = "'" + str;
    }
    str = str.replace(/"/g, '""');
    return `"${str}"`;
  };

  const headerLine = headers.map(h => escapeCell(h.label || h)).join(',');
  const rowLines = rows.map(row => {
    return headers.map(h => {
      const key = h.key || h;
      return escapeCell(row[key] !== undefined ? row[key] : '');
    }).join(',');
  });

  const csvContent = [headerLine, ...rowLines].join('\r\n');
  const blob = new Blob(["\ufeff" + csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', filename.endsWith('.csv') ? filename : `${filename}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/** Fetch every API page for the current filter set before exporting. */
export async function fetchAllFilteredRows(fetchPage, filters = {}) {
  const pageSize = 100;
  const rows = [];
  let page = 1;
  let expectedTotal = null;
  while (page <= 10000) {
    const response = await fetchPage({ ...filters, page, page_size: pageSize });
    const data = response?.data || response || {};
    const items = Array.isArray(data.items) ? data.items : [];
    const total = Number(data.total ?? data.pagination?.total_records);
    if (Number.isFinite(total) && total >= 0) expectedTotal = total;
    rows.push(...items);
    if (!items.length || items.length < pageSize || (expectedTotal !== null && rows.length >= expectedTotal)) break;
    page += 1;
  }
  if (page > 10000) throw new Error('Export stopped at the safety limit; narrow the filters and try again.');
  if (expectedTotal !== null && rows.length !== expectedTotal) {
    throw new Error(`Export incomplete: fetched ${rows.length} of ${expectedTotal} matching rows. Try again after data sync finishes.`);
  }
  return rows;
}

/**
 * Safe Chart.js instance destruction to prevent canvas memory leaks
 */
export function destroyChartSafe(chartInstance) {
  if (chartInstance && typeof chartInstance.destroy === 'function') {
    try {
      chartInstance.destroy();
    } catch (e) {
      console.warn('Error destroying chart instance:', e);
    }
  }
  return null;
}

/**
 * Render smart full-dataset pagination controls
 */
export function generatePaginationControls(container, currentPage, totalPages, onPageChange) {
  if (!container) return;
  if (!totalPages || totalPages < 1) {
    container.innerHTML = '';
    return;
  }

  let html = '';
  // First & Prev
  html += `<button class="btn-page btn-page-nav" data-target="1" ${currentPage <= 1 ? 'disabled' : ''} title="First Page">«</button>`;
  html += `<button class="btn-page btn-page-nav" data-target="${currentPage - 1}" ${currentPage <= 1 ? 'disabled' : ''} title="Previous Page">‹</button>`;

  // Smart page numbers
  const pagesToShow = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pagesToShow.push(i);
  } else {
    if (currentPage <= 4) {
      pagesToShow.push(1, 2, 3, 4, 5, '...', totalPages);
    } else if (currentPage >= totalPages - 3) {
      pagesToShow.push(1, '...', totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
    } else {
      pagesToShow.push(1, '...', currentPage - 1, currentPage, currentPage + 1, '...', totalPages);
    }
  }

  pagesToShow.forEach(p => {
    if (p === '...') {
      html += `<span class="page-ellipsis" style="color: #6B7280; padding: 0 4px; font-family: var(--font-mono); font-size: 11px;">…</span>`;
    } else {
      const isActive = p === currentPage;
      html += `<button class="btn-page ${isActive ? 'active' : ''}" data-target="${p}">${p}</button>`;
    }
  });

  // Next & Last
  html += `<button class="btn-page btn-page-nav" data-target="${currentPage + 1}" ${currentPage >= totalPages ? 'disabled' : ''} title="Next Page">›</button>`;
  html += `<button class="btn-page btn-page-nav" data-target="${totalPages}" ${currentPage >= totalPages ? 'disabled' : ''} title="Last Page">»</button>`;

  container.innerHTML = html;

  container.querySelectorAll('button[data-target]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const target = parseInt(btn.dataset.target, 10);
      if (!isNaN(target) && target >= 1 && target <= totalPages && target !== currentPage) {
        onPageChange(target);
      }
    });
  });
}

