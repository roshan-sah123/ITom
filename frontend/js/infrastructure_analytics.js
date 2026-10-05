/** Standalone compatibility entry point for the infrastructure analytics page. */
import { itomApi } from './api.js';

const freshness = document.getElementById('infraFreshnessLabel');
const database = document.getElementById('infraDatabaseLabel');

async function initializeInfrastructureAnalytics() {
  const [freshnessResult, readinessResult] = await Promise.allSettled([
    itomApi.getFreshness(), itomApi.getReadiness()
  ]);
  const report = freshnessResult.status === 'fulfilled' ? freshnessResult.value : null;
  if (freshness) {
    freshness.textContent = report?.overall_status === 'FRESH' ? 'Fresh' : report?.overall_status === 'STALE' ? 'Data stale' : 'Unavailable';
  }
  const ready = readinessResult.status === 'fulfilled' ? readinessResult.value : null;
  if (database) {
    database.textContent = ready?.active_database_engine
      ? `${ready.active_database_engine} database · ${ready.database_status}`
      : 'Database unavailable';
  }
}

initializeInfrastructureAnalytics();
