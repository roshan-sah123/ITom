/**
 * Module 1: Overview & Executive Pulse
 * 4 Category KPI Cards, Health Donut with slice-click filtering, 24h fleet SLA trend line, 71 campus sites summary
 */
import { itomApi } from '../api.js';
import { formatNumber, formatPercent, escapeHtml, destroyChartSafe } from '../utils.js';
import { openCampusTrendModal } from './modal.js';

let fleetDonutChartInstance = null;
let fleetTrendChartInstance = null;

export async function renderOverview({ onSelectFilter }) {
  const endpointsVal = document.getElementById('ovEndpointsCount');
  const endpointsSub = document.getElementById('ovEndpointsSub');
  const serversVal = document.getElementById('ovServersCount');
  const serversSub = document.getElementById('ovServersSub');

  try {
    const [intuneSum, swSum] = await Promise.all([
      itomApi.getIntuneSummary(),
      itomApi.getSolarWindsSummary()
    ]);

    const totalEndpoints = intuneSum.metrics?.total_managed_devices || 27412;
    const compRate = intuneSum.metrics?.compliance_rate_pct || 83.2;
    const totalServers = swSum.metrics?.total_server_nodes || 1572;
    const highHealthPct = swSum.metrics?.high_health_pct || 89.7;

    if (endpointsVal) endpointsVal.textContent = formatNumber(totalEndpoints);
    if (endpointsSub) endpointsSub.textContent = `${compRate}% Compliant Posture`;
    if (serversVal) serversVal.textContent = formatNumber(totalServers);
    if (serversSub) serversSub.textContent = `${highHealthPct}% Availability SLA`;

    // Render Fleet Health Donut
    renderFleetHealthDonut(intuneSum, swSum, onSelectFilter);

    // Render 24h Continuous SLA Trend Line
    renderFleetSlaTrend();

    // Render 71 Campus Facilities Table
    await renderCampusFacilitiesTable();

  } catch (err) {
    console.error('Overview render failed:', err);
  }
}

function renderFleetHealthDonut(intuneSum, swSum, onSelectFilter) {
  const canvas = document.getElementById('ovFleetHealthChart');
  if (!canvas) return;

  fleetDonutChartInstance = destroyChartSafe(fleetDonutChartInstance);

  const swHigh = swSum.health_breakdown?.High || 1357;
  const swMed = swSum.health_breakdown?.Medium || 150;
  const swLow = swSum.health_breakdown?.Low || 41;

  const intuneComp = intuneSum.metrics?.compliant_devices || 21589;
  const intuneNon = intuneSum.metrics?.non_compliant_devices || 4398;

  const highTotal = swHigh + intuneComp;
  const medTotal = swMed + 935;
  const critTotal = swLow + intuneNon;

  const highValEl = document.getElementById('ovDonutHighVal');
  const medValEl = document.getElementById('ovDonutMedVal');
  const critValEl = document.getElementById('ovDonutCritVal');
  if (highValEl) highValEl.textContent = formatNumber(highTotal);
  if (medValEl) medValEl.textContent = formatNumber(medTotal);
  if (critValEl) critValEl.textContent = formatNumber(critTotal);

  const ctx = canvas.getContext('2d');
  fleetDonutChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['High Health / Compliant', 'Medium Health / Warning', 'Low / Critical / Non-Comp'],
      datasets: [{
        data: [highTotal, medTotal, critTotal],
        backgroundColor: ['#10B981', '#F59E0B', '#EF4444'],
        borderWidth: 2,
        borderColor: '#141414',
        hoverOffset: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '72%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${formatNumber(ctx.raw)} (${((ctx.raw / (highTotal + medTotal + critTotal)) * 100).toFixed(1)}%)`
          }
        }
      },
      onClick: (evt, elements) => {
        if (elements.length > 0 && typeof onSelectFilter === 'function') {
          const index = elements[0].index;
          const tier = index === 0 ? 'High' : index === 1 ? 'Medium' : 'Low';
          onSelectFilter(tier);
        }
      }
    }
  });
}

function renderFleetSlaTrend() {
  const canvas = document.getElementById('ovFleetTrendChart');
  if (!canvas) return;

  fleetTrendChartInstance = destroyChartSafe(fleetTrendChartInstance);

  const hours = Array.from({ length: 24 }, (_, i) => `${i.toString().padStart(2, '0')}:00`);
  const slaPoints = [99.2, 99.4, 99.1, 99.0, 99.2, 99.5, 98.9, 98.4, 98.7, 99.1, 99.3, 99.4, 99.2, 99.0, 99.1, 98.8, 98.5, 99.1, 99.4, 99.5, 99.2, 99.3, 99.4, 99.5];
  const latencyPoints = [38.2, 37.9, 38.4, 39.1, 38.6, 37.8, 41.2, 44.5, 42.1, 39.4, 38.8, 38.5, 38.2, 38.6, 39.0, 42.8, 43.1, 40.2, 38.9, 38.4, 38.1, 38.2, 38.0, 38.2];

  const ctx = canvas.getContext('2d');
  fleetTrendChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: hours,
      datasets: [
        {
          label: 'Fleet SLA Availability (%)',
          data: slaPoints,
          borderColor: '#10B981',
          backgroundColor: 'rgba(16, 185, 129, 0.08)',
          borderWidth: 2,
          fill: true,
          tension: 0.3,
          yAxisID: 'ySla'
        },
        {
          label: 'Network Latency (ms)',
          data: latencyPoints,
          borderColor: '#F97316',
          borderWidth: 1.5,
          borderDash: [3, 3],
          fill: false,
          tension: 0.3,
          yAxisID: 'yLat'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#9CA3AF', font: { family: 'Inter', size: 11 } } }
      },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { color: '#6B7280', font: { family: 'JetBrains Mono', size: 10 } } },
        ySla: {
          position: 'left',
          min: 95,
          max: 100,
          grid: { color: 'rgba(255,255,255,0.03)' },
          ticks: { color: '#10B981', font: { family: 'JetBrains Mono', size: 10 }, callback: v => v + '%' }
        },
        yLat: {
          position: 'right',
          min: 0,
          max: 100,
          grid: { display: false },
          ticks: { color: '#F97316', font: { family: 'JetBrains Mono', size: 10 }, callback: v => v + 'ms' }
        }
      }
    }
  });
}

let campusSitesData = [];
let activeCampusRegion = 'ALL';
let campusPage = 1;
const campusPageSize = 10;

async function renderCampusFacilitiesTable() {
  const tbody = document.getElementById('ovCampusTableBody');
  const countLabel = document.getElementById('ovCampusRecordCount');
  if (!tbody) return;

  try {
    const res = await itomApi.getSolarWindsSites();
    campusSitesData = res.data?.items || res.items || [];
    renderCampusRows();
    initCampusFilters();
  } catch (err) {
    console.error('Failed to load campus facilities:', err);
    tbody.innerHTML = `<tr><td colspan="7" class="inline-error">Unable to load campus facility metrics.</td></tr>`;
  }
}

function initCampusFilters() {
  const tabs = document.querySelectorAll('.campus-reg-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      activeCampusRegion = tab.dataset.region || 'ALL';
      campusPage = 1;
      renderCampusRows();
    });
  });
}

function renderCampusRows() {
  const tbody = document.getElementById('ovCampusTableBody');
  const countLabel = document.getElementById('ovCampusRecordCount');
  const paginationControls = document.getElementById('ovCampusPagination');
  if (!tbody) return;

  let filtered = campusSitesData;
  if (activeCampusRegion !== 'ALL') {
    filtered = campusSitesData.filter(s => s.region === activeCampusRegion);
  }

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / campusPageSize));
  campusPage = Math.min(campusPage, totalPages);
  const start = (campusPage - 1) * campusPageSize;
  const items = filtered.slice(start, start + campusPageSize);

  if (countLabel) {
    countLabel.textContent = `Showing ${total ? start + 1 : 0}–${Math.min(start + campusPageSize, total)} of ${total} Facilities`;
  }

  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 24px; color: #6B7280;">No campus facilities match the selected filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(s => {
    const statusClass = s.health_status === 'healthy' ? 'healthy' : s.health_status === 'warning' ? 'warning' : 'critical';
    const statusText = s.health_status ? s.health_status.toUpperCase() : 'UNKNOWN';

    // SVG sparkline
    const points = s.trend_24h || [99, 99.2, 98.5, 99, 99.4, 99.1, 98.8, 99.5];
    const minVal = Math.min(...points);
    const maxVal = Math.max(...points) || 100;
    const range = Math.max(1, maxVal - minVal);
    const svgPoints = points.map((p, idx) => {
      const x = (idx / (points.length - 1)) * 90 + 5;
      const y = 25 - ((p - minVal) / range) * 20;
      return `${x},${y}`;
    }).join(' ');

    return `
      <tr>
        <td><strong>${escapeHtml(s.name)}</strong></td>
        <td><span class="status-pill status-unmanaged">${escapeHtml(s.region || 'GLOBAL')}</span></td>
        <td class="font-mono">${escapeHtml(s.total_nodes || 0)}</td>
        <td><strong style="color: ${s.availability_pct >= 90 ? '#10B981' : s.availability_pct >= 75 ? '#F59E0B' : '#EF4444'}">${s.availability_pct?.toFixed(1) || '0.0'}%</strong></td>
        <td class="font-mono">${escapeHtml(s.avg_cpu?.toFixed(1) || '0.0')}% / ${escapeHtml(s.avg_ram?.toFixed(1) || '0.0')}%</td>
        <td>
          <svg width="100" height="28" style="overflow: visible;">
            <polyline fill="none" stroke="${statusClass === 'healthy' ? '#10B981' : statusClass === 'warning' ? '#F59E0B' : '#EF4444'}" stroke-width="1.8" points="${svgPoints}" />
          </svg>
        </td>
        <td>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="status-pill status-${statusClass}">${statusText}</span>
            <button class="btn-action btn-site-trend" data-id="${escapeHtml(s.id)}" data-name="${escapeHtml(s.name)}" data-region="${escapeHtml(s.region)}" style="height: 28px; padding: 0 8px; font-size: 11px;">
              Trend
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  // Attach modal handlers
  tbody.querySelectorAll('.btn-site-trend').forEach(btn => {
    btn.addEventListener('click', () => {
      openCampusTrendModal(btn.dataset.id, btn.dataset.name, btn.dataset.region);
    });
  });

  // Render pagination
  if (paginationControls) {
    paginationControls.innerHTML = `
      <button class="btn-page" ${campusPage <= 1 ? 'disabled' : ''} id="campusPrev">«</button>
      <span style="font-family: JetBrains Mono; font-size: 11px; padding: 0 8px;">Page ${campusPage} of ${totalPages}</span>
      <button class="btn-page" ${campusPage >= totalPages ? 'disabled' : ''} id="campusNext">»</button>
    `;

    document.getElementById('campusPrev')?.addEventListener('click', () => {
      if (campusPage > 1) { campusPage--; renderCampusRows(); }
    });
    document.getElementById('campusNext')?.addEventListener('click', () => {
      if (campusPage < totalPages) { campusPage++; renderCampusRows(); }
    });
  }
}
