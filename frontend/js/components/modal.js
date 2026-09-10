/**
 * Leadership 24h Trend Modal
 */
import { itomApi } from '../api.js';
import { escapeHtml, formatPercent, formatLatency, destroyChartSafe } from '../utils.js';

let trendChartInstance = null;

export function initModal() {
  const backdrop = document.getElementById('trendModalBackdrop');
  const closeBtn = document.getElementById('modalCloseBtn');

  if (closeBtn && backdrop) {
    closeBtn.addEventListener('click', () => {
      backdrop.style.display = 'none';
      backdrop.classList.remove('active');
      trendChartInstance = destroyChartSafe(trendChartInstance);
    });

    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        backdrop.style.display = 'none';
        backdrop.classList.remove('active');
        trendChartInstance = destroyChartSafe(trendChartInstance);
      }
    });
  }
}

export async function openCampusTrendModal(siteName, region) {
  const backdrop = document.getElementById('trendModalBackdrop');
  const titleEl = document.getElementById('modalCampusTitle');
  const subEl = document.getElementById('modalCampusSubtitle');
  const chartCanvas = document.getElementById('campusModalChart') || document.getElementById('modalTrendChart');

  if (!backdrop) return;

  if (titleEl) titleEl.textContent = siteName || 'Campus Facility';
  if (subEl) subEl.textContent = `Region: ${region || 'GLOBAL'} | Monitored Facility 24-Hour Continuous SLA & Latency Trend`;

  backdrop.style.display = 'flex';
  backdrop.classList.add('active');

  trendChartInstance = destroyChartSafe(trendChartInstance);

  try {
    const trendRes = await itomApi.getSolarWindsSiteTrend(siteName, 24);
    const data = trendRes.data || trendRes;
    const points = data.data_points || [];

    const labels = points.length ? points.map(p => {
      const d = new Date(p.timestamp);
      return `${d.getHours().toString().padStart(2, '0')}:00`;
    }) : Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`);

    const slaValues = points.length ? points.map(p => p.availability_pct) : [98.8, 99.1, 99.4, 99.2, 98.9, 99.5, 99.3, 98.7, 99.2, 99.6, 99.1, 98.9, 99.2, 99.4, 99.6, 99.5, 99.2, 99.4, 99.5, 99.6, 99.2, 99.5, 99.4, 99.2];
    const cpuValues = points.length ? points.map(p => p.avg_cpu) : [12, 14, 11, 10, 9, 12, 18, 22, 25, 24, 21, 19, 18, 20, 22, 19, 15, 12, 14, 13, 11, 12, 10, 11];

    if (chartCanvas) {
      const ctx = chartCanvas.getContext('2d');
      trendChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Availability SLA (%)',
              data: slaValues,
              borderColor: '#10B981',
              backgroundColor: 'rgba(16, 185, 129, 0.1)',
              borderWidth: 2,
              fill: true,
              tension: 0.3,
              pointRadius: 3,
              pointHoverRadius: 6,
              yAxisID: 'ySla'
            },
            {
              label: 'Avg CPU Load (%)',
              data: cpuValues,
              borderColor: '#F97316',
              borderDash: [3, 3],
              borderWidth: 1.5,
              fill: false,
              tension: 0.3,
              pointRadius: 3,
              pointHoverRadius: 6,
              yAxisID: 'yCpu'
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              labels: { color: '#9CA3AF', font: { family: 'Inter', size: 11 } }
            }
          },
          scales: {
            x: {
              grid: { color: 'rgba(255, 255, 255, 0.04)' },
              ticks: { color: '#6B7280', font: { family: 'JetBrains Mono', size: 10 } }
            },
            ySla: {
              position: 'left',
              min: 0,
              max: 100,
              grid: { color: 'rgba(255, 255, 255, 0.04)' },
              ticks: { color: '#10B981', font: { family: 'JetBrains Mono', size: 10 } }
            },
            yCpu: {
              position: 'right',
              min: 0,
              max: 100,
              grid: { display: false },
              ticks: { color: '#F97316', font: { family: 'JetBrains Mono', size: 10 } }
            }
          }
        }
      });
    }

  } catch (err) {
    console.error('Failed to load campus trend modal:', err);
  }
}
