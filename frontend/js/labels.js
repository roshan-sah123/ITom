// Route IDs are stable; visible workspace terminology lives here.
export const workspaceLabels = Object.freeze({
  home: 'Home page', infrastructure: 'Operations Analytics', endpoints: 'Digital Workspace',
  cmdb: 'Assets Analytics', knowledge: 'Knowledge Centre', automations: 'Automations',
  sync: 'Sync runs', 'sync-schedule': 'Sync & schedule'
});
export const siteScoreLabel = 'Site Score';
export function applyWorkspaceLabels(root = document) {
  root.querySelectorAll('[data-workspace-label]').forEach(element => {
    element.textContent = workspaceLabels[element.dataset.workspaceLabel] || element.textContent;
  });
  root.querySelectorAll('.nav-tab[data-view]').forEach(element => {
    const label = workspaceLabels[element.dataset.view];
    if (label) { element.textContent = label; element.setAttribute('aria-label', label); }
  });
}
