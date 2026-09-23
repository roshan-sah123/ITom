/**
 * Master Application Bootstrap & Unified View Router
 */
import { initHeader } from './components/header.js?v=4';
import { initModal } from './components/modal.js';
import { initDrawer } from './components/drawer.js';
import { renderHome } from './components/home.js?v=6';
import { renderInfrastructureWorkspace } from './components/infraWorkspace.js?v=10';
import { renderEndpoints } from './components/endpoints.js?v=9';
import { renderCmdb } from './components/cmdb.js?v=8';
import { renderSyncLedger } from './components/syncLedger.js?v=3';
import { renderSyncSchedule } from './components/syncSchedule.js?v=1';

let activeView = 'home';

const workspaceLabels = {
  home: 'Operations overview',
  infrastructure: 'Infrastructure',
  endpoints: 'Endpoints',
  cmdb: 'CMDB',
  sync: 'Sync runs',
  automation: 'Sync & schedule'
};

// Expose global navigation helper for cards and buttons
window.navigateToView = function(viewName, subtabName = '', filterParam = '') {
  const tabs = document.querySelectorAll('.nav-tab');
  const targetTab = document.querySelector(`.nav-tab[data-view="${viewName}"]`);
  
  if (targetTab) {
    tabs.forEach(t => t.classList.remove('active'));
    targetTab.classList.add('active');
  }

  document.querySelectorAll('.view-section').forEach(sec => sec.classList.remove('active'));
  const targetSec = document.getElementById(`view-${viewName}`);
  if (targetSec) targetSec.classList.add('active');

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

  document.getElementById('btnSyncLedger')?.addEventListener('click', () => {
    window.navigateToView('sync');
  });

  // Navigation tab routing
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const targetView = tab.dataset.view;
      if (!targetView || targetView === activeView) return;

      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      document.querySelectorAll('.view-section').forEach(sec => sec.classList.remove('active'));
      const targetSec = document.getElementById(`view-${targetView}`);
      if (targetSec) targetSec.classList.add('active');

      activeView = targetView;
      loadViewData(targetView);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
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
    case 'sync':
      renderSyncLedger();
      break;
    case 'automation':
      renderSyncSchedule();
      break;
  }
}

function refreshCurrentView() {
  loadViewData(activeView);
}
