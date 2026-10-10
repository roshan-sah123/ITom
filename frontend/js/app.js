/**
 * Master Application Bootstrap & Unified View Router
 */
import { initHeader } from './components/header.js?v=4';
import { initModal } from './components/modal.js';
import { initDrawer } from './components/drawer.js?v=2';
import { renderHome } from './components/home.js?v=6';
import { renderInfrastructureWorkspace } from './components/infraWorkspace.js?v=17';
import { renderEndpoints } from './components/endpoints.js?v=10';
import { renderCmdb } from './components/cmdb.js?v=10';
import { renderSyncLedger } from './components/syncLedger.js?v=3';
import { renderSyncSchedule } from './components/syncSchedule.js?v=1';

let activeView = 'home';

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
window.navigateToView = function(viewName, subtabName = '', filterParam = '') {
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
  const workspaceLabel = document.getElementById('activeWorkspaceLabel');
  if (workspaceLabel) workspaceLabel.textContent = workspaceLabels[viewName] || 'Operations overview';
  loadViewData(viewName, subtabName, filterParam);

  window.scrollTo({ top: 0, behavior: 'smooth' });
};

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Global UI Shell components
  initHeader();
  initModal();
  initDrawer();

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
  switch (view) {
    case 'home':
      renderHome();
      break;
    case 'infrastructure':
      renderInfrastructureWorkspace(subtabName || 'servers', filterParam);
      break;
    case 'endpoints':
      renderEndpoints(subtabName, filterParam);
      break;
    case 'cmdb':
      renderCmdb();
      break;
    case 'knowledge':
    case 'automations':
      break;
    case 'sync':
      renderSyncLedger();
      break;
    case 'sync-schedule':
      renderSyncSchedule();
      break;
  }
}

function refreshCurrentView() {
  loadViewData(activeView);
}
