const API = '/api/v1/cmdb-inventory';
const PAGE_SIZE = 50;
const TYPES = ['server', 'network', 'telecom'];
const TYPE_LABELS = {server: 'Servers', network: 'Network Devices', telecom: 'Telecom'};
let initialized = false;
let adminToken = 'local-development';
let activeType = 'server';
let activePage = 1;
let activeSearch = '';
let inventoryDialog;
let adminDialog;
let editDialog;
let addDialog;
let importDialog;
let activeRecordTemplate = null;
let legacyInventory;
let allInventoryCache;
let editMode = false;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}

function button(text, action, className = '', ariaLabel = text) {
  const element = node('button', text, className);
  element.type = 'button';
  element.setAttribute('aria-label', ariaLabel);
  element.addEventListener('click', action);
  return element;
}

async function request(path, options = {}, token = '') {
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers,
    credentials: 'same-origin',
    cache: 'no-store'
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.error || `Request failed (${response.status}).`);
  return data;
}

async function loadLegacyInventory() {
  if (legacyInventory) return legacyInventory;
  const response = await fetch('./inventory_consolidated.json', {cache: 'no-store'});
  if (!response.ok) throw new Error('Existing CMDB inventory is unavailable.');
  legacyInventory = await response.json();
  return legacyInventory;
}

function legacyRows(data, type) {
  const rows = type === 'server' ? data.servers || []
    : type === 'network' ? data.network_devices || []
      : data.telecom_devices || data.telecom || [];
  return rows.map((record, index) => {
    const fields = Object.fromEntries(Object.entries(record).filter(([key]) => key && key !== 'null'));
    const name = fields['Computer Name'] || fields.HostName || fields['Host Name'] || fields.Name
      || fields.name || fields['Serial Number'] || fields['Serial No'] || `${TYPE_LABELS[type]} row ${index + 1}`;
    return {
      id: `legacy-${type}-${index + 1}`,
      inventory_type: type,
      name: String(name),
      source_file: 'inventory_consolidated.json',
      source_sheet: 'Existing CMDB inventory',
      source_row: index + 1,
      data: Object.entries(fields).map(([header, value], cellIndex) => ({index: cellIndex, header, value})),
      is_validated: false,
      validated_at: null,
      validated_by: null
    };
  });
}

function setStatus(id, message, isError = false) {
  const target = document.getElementById(id);
  if (!target) return;
  target.textContent = message;
  target.dataset.error = String(isError);
}

function buildDialogs() {
  if (!document.getElementById('cmdbInventoryActionStyles')) {
    const style = document.createElement('style'); style.id = 'cmdbInventoryActionStyles';
    style.textContent = '.cmdb-validated-action{background:#107650!important;border-color:#107650!important;color:#fff!important;opacity:1!important}.cmdb-inventory-row-actions{white-space:nowrap}.cmdb-validated-time{font-size:12px;color:#526170;white-space:nowrap}';
    document.head.append(style);
  }
  inventoryDialog = document.createElement('dialog');
  inventoryDialog.className = 'cmdb-inventory-dialog';
  inventoryDialog.setAttribute('aria-labelledby', 'cmdbInventoryTitle');
  inventoryDialog.innerHTML = `
    <div class="cmdb-inventory-dialog-head">
      <div><h2 id="cmdbInventoryTitle"></h2><p id="cmdbInventoryCount" class="cmdb-inventory-muted"></p></div>
      <div class="cmdb-inventory-actions">
        <button type="button" id="cmdbInventoryAddRecord" class="primary" hidden aria-label="Add inventory record">+ Add data</button>
        <button type="button" id="cmdbInventoryExport">Export CSV</button>
        <button type="button" id="cmdbInventoryEditToggle">Edit records</button>
        <button type="button" data-close-inventory aria-label="Close inventory">Close</button>
      </div>
    </div>
    <div class="cmdb-inventory-toolbar"><input id="cmdbInventorySearch" type="search" aria-label="Search inventory" placeholder="Search inventory"></div>
    <p id="cmdbInventoryStatus" class="cmdb-inventory-status" role="status" aria-live="polite"></p>
    <div class="cmdb-inventory-table-wrap"><div id="cmdbInventoryTables" class="cmdb-inventory-sheet-list"></div></div>
    <div class="cmdb-inventory-footer"><span id="cmdbInventoryPageLabel"></span><div><button type="button" id="cmdbInventoryPrevious">Previous</button><button type="button" id="cmdbInventoryNext">Next</button></div></div>`;


  adminDialog = document.createElement('dialog');
  adminDialog.className = 'cmdb-inventory-dialog cmdb-admin-dialog';
  adminDialog.setAttribute('aria-labelledby', 'cmdbAdminTitle');
  adminDialog.innerHTML = `
    <div class="cmdb-inventory-dialog-head">
      <div><h2 id="cmdbAdminTitle">Inventory Admin</h2><p class="cmdb-inventory-muted">Review, correct, validate, or remove imported inventory records.</p></div>
      <button type="button" data-close-admin aria-label="Close Inventory Admin">Close</button>
    </div>
    <div class="cmdb-inventory-toolbar cmdb-admin-toolbar">
      <select id="cmdbAdminType" aria-label="Filter inventory type"><option value="server">Servers</option><option value="network">Network Devices</option><option value="telecom">Telecom</option></select>
      <input id="cmdbAdminSearch" type="search" aria-label="Search review rows" placeholder="Search records">
      <span id="cmdbAdminCount" class="cmdb-inventory-muted"></span>
    </div>
    <p id="cmdbAdminStatus" class="cmdb-inventory-status" role="status" aria-live="polite"></p>
    <div class="cmdb-inventory-table-wrap"><div id="cmdbAdminTables" class="cmdb-inventory-sheet-list"></div></div>
    <div class="cmdb-inventory-footer"><span id="cmdbAdminPageLabel"></span><div><button type="button" id="cmdbAdminPrevious">Previous</button><button type="button" id="cmdbAdminNext">Next</button></div></div>`;

  editDialog = document.createElement('dialog');
  editDialog.className = 'cmdb-inventory-dialog cmdb-edit-dialog';
  editDialog.setAttribute('aria-labelledby', 'cmdbEditTitle');

  addDialog = document.createElement('dialog');
  addDialog.className = 'cmdb-inventory-dialog cmdb-edit-dialog';
  addDialog.setAttribute('aria-labelledby', 'cmdbAddTitle');

  importDialog = document.createElement('dialog');
  importDialog.className = 'cmdb-inventory-dialog cmdb-import-dialog';
  importDialog.setAttribute('aria-labelledby', 'cmdbImportTitle');
  importDialog.innerHTML = `
    <div class="cmdb-inventory-dialog-head">
      <div><h2 id="cmdbImportTitle">Import inventory file</h2><p class="cmdb-inventory-muted">Replaces only the selected inventory; other categories stay unchanged.</p></div>
      <button type="button" data-close-import aria-label="Close import">Close</button>
    </div>
    <form id="cmdbInventoryImportForm" class="cmdb-inventory-import-form">
      <label for="cmdbImportType">Inventory</label>
      <select id="cmdbImportType"><option value="server">Servers</option><option value="network">Network Devices</option><option value="telecom">Telecom</option></select>
      <label for="cmdbImportFile">Replacement workbook (.xlsx)</label>
      <input id="cmdbImportFile" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required>
      <button type="submit" class="primary">Import and replace</button>
      <p id="cmdbImportStatus" class="cmdb-inventory-status" role="status" aria-live="polite"></p>
    </form>`;

  document.body.append(inventoryDialog, adminDialog, editDialog, addDialog, importDialog);
  bindDialogEvents();
}

function bindDialogEvents() {
  inventoryDialog.querySelector('[data-close-inventory]').addEventListener('click', () => inventoryDialog.close());
  adminDialog.querySelector('[data-close-admin]').addEventListener('click', () => adminDialog.close());
  document.getElementById('cmdbInventoryPrevious').addEventListener('click', () => loadBrowsePage(activePage - 1));
  document.getElementById('cmdbInventoryNext').addEventListener('click', () => loadBrowsePage(activePage + 1));
  document.getElementById('cmdbAdminPrevious').addEventListener('click', () => loadAdminPage(activePage - 1));
  document.getElementById('cmdbAdminNext').addEventListener('click', () => loadAdminPage(activePage + 1));
  document.getElementById('cmdbInventorySearch').addEventListener('input', event => {
    activeSearch = event.target.value.trim();
    loadBrowsePage(1);
  });
  document.getElementById('cmdbAdminSearch').addEventListener('input', event => {
    activeSearch = event.target.value.trim();
    loadAdminPage(1);
  });
  document.getElementById('cmdbAdminType').addEventListener('change', event => {
    activeType = event.target.value;
    activePage = 1;
    loadAdminPage(1);
  });
  document.getElementById('cmdbImportType').addEventListener('change', event => {
    activeType = event.target.value;
  });
  document.getElementById('cmdbInventoryImportForm').addEventListener('submit', importWorkbook);
  document.getElementById('cmdbInventoryEditToggle').addEventListener('click', toggleBrowseEditing);
  document.getElementById('cmdbInventoryAddRecord').addEventListener('click', openAddRecord);
  document.getElementById('cmdbInventoryExport').addEventListener('click', exportActiveInventoryCsv);
  importDialog.querySelector('[data-close-import]').addEventListener('click', () => importDialog.close());
}

function openImport() {
  document.getElementById('cmdbImportFile').value = '';
  setStatus('cmdbImportStatus', '');
  importDialog.showModal();
}

function updateEditToggleLabel() {
  const toggle = document.getElementById('cmdbInventoryEditToggle');
  if (toggle) toggle.textContent = editMode ? 'Done editing' : 'Edit records';
}

async function toggleBrowseEditing() {
  editMode = !editMode;
  updateEditToggleLabel();
  const add = document.getElementById('cmdbInventoryAddRecord');
  if (add) add.hidden = !editMode;
  await loadBrowsePage(activePage);
}

function isEditableRecord(record) {
  return editMode && !String(record.id).startsWith('legacy-');
}

function reviewCell(_record, cell) {
  return node('td', cell.value ?? '');
}

function rowActionsCell(record) {
  const actions = node('td', undefined, 'cmdb-inventory-row-actions');
  const validate = button(record.is_validated ? 'Validated' : 'Validate',
    () => validateRecord(record.id), '', `Validate ${record.name}`);
  validate.disabled = !!record.is_validated;
  if (record.is_validated) validate.classList.add('cmdb-validated-action');
  actions.append(
    button('Edit', () => editRecord(record), '', `Edit ${record.name}`),
    button('Delete', () => deleteRecord(record), 'danger', `Delete ${record.name}`),
    validate
  );
  return actions;
}

function validatedByCell(record) {
  return node('td', record.validated_by || '—');
}

function validatedOnCell(record) {
  const value = record.validated_at ? new Date(record.validated_at).toLocaleString() : '—';
  return node('td', value, 'cmdb-validated-time');
}

async function reloadActiveView() {
  allInventoryCache = null;
  if (adminDialog.open) await loadAdminPage(activePage);
  if (inventoryDialog.open) await loadBrowsePage(activePage);
  await refreshSummary();
}

async function refreshSummary() {
  try {
    const summary = await request('/summary');
    const counts = {
      server: Number(summary.server_count || 0),
      network: Number(summary.network_count || 0),
      telecom: Number(summary.telecom_count || 0)
    };
    for (const [id, value] of [
      ['inv-total-count', Number(summary.total_records || 0)],
      ['inv-server-count', counts.server],
      ['inv-network-count', counts.network],
      ['inv-telecom-count', counts.telecom]
    ]) {
      const target = document.getElementById(id);
      if (target) target.textContent = Number(value).toLocaleString();
    }
  } catch (error) {
    for (const id of ['inv-total-count', 'inv-server-count', 'inv-network-count', 'inv-telecom-count']) {
      const target = document.getElementById(id);
      if (target) target.textContent = 'Unavailable';
    }
    console.error('Database-backed CMDB inventory is unavailable:', error);
  }
}

function openInventory(type) {
  activeType = TYPES.includes(type) ? type : 'all';
  activePage = 1;
  activeSearch = '';
  editMode = false; activeRecordTemplate = null;
  const add = document.getElementById('cmdbInventoryAddRecord'); if (add) add.hidden = true;
  updateEditToggleLabel();
  document.getElementById('cmdbInventoryTitle').textContent = activeType === 'all' ? 'All Inventory' : TYPE_LABELS[activeType];
  document.getElementById('cmdbInventorySearch').value = '';
  updateEditToggleLabel();
  inventoryDialog.showModal();
  loadBrowsePage(1);
}

async function loadBrowsePage(page) {
  activePage = Math.max(1, page);
  if (activeType === 'all') {
    setStatus('cmdbInventoryStatus', 'Loading inventory…');
    try {
      const all = await loadAllInventoryRows();
      const query = activeSearch.toLocaleLowerCase();
      const filtered = all.items.filter(record =>
        [record.name, ...Object.values(record.data || {})].join(' ').toLocaleLowerCase().includes(query)
      );
      const start = (activePage - 1) * PAGE_SIZE;
      const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
      renderBrowseRows({
        items: filtered.slice(start, start + PAGE_SIZE),
        total: filtered.length,
        page: activePage,
        page_size: PAGE_SIZE,
        total_pages: totalPages,
        headers: all.headers
      });
      setStatus('cmdbInventoryStatus', filtered.length ? '' : 'No inventory records are available.');
    } catch (error) {
      setStatus('cmdbInventoryStatus', error.message, true);
    }
    return;
  }
  const query = new URLSearchParams({page: String(activePage), page_size: String(PAGE_SIZE)});
  query.set('inventory_type', activeType);
  if (activeSearch) query.set('search', activeSearch);
  setStatus('cmdbInventoryStatus', 'Loading inventory…');
  try {
    const result = await request(`/records?${query}`);
    renderBrowseRows(result);
    setStatus('cmdbInventoryStatus', result.total ? '' : 'No inventory records have been imported.');
  } catch (error) {
    const host = document.getElementById('cmdbInventoryTables');
    host.replaceChildren(node('p', error.message, 'cmdb-inventory-status'));
    setStatus('cmdbInventoryStatus', error.message, true);

  }
}

async function loadAllInventoryRows() {
  if (allInventoryCache) return allInventoryCache;
  const sources = await Promise.all(TYPES.map(async type => {
    const first = await request(`/records?inventory_type=${type}&page=1&page_size=100`);
    const items = [...first.items];
    for (let currentPage = 2; currentPage <= first.total_pages; currentPage += 1) {
      const next = await request(`/records?inventory_type=${type}&page=${currentPage}&page_size=100`);
      items.push(...next.items);
    }
    return {type, items, headers: first.headers?.[type] || {}};
  }));
  allInventoryCache = {
    items: sources.flatMap(source => source.items),
    headers: Object.fromEntries(sources.map(source => [source.type, source.headers]))
  };
  return allInventoryCache;
}

function telecomDisplayCells(record) {
  if (record.inventory_type !== 'telecom') return record.data;
  const normalizeHeader = value => String(value || '').trim().toLocaleLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ');
  const providerIndexes = record.data.map((cell, index) => normalizeHeader(cell.header) === 'provider' ? index : -1).filter(index => index >= 0);
  const lastProvider = providerIndexes.length > 1 ? providerIndexes[providerIndexes.length - 1] : -1;
  const hiddenHeaders = new Set(['hostname', 'host name', 'ip', 'ip address', 'model']);
  return record.data
    .filter((cell, index) => index !== lastProvider && !hiddenHeaders.has(normalizeHeader(cell.header)))
    .map(cell => ['serial no', 'serial no.', 'serial number'].includes(normalizeHeader(cell.header))
      ? {...cell, header: 'Circuit Id'}
      : cell);
}

function renderBrowseRows(result) {
  const host = document.getElementById('cmdbInventoryTables');
  host.replaceChildren();
  const groups = new Map();
  for (const record of result.items) {
    const key = `${record.inventory_type}:${record.source_sheet}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  }
  for (const records of groups.values()) {
    const first = records[0];
    const editable = records.some(isEditableRecord);
    if (activeType !== 'all' && !activeRecordTemplate) activeRecordTemplate = records[0];
    const section = node('section', undefined, 'cmdb-inventory-sheet');
    section.append(node('h3', activeType === 'all'
      ? `${TYPE_LABELS[first.inventory_type]} · ${first.source_sheet}`
      : first.source_sheet));
    const table = node('table', undefined, `cmdb-inventory-table${editable ? ' cmdb-admin-table' : ''}`);
    const head = node('thead');
    const headingRow = node('tr');
    const headers = telecomDisplayCells(first).map(cell => cell.header);
    headers.forEach(header => headingRow.append(node('th', header)));
    if (editable) { headingRow.append(node('th', 'Admin actions'), node('th', 'Validated by'), node('th', '◷ Validated on')); }
    head.append(headingRow);
    const body = node('tbody');
    for (const record of records) {
      const row = node('tr');
      const rowEditable = isEditableRecord(record);
      telecomDisplayCells(record).forEach(cell => row.append(rowEditable ? reviewCell(record, cell) : node('td', cell.value ?? '')));
      if (editable) row.append(rowEditable ? rowActionsCell(record) : node('td', ''), rowEditable ? validatedByCell(record) : node('td', ''), rowEditable ? validatedOnCell(record) : node('td', ''));
      body.append(row);
    }
    table.append(head, body);
    section.append(table);
    host.append(section);
  }
  document.getElementById('cmdbInventoryCount').textContent = `${Number(result.total).toLocaleString()} records`;
  setPager('cmdbInventoryPageLabel', 'cmdbInventoryPrevious', 'cmdbInventoryNext', result);
}

function openAdmin() {
  activePage = 1;
  activeSearch = '';
  document.getElementById('cmdbAdminSearch').value = '';
  adminDialog.showModal();
  loadAdminPage(1);
}


async function importWorkbook(event) {
  event.preventDefault();
  const file = document.getElementById('cmdbImportFile').files[0];
  if (!file) return;
  const type = document.getElementById('cmdbImportType').value;
  if (!window.confirm(`Replace the spreadsheet-owned ${TYPE_LABELS[type]} inventory with ${file.name}?`)) return;
  const formData = new FormData();
  formData.set('file', file);
  setStatus('cmdbImportStatus', 'Importing workbook…');
  try {
    const result = await request(`/${type}/import`, {method: 'POST', body: formData}, adminToken);
    document.getElementById('cmdbImportFile').value = '';
    setStatus('cmdbImportStatus', `${Number(result.imported_count).toLocaleString()} rows imported from ${result.source_file}.`);
    activeType = type;
    const adminType = document.getElementById('cmdbAdminType');
    if (adminType) adminType.value = type;
    await reloadActiveView();
  } catch (error) {
    setStatus('cmdbImportStatus', error.message, true);
  }
}

async function loadAdminPage(page) {
  activePage = Math.max(1, page);
  const query = new URLSearchParams({inventory_type: activeType, page: String(activePage), page_size: String(PAGE_SIZE)});
  if (activeSearch) query.set('search', activeSearch);
  setStatus('cmdbAdminStatus', 'Loading review records…');
  try {
    const result = await request(`/records?${query}`);
    renderAdminRows(result);
    setStatus('cmdbAdminStatus', result.total ? '' : 'No inventory records have been imported for this category.');
  } catch (error) {
    const host = document.getElementById('cmdbAdminTables');
    host.replaceChildren(node('p', error.message, 'cmdb-inventory-status'));
    setStatus('cmdbAdminStatus', error.message, true);
  }
}

function renderAdminRows(result) {
  const host = document.getElementById('cmdbAdminTables');
  host.replaceChildren();
  document.getElementById('cmdbAdminCount').textContent = `${Number(result.total).toLocaleString()} records`;
  const groups = new Map();
  for (const record of result.items) {
    if (!groups.has(record.source_sheet)) groups.set(record.source_sheet, []);
    groups.get(record.source_sheet).push(record);
  }
  const headersBySheet = result.headers?.[activeType] || {};
  for (const [sheetName, records] of groups) {
    const section = node('section', undefined, 'cmdb-inventory-sheet');
    section.append(node('h3', sheetName));
    const table = node('table', undefined, 'cmdb-inventory-table cmdb-admin-table');
    const head = node('thead');
    const heading = node('tr');
    const headers = activeType === 'telecom'
      ? telecomDisplayCells(records[0]).map(cell => cell.header)
      : (headersBySheet[sheetName] || records[0].data.map(cell => cell.header));
    headers.forEach(header => heading.append(node('th', header)));
    heading.append(node('th', 'Admin actions'), node('th', 'Validated by'), node('th', '◷ Validated on'));
    head.append(heading);
    const body = node('tbody');
    for (const record of records) {
      const row = node('tr');
      for (const cell of telecomDisplayCells(record)) row.append(node('td', cell.value ?? ''));
      row.append(rowActionsCell(record), validatedByCell(record), validatedOnCell(record));
      body.append(row);
    }
    table.append(head, body);
    section.append(table);
    host.append(section);
  }
  setPager('cmdbAdminPageLabel', 'cmdbAdminPrevious', 'cmdbAdminNext', result);
}

function setPager(labelId, previousId, nextId, result) {
  document.getElementById(labelId).textContent = `Page ${result.page} of ${result.total_pages}`;
  document.getElementById(previousId).disabled = result.page <= 1;
  document.getElementById(nextId).disabled = result.page >= result.total_pages;
}

function renderTableError(headId, bodyId, message, colspan) {
  if (headId) document.getElementById(headId).replaceChildren();
  const body = document.getElementById(bodyId);
  body.replaceChildren();
  const row = node('tr');
  row.append(node('td', message));
  row.firstElementChild.colSpan = colspan;
  body.append(row);
}

function editRecord(record) {
  editDialog.replaceChildren();
  const form = node('form');
  form.className = 'cmdb-inventory-edit-form';
  form.innerHTML = '<h2 id="cmdbEditTitle">Edit inventory record</h2>';
  const fields = {};
  record.data.forEach((cell, index) => {
    const label = node('label', cell.header);
    const input = node('textarea');
    input.id = `cmdbEditField-${index}`;
    label.htmlFor = input.id;
    input.rows = 2;
    input.value = cell.value === null || cell.value === undefined ? '' : String(cell.value);
    fields[index] = {input, previous: cell.value};
    form.append(label, input);
  });
  const status = node('p', '', 'cmdb-inventory-status');
  status.setAttribute('role', 'status');
  const actions = node('div', undefined, 'cmdb-inventory-actions');
  actions.append(button('Cancel', () => editDialog.close()), button('Save changes', async () => {
    const data = record.data.map((cell, index) => {
      const field = fields[index];
      const value = field.input.value;
      let cleanValue = value;
      if (!value && field.previous === null) cleanValue = null;
      else if (typeof field.previous === 'number' && value.trim() && Number.isFinite(Number(value))) cleanValue = Number(value);
      return {...cell, value: cleanValue};
    });
    const nameCell = data.find(cell => NAME_HEADERS.has(cell.header.trim().toLocaleLowerCase()) && cell.value);
    const name = nameCell ? String(nameCell.value) : record.name;
    actions.querySelectorAll('button').forEach(control => { control.disabled = true; });
    try {
      await request(`/records/${record.id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, data})
      }, adminToken);
      allInventoryCache = null;
      editDialog.close();
      await loadAdminPage(activePage);
    } catch (error) {
      status.textContent = error.message;
      actions.querySelectorAll('button').forEach(control => { control.disabled = false; });
    }
  }, 'primary'));
  form.addEventListener('submit', event => event.preventDefault());
  form.append(status, actions);
  editDialog.append(form);
  editDialog.showModal();
  editDialog.querySelector('textarea')?.focus();
}

function csvValue(value) {
  const text = value === null || value === undefined ? '' : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

async function allRecordsForType(type) {
  const first = await request(`/records?inventory_type=${type}&page=1&page_size=100`);
  const items = [...first.items];
  for (let page = 2; page <= first.total_pages; page += 1) {
    const next = await request(`/records?inventory_type=${type}&page=${page}&page_size=100`);
    items.push(...next.items);
  }
  return items;
}

async function exportActiveInventoryCsv() {
  if (!TYPES.includes(activeType)) return;
  const control = document.getElementById('cmdbInventoryExport');
  control.disabled = true; setStatus('cmdbInventoryStatus', 'Preparing CSV export…');
  try {
    const records = await allRecordsForType(activeType);
    if (!records.length) throw new Error('No records are available to export.');
    const projected = records.map(record => ({record, cells: telecomDisplayCells(record)}));
    const headers = [];
    projected.forEach(({cells}) => cells.forEach(cell => { if (!headers.includes(cell.header)) headers.push(cell.header); }));
    const lines = [[...headers, 'Validated by', 'Validated on'].map(csvValue).join(',')];
    projected.forEach(({record, cells}) => {
      const values = Object.fromEntries(cells.map(cell => [cell.header, cell.value]));
      lines.push([...headers.map(header => values[header] ?? ''), record.validated_by || '', record.validated_at || ''].map(csvValue).join(','));
    });
    const blob = new Blob(['\uFEFF' + lines.join('\r\n')], {type:'text/csv;charset=utf-8'});
    const url = URL.createObjectURL(blob); const link = document.createElement('a');
    const stamp = new Date().toISOString().slice(0,10);
    link.href = url; link.download = `${activeType}-inventory-${stamp}.csv`; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setStatus('cmdbInventoryStatus', `${records.length.toLocaleString()} records exported.`);
  } catch (error) { setStatus('cmdbInventoryStatus', error.message, true); }
  finally { control.disabled = false; }
}

function openAddRecord() {
  if (!activeRecordTemplate) {
    setStatus('cmdbInventoryStatus', 'No existing record is available to define the new row columns.', true);
    return;
  }
  addDialog.replaceChildren();
  const form = node('form'); form.className = 'cmdb-inventory-edit-form';
  form.innerHTML = '<h2 id="cmdbAddTitle">Add inventory record</h2>';
  const templateCells = telecomDisplayCells(activeRecordTemplate);
  const fields = [];
  templateCells.forEach((cell, index) => {
    const label = node('label', cell.header); const input = node('textarea'); input.rows = 2;
    input.id = `cmdbAddField-${index}`; label.htmlFor = input.id; fields.push({cell, input}); form.append(label, input);
  });
  const status = node('p', '', 'cmdb-inventory-status'); status.setAttribute('role', 'status');
  const actions = node('div', undefined, 'cmdb-inventory-actions');
  actions.append(button('Cancel', () => addDialog.close()), button('Add record', async () => {
    const data = fields.map(({cell, input}, index) => ({index, header: cell.header, value: input.value || null}));
    const nameCell = data.find(cell => NAME_HEADERS.has(cell.header.trim().toLocaleLowerCase()) && cell.value);
    const name = nameCell ? String(nameCell.value) : `${TYPE_LABELS[activeType]} manual record`;
    actions.querySelectorAll('button').forEach(control => { control.disabled = true; });
    try {
      await request('/records', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({inventory_type: activeType, source_sheet: activeRecordTemplate.source_sheet, name, data})
      }, adminToken);
      allInventoryCache = null; addDialog.close(); await loadBrowsePage(activePage); await refreshSummary();
    } catch (error) { status.textContent = error.message; actions.querySelectorAll('button').forEach(control => { control.disabled = false; }); }
  }, 'primary'));
  form.addEventListener('submit', event => event.preventDefault()); form.append(status, actions); addDialog.append(form); addDialog.showModal();
  addDialog.querySelector('textarea')?.focus();
}

const NAME_HEADERS = new Set(['computer name', 'host name', 'hostname', 'name', 'server name', 'serial no', 'serial number']);

async function validateRecord(id) {
  const statusId = adminDialog.open ? 'cmdbAdminStatus' : 'cmdbInventoryStatus';
  setStatus(statusId, 'Validating record…');
  try {
    const validated = await request(`/records/${id}/validate`, {method: 'POST'}, adminToken);
    if (!validated?.is_validated || !validated?.validated_at || !validated?.validated_by) {
      throw new Error('The server did not confirm validation.');
    }
    allInventoryCache = null;
    if (adminDialog.open) await loadAdminPage(activePage);
    if (inventoryDialog.open) await loadBrowsePage(activePage);
    await refreshSummary();
    setStatus(statusId, `Validated by ${validated.validated_by} on ${new Date(validated.validated_at).toLocaleString()}.`);
  } catch (error) {
    setStatus(statusId, error.message, true);
  }
}

async function deleteRecord(record) {
  if (!window.confirm(`Delete ${record.name} from spreadsheet inventory?`)) return;
  try {
    await request(`/records/${record.id}`, {method: 'DELETE'}, adminToken);
    allInventoryCache = null;
    await loadAdminPage(activePage);
    await refreshSummary();
  } catch (error) {
    setStatus('cmdbAdminStatus', error.message, true);
  }
}

function simplifyCmdbWorkspace() {
  const tiles = Array.from(document.querySelectorAll('[data-inventory-type]'));
  const totalTile = tiles.find(tile => tile.dataset.inventoryType === 'all' || tile.querySelector('#inv-total-count'));
  totalTile?.remove();
  const remaining = tiles.filter(tile => ['server', 'network', 'telecom'].includes(tile.dataset.inventoryType) && tile.isConnected);
  const container = remaining[0]?.parentElement;
  if (container) container.style.gridTemplateColumns = 'repeat(3, minmax(0, 1fr))';

  // Hide the legacy CMDB KPI/provenance/grid section and everything that follows it.
  const cmdbView = document.getElementById('view-cmdb');
  const legacyMarker = document.getElementById('cmdbTotalCisVal');
  if (cmdbView && legacyMarker) {
    let legacySection = legacyMarker;
    while (legacySection.parentElement && legacySection.parentElement !== cmdbView) {
      legacySection = legacySection.parentElement;
    }
    if (legacySection.parentElement === cmdbView) {
      let section = legacySection;
      while (section) {
        section.hidden = true;
        section.style.setProperty('display', 'none', 'important');
        section.setAttribute('aria-hidden', 'true');
        section = section.nextElementSibling;
      }
    } else {
      const legacyGrid = legacyMarker.closest('.kpi-grid');
      if (legacyGrid) legacyGrid.style.setProperty('display', 'none', 'important');
      const provenance = document.getElementById('cmdbProvenanceBar')?.closest('.charts-grid-2');
      if (provenance) provenance.style.setProperty('display', 'none', 'important');
    }
  }
}

export function initializeCmdbInventory() {
  if (initialized) return;
  initialized = true;
  buildDialogs();
  simplifyCmdbWorkspace();
  document.querySelectorAll('[data-inventory-type]').forEach(tile => {
    const open = () => openInventory(tile.dataset.inventoryType);
    tile.addEventListener('click', open);
    tile.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        open();
      }
    });
  });
  document.getElementById('cmdbInventoryAdminOpen')?.addEventListener('click', openAdmin);
  document.getElementById('cmdbInventoryImportOpen')?.addEventListener('click', openImport);
  window.filterCmdbByInventoryType = type => openInventory(type === 'servers' ? 'server' : type);
  refreshSummary();
}