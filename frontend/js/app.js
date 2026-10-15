/**
 * Master Application Bootstrap & Unified View Router
 */
import { initHeader } from './components/header.js?v=4';
import { initModal } from './components/modal.js';
import { initDrawer } from './components/drawer.js?v=3';
import { renderHome } from './components/home.js?v=10';
import { renderInfrastructureWorkspace } from './components/infraWorkspace.js?v=27';
import { renderEndpoints } from './components/endpoints.js?v=13';
import { renderCmdb } from './components/cmdb.js?v=14';
import { renderSyncLedger } from './components/syncLedger.js?v=3';
import { renderSyncSchedule } from './components/syncSchedule.js?v=1';
import { initWorkspaceFreshness, renderWorkspaceFreshness } from './components/workspaceFreshness.js?v=2';

let activeView = 'home';
let navigationVersion = 0;

const workspaceLabels = {
  home: 'Operations overview',
  infrastructure: 'Infrastructure',
  endpoints: 'Endpoints',
  cmdb: 'CMDB',
  knowledge: 'Knowledge Centre',
  automations: 'Automations',
  sync: 'Sync runs',
  'sync-schedule': 'Sync & schedule'
};

// Expose global navigation helper for cards and buttons
window.navigateToView = async function(viewName, subtabName = '', filterParam = '') {
  const targetSec = document.getElementById(`view-${viewName}`);
  if (!targetSec) return;

  const tabs = document.querySelectorAll('.nav-tab');
  const targetTab = document.querySelector(`.nav-tab[data-view="${viewName}"]`);
  tabs.forEach((tab) => {
    const isActive = tab === targetTab;
    tab.classList.toggle('active', isActive);
    if (isActive) tab.setAttribute('aria-current', 'page');
    else tab.removeAttribute('aria-current');
  });

  document.querySelectorAll('.view-section').forEach(sec => sec.classList.remove('active'));
  targetSec.classList.add('active');

  activeView = viewName;
  const version = ++navigationVersion;
  const inventoryId = viewName === 'infrastructure' && (!subtabName || subtabName === 'servers')
    ? 'swInventoryHeading' : viewName === 'endpoints' ? 'epInventoryHeading' : null;
  const exceptionLanding = Boolean(inventoryId && filterParam);
  const summary = document.getElementById(viewName === 'infrastructure' ? 'swChartSummary' : 'epChartSummary');
  if (inventoryId && summary) summary.open = !exceptionLanding;
  const workspaceLabel = document.getElementById('activeWorkspaceLabel');
  if (workspaceLabel) workspaceLabel.textContent = workspaceLabels[viewName] || 'Operations overview';
  window.scrollTo({ top: 0, behavior: 'instant' });
  await loadViewData(viewName, subtabName, filterParam);
  if (!exceptionLanding || version !== navigationVersion) return;
  const heading = document.getElementById(inventoryId);
  if (!heading?.getClientRects().length) return;
  heading.focus({ preventScroll: true });
  heading.scrollIntoView({ block: 'start', behavior: 'instant' });
};

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Global UI Shell components
  initHeader();
  initModal();
  initDrawer();
  initWorkspaceFreshness(refreshCurrentView);

  const globalSearch = document.getElementById('globalSearch');
  globalSearch?.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    const query = globalSearch.value.trim();
    if (!query) return;
    window.navigateToView('cmdb');
    document.dispatchEvent(new CustomEvent('itom:global-search', { detail: { query } }));
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === '/' && document.activeElement !== globalSearch) {
      event.preventDefault();
      globalSearch?.focus();
    }
  });

  document.getElementById('brandHome')?.addEventListener('click', () => {
    window.navigateToView('home');
  });

  document.querySelectorAll('[data-back-home]').forEach(button => {
    button.addEventListener('click', () => window.navigateToView('home'));
  });

  // Navigation tab routing
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const targetView = tab.dataset.view;
      if (!targetView || targetView === activeView) return;
      window.navigateToView(targetView);
    });
  });

  document.querySelectorAll('.footer-operation-link').forEach((button) => {
    button.addEventListener('click', () => window.navigateToView(button.dataset.targetView));
  });

  // Initial load: Portal Home Page
  loadViewData('home');
});

function loadViewData(view, subtabName = '', filterParam = '') {
  renderWorkspaceFreshness(view);
  switch (view) {
    case 'home':
      return renderHome();
    case 'infrastructure':
      return renderInfrastructureWorkspace(subtabName || 'servers', filterParam);
    case 'endpoints':
      return renderEndpoints(subtabName, filterParam);
    case 'cmdb':
      return renderCmdb();
    case 'knowledge':
    case 'automations':
      break;
    case 'sync':
      return renderSyncLedger();
    case 'sync-schedule':
      return renderSyncSchedule();
  }
}

function refreshCurrentView() {
  const subtab = activeView === 'infrastructure'
    ? document.querySelector('.category-card-tab.active')?.dataset.subtab || 'servers' : '';
  loadViewData(activeView, subtab);
}
