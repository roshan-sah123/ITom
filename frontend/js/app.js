/**
 * Master Application Bootstrap & Unified View Router
 */
import { initHeader } from './components/header.js';
import { initModal } from './components/modal.js';
import { initDrawer } from './components/drawer.js';
import { renderHome } from './components/home.js';
import { renderInfrastructureWorkspace, switchInfraSubtab } from './components/infraWorkspace.js';
import { renderEndpoints } from './components/endpoints.js';
import { renderCmdb } from './components/cmdb.js';
import { renderSyncLedger } from './components/syncLedger.js';

let activeView = 'home';

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
  loadViewData(viewName);

  if (viewName === 'infrastructure' && subtabName) {
    setTimeout(() => {
      switchInfraSubtab(subtabName, filterParam);
    }, 50);
  }

  window.scrollTo({ top: 0, behavior: 'smooth' });
};

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Global UI Shell components
  initHeader({
    onSyncTriggered: () => {
      refreshCurrentView();
    }
  });
  initModal();
  initDrawer();

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

function loadViewData(view) {
  switch (view) {
    case 'home':
      renderHome();
      break;
    case 'infrastructure':
      renderInfrastructureWorkspace();
      break;
    case 'endpoints':
      renderEndpoints();
      break;
    case 'cmdb':
      renderCmdb();
      break;
    case 'sync':
      renderSyncLedger();
      break;
  }
}

function refreshCurrentView() {
  loadViewData(activeView);
}
