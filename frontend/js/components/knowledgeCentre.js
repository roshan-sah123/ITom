const STORAGE_KEY = 'itom-knowledge-centre-v1';
const FILE_DB_NAME = 'itom-knowledge-files-v1';
const FILE_STORE = 'files';
const MAX_FILE_BYTES = 5 * 1024 * 1024;
let initialized = false;
let records = [];
let editingId = null;
let contentDialog;
let detailDialog;
let activeDetailUrl = null;
const CONTENT_CATEGORIES = ['SOP','Runbook','Technical Document','Diagram','Training Video','Training Presentation','User Guide','Policy / Standard','Troubleshooting Guide','Other'];

const el = (tag, text = '', className = '') => {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
};

function loadRecords() {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    return Array.isArray(value) ? value.map(record => ({...record, category: record.category || 'Other'})) : [];
  } catch { return []; }
}

function saveRecords() { localStorage.setItem(STORAGE_KEY, JSON.stringify(records)); }
function nextSerial() { return records.reduce((max, row) => Math.max(max, Number(row.serial) || 0), 0) + 1; }
function extension(name = '') { return name.includes('.') ? name.split('.').pop().toUpperCase() : 'FILE'; }

function openFileDatabase() {
  return new Promise((resolve, reject) => {
    if (!('indexedDB' in window)) return reject(new Error('This browser does not support persistent file storage.'));
    const request = indexedDB.open(FILE_DB_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(FILE_STORE)) request.result.createObjectStore(FILE_STORE);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('File storage could not be opened.'));
  });
}

async function storeFile(file) {
  const allowed = new Set([
    'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain', 'image/png', 'image/jpeg', 'image/webp',
    'video/mp4', 'video/webm', 'video/quicktime'
  ]);
  if (!file) throw new Error('Choose a file.');
  if (!allowed.has(file.type) || file.size > MAX_FILE_BYTES) {
    throw new Error('Use PDF, DOCX, XLSX, PPTX, TXT, PNG, JPEG, WebP, MP4, WebM or MOV up to 5 MB.');
  }
  const storageId = crypto.randomUUID();
  const database = await openFileDatabase();
  try {
    await new Promise((resolve, reject) => {
      const transaction = database.transaction(FILE_STORE, 'readwrite');
      transaction.objectStore(FILE_STORE).put(file, storageId);
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error || new Error('The file could not be stored.'));
      transaction.onabort = () => reject(transaction.error || new Error('The file upload was cancelled.'));
    });
  } finally { database.close(); }
  return {storageId, name:file.name, type:file.type, size:file.size};
}

async function storedBlob(file) {
  if (file?.data) {
    const match = /^data:([^;,]+);base64,(.+)$/s.exec(file.data);
    if (!match) throw new Error('File data is unavailable.');
    const bytes = atob(match[2]); const array = new Uint8Array(bytes.length);
    for (let index = 0; index < bytes.length; index += 1) array[index] = bytes.charCodeAt(index);
    return new Blob([array], {type:match[1]});
  }
  if (!file?.storageId) throw new Error('File data is unavailable.');
  const database = await openFileDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const request = database.transaction(FILE_STORE, 'readonly').objectStore(FILE_STORE).get(file.storageId);
      request.onsuccess = () => request.result ? resolve(request.result) : reject(new Error('The uploaded file was not found.'));
      request.onerror = () => reject(request.error || new Error('The uploaded file could not be read.'));
    });
  } finally { database.close(); }
}

async function deleteStoredFile(file) {
  if (!file?.storageId) return;
  const database = await openFileDatabase();
  try {
    await new Promise((resolve, reject) => {
      const transaction = database.transaction(FILE_STORE, 'readwrite');
      transaction.objectStore(FILE_STORE).delete(file.storageId);
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
    });
  } finally { database.close(); }
}

function blobUrl(dataUrl) {
  const match = /^data:([^;,]+);base64,(.+)$/s.exec(dataUrl || '');
  if (!match) throw new Error('File data is unavailable.');
  const bytes = atob(match[2]); const array = new Uint8Array(bytes.length);
  for (let index = 0; index < bytes.length; index += 1) array[index] = bytes.charCodeAt(index);
  return URL.createObjectURL(new Blob([array], {type:match[1]}));
}

async function openFile(record) {
  try {
    const blob = await storedBlob(record.file); const url = URL.createObjectURL(blob);
    const opened = window.open(url, '_blank', 'noopener');
    if (!opened) throw new Error('Allow pop-ups to view this file.');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (error) { setStatus(error.message, true); }
}

async function downloadFile(record) {
  try {
    const blob = await storedBlob(record.file); const url = URL.createObjectURL(blob); const link = document.createElement('a');
    link.href = url; link.download = record.file.name; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { setStatus(error.message, true); }
}

function setStatus(message, error = false) {
  const status = document.getElementById('knowledgeStatus');
  if (status) { status.textContent = message; status.dataset.error = String(error); }
}

function button(text, handler, className = '') {
  const control = el('button', text, className); control.type = 'button'; control.addEventListener('click', handler); return control;
}

function injectStyles() {
  if (document.getElementById('knowledgeCentreStyles')) return;
  const style = document.createElement('style'); style.id = 'knowledgeCentreStyles';
  style.textContent = `
    .knowledge-shell{padding:28px 30px;min-height:calc(100vh - 190px);background:linear-gradient(180deg,rgba(19,91,214,.045),transparent 260px)}.knowledge-head{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:22px;padding:22px 24px;border:1px solid var(--border-subtle,#dce4f0);border-radius:14px;background:linear-gradient(135deg,var(--surface-card,#fff),rgba(19,91,214,.08));box-shadow:0 12px 30px rgba(23,42,70,.06)}
    .knowledge-head h1{margin:0;font-size:29px;letter-spacing:-.02em}.knowledge-head p{margin:6px 0 0;color:var(--text-muted);max-width:680px}
    .knowledge-add{display:inline-flex;align-items:center;gap:9px;padding:11px 17px!important;border:1px solid #135bd6!important;border-radius:8px!important;background:#135bd6!important;color:white!important;box-shadow:0 8px 18px rgba(19,91,214,.22);transition:transform .16s ease,box-shadow .16s ease}.knowledge-add:hover{transform:translateY(-1px);box-shadow:0 10px 22px rgba(19,91,214,.28)}.knowledge-add span{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;background:white;color:#135bd6;font-size:18px;font-weight:800}
    .knowledge-card{background:var(--surface-card,#fff);border:1px solid var(--border-subtle,#dce4f0);border-radius:14px;padding:22px;box-shadow:0 12px 30px rgba(23,42,70,.055)}
    .knowledge-toolbar{display:flex;gap:10px;margin-bottom:16px}.knowledge-toolbar input{max-width:360px;width:100%;padding:10px 12px;border:1px solid var(--border-subtle,#dce4f0);border-radius:7px}
    .knowledge-table-wrap{overflow:auto}.knowledge-table{width:100%;min-width:1080px;border-collapse:collapse}.knowledge-table th:last-child,.knowledge-table td:last-child{min-width:230px;text-align:center}.knowledge-table th,.knowledge-table td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid var(--border-subtle,#dce4f0)}
    .knowledge-table th{color:var(--text-muted);font-size:11px;text-transform:uppercase;letter-spacing:.055em;background:rgba(96,113,138,.055)}.knowledge-table tbody tr{transition:background .15s ease}.knowledge-table tbody tr:hover{background:rgba(19,91,214,.035)}.knowledge-file{display:block;font-weight:700;color:var(--ink,#172a46)}.knowledge-category{display:inline-block;margin-top:6px;margin-inline-end:6px;padding:3px 8px;border-radius:999px;background:#e7f6ef;color:#087a50;font-size:11px;font-weight:700}.knowledge-type{display:inline-block;margin-top:6px;padding:3px 8px;border-radius:999px;background:#eaf2ff;color:#135bd6;font-size:11px;font-weight:700}
    .knowledge-state{display:inline-block;padding:4px 8px;border-radius:5px;background:#fff3d6;color:#805600;font-size:12px;font-weight:650}.knowledge-state.validated{background:#e5f5ed;color:#107650}
    .knowledge-actions{display:flex;gap:5px;flex-wrap:nowrap;align-items:center;justify-content:center;white-space:nowrap}.knowledge-actions button{padding:6px 8px;border-radius:6px;font-size:12px;min-width:auto}.knowledge-actions button:hover{border-color:#135bd6;color:#135bd6}.knowledge-danger{color:#b42332!important}.knowledge-empty{text-align:center;padding:46px 24px;color:var(--text-muted);border:1px dashed var(--border-subtle,#dce4f0);border-radius:10px;background:rgba(96,113,138,.025)}
    .knowledge-dialog{position:fixed;inset:50% auto auto 50%;transform:translate(-50%,-50%);margin:0;width:min(720px,calc(100% - 32px));background:#fff;color:#172a46;box-shadow:0 24px 60px rgba(23,42,70,.28);max-height:88vh;overflow:auto;border:1px solid #dce4f0;border-radius:12px;padding:24px}.knowledge-dialog::backdrop{background:rgba(15,23,42,.52);backdrop-filter:blur(2px)}.knowledge-dialog label{display:block;font-weight:650;margin:14px 0 6px}.knowledge-dialog input,.knowledge-dialog textarea,.knowledge-dialog select{width:100%;padding:10px 12px;border:1px solid #dce4f0;border-radius:7px}.knowledge-dialog textarea{min-height:110px}.knowledge-dialog-actions{display:flex;gap:9px;justify-content:flex-end;margin-top:18px}.knowledge-detail-hero{padding:17px 18px;border-radius:10px;background:linear-gradient(135deg,#eaf2ff,rgba(19,91,214,.055));border:1px solid #cbdcf7}.knowledge-detail-hero h2{margin:0 0 6px}.knowledge-detail-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.knowledge-detail-chip{padding:4px 9px;border-radius:999px;background:white;color:#135bd6;border:1px solid #cbdcf7;font-size:12px;font-weight:700}.knowledge-info-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}.knowledge-info-card{padding:13px;border:1px solid #dce4f0;border-radius:9px;background:#fff}.knowledge-info-card span{display:block;color:#60718a;font-size:11px;text-transform:uppercase;letter-spacing:.05em}.knowledge-info-card strong{display:block;margin-top:5px}.knowledge-description-card{margin-top:14px;padding:15px;border:1px solid #dce4f0;border-radius:9px;background:#fff}.knowledge-description-card h3{margin:0 0 7px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#60718a}.knowledge-detail{margin:0;white-space:pre-wrap;line-height:1.65}.knowledge-file-actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}.knowledge-file-actions button{padding:9px 13px;border-radius:7px}.knowledge-video-wrap{margin-top:16px;padding:12px;border:1px solid #dce4f0;border-radius:10px;background:#0f172a}.knowledge-video{display:block;width:100%;max-height:58vh;border-radius:7px;background:#000}.knowledge-video-note{margin:8px 0 0;color:#cbd5e1;font-size:12px}.knowledge-dialog [hidden]{display:none!important}.knowledge-status[data-error="true"]{color:#b42332}
  `; document.head.append(style);
}

function buildDialogs() {
  contentDialog = el('dialog', '', 'knowledge-dialog'); contentDialog.setAttribute('aria-labelledby','knowledgeDialogTitle');
  detailDialog = el('dialog', '', 'knowledge-dialog'); detailDialog.setAttribute('aria-labelledby','knowledgeDetailTitle');
  detailDialog.addEventListener('close', clearDetailMedia);
  document.body.append(contentDialog, detailDialog);
}

function openEditor(record = null) {
  editingId = record?.id || null; contentDialog.replaceChildren();
  const form = el('form'); const title = el('h2', record ? 'Edit content' : 'Add content'); title.id='knowledgeDialogTitle'; form.append(title);
  const serialLabel=el('label','Serial no'); const serial=el('input'); serial.readOnly=true; serial.value=record?.serial || nextSerial(); form.append(serialLabel,serial);
  const nameLabel=el('label','Content name *'); const name=el('input'); name.required=true; name.maxLength=160; name.value=record?.name || ''; form.append(nameLabel,name);
  const descriptionLabel=el('label','Description *'); const description=el('textarea'); description.required=true; description.maxLength=4000; description.value=record?.description || ''; form.append(descriptionLabel,description);
  const categoryLabel=el('label','Content category *'); const category=el('select'); category.required=true;
  category.append(el('option','Select a category')); category.firstElementChild.value='';
  CONTENT_CATEGORIES.forEach(value => { const option=el('option',value); option.value=value; category.append(option); });
  const savedCategory=record?.category || ''; category.value=CONTENT_CATEGORIES.includes(savedCategory) ? savedCategory : (savedCategory ? 'Other' : '');
  const otherCategoryLabel=el('label','Other category *'); const otherCategory=el('input'); otherCategory.maxLength=100; otherCategory.value=CONTENT_CATEGORIES.includes(savedCategory) ? '' : savedCategory; otherCategory.hidden=category.value!=='Other'; otherCategoryLabel.hidden=otherCategory.hidden;
  category.addEventListener('change',()=>{ const other=category.value==='Other'; otherCategory.hidden=!other; otherCategoryLabel.hidden=!other; otherCategory.required=other; if(!other)otherCategory.value=''; });
  if(category.value==='Other')otherCategory.required=true;
  form.append(categoryLabel,category,otherCategoryLabel,otherCategory);
  const fileLabel=el('label',record ? 'Replace file (optional)' : 'Add file *'); const file=el('input'); file.type='file'; file.accept='.pdf,.docx,.xlsx,.pptx,.txt,.png,.jpg,.jpeg,.webp,.mp4,.webm,.mov,video/mp4,video/webm,video/quicktime'; if(!record) file.required=true; form.append(fileLabel,file);
  const status=el('p','','knowledge-status'); const actions=el('div','','knowledge-dialog-actions');
  actions.append(button('Cancel',()=>contentDialog.close()),button(record?'Save changes':'Add content',async()=>{
    if(!form.reportValidity()) return;
    let storedFile=record?.file || null;
    try { if(file.files[0]) storedFile=await storeFile(file.files[0]); if(!storedFile) throw new Error('Choose a file.'); }
    catch(error){status.textContent=error.message;status.dataset.error='true';return;}
    const contentCategory=(category.value==='Other'?otherCategory.value.trim():category.value);
    if(!contentCategory){status.textContent='Select or enter a content category.';status.dataset.error='true';return;}
    const row={id:record?.id||crypto.randomUUID(),serial:record?.serial||nextSerial(),name:name.value.trim(),description:description.value.trim(),category:contentCategory,file:storedFile,validatedOn:null,validatedBy:''};
    if(record){
      const previousFile=record.file; records=records.map(item=>item.id===record.id?row:item); saveRecords();
      if(file.files[0] && previousFile?.storageId !== storedFile.storageId) deleteStoredFile(previousFile).catch(()=>{});
    }else{records.push(row);saveRecords();}
    contentDialog.close();renderTable();
  },'primary'));
  form.addEventListener('submit',event=>event.preventDefault()); form.append(status,actions);contentDialog.append(form);contentDialog.showModal();name.focus();
}

function isVideoRecord(record) {
  return String(record?.file?.type || '').startsWith('video/') || /\.(mp4|webm|mov)$/i.test(record?.file?.name || '');
}

function clearDetailMedia() {
  if (activeDetailUrl) URL.revokeObjectURL(activeDetailUrl);
  activeDetailUrl = null;
}

async function openDetails(record) {
  detailDialog.replaceChildren();
  const hero = el('div', '', 'knowledge-detail-hero');
  const title = el('h2', record.name); title.id = 'knowledgeDetailTitle';
  const subtitle = el('p', record.file.name, 'muted');
  hero.append(title, subtitle);
  const infoGrid = el('div', '', 'knowledge-info-grid');
  const typeCard = el('div', '', 'knowledge-info-card'); typeCard.append(el('span', 'Content type'), el('strong', record.category || 'Other'));
  const fileCard = el('div', '', 'knowledge-info-card'); fileCard.append(el('span', 'File format'), el('strong', extension(record.file.name)));
  infoGrid.append(typeCard, fileCard);
  const descriptionCard = el('section', '', 'knowledge-description-card');
  descriptionCard.append(el('h3', 'Description'), el('p', record.description, 'knowledge-detail'));
  const actions = el('div', '', 'knowledge-file-actions');
  detailDialog.append(hero, infoGrid, descriptionCard);
  if (isVideoRecord(record)) {
    try {
      clearDetailMedia();
      const blob = await storedBlob(record.file); activeDetailUrl = URL.createObjectURL(blob);
      const videoWrap = el('section', '', 'knowledge-video-wrap');
      const video = el('video', '', 'knowledge-video'); video.controls = true; video.playsInline = true; video.preload = 'metadata'; video.src = activeDetailUrl;
      video.setAttribute('aria-label', `Watch ${record.name}`);
      const note = el('p', 'Use the player controls for playback, volume, seeking and full screen.', 'knowledge-video-note');
      videoWrap.append(video, note); detailDialog.append(videoWrap);
    } catch (error) { detailDialog.append(el('p', `Video cannot be played: ${error.message}`, 'knowledge-status')); }
    actions.append(button('Download video', () => downloadFile(record)), button('Close', () => { clearDetailMedia(); detailDialog.close(); }));
  } else {
    actions.append(button('View file', () => openFile(record), 'primary'), button('Download file', () => downloadFile(record)), button('Close', () => detailDialog.close()));
  }
  detailDialog.append(actions);
  detailDialog.showModal();
}

function validateRecord(record) { const actor=prompt('Validated by');if(!actor?.trim())return;record.validatedOn=new Date().toISOString();record.validatedBy=actor.trim();saveRecords();renderTable(); }
function deleteRecord(record) { if(!confirm(`Delete ${record.name}?`))return;records=records.filter(item=>item.id!==record.id);saveRecords();deleteStoredFile(record.file).catch(()=>{});renderTable(); }

function renderTable() {
  setStatus('');
  const body=document.getElementById('knowledgeRows');body.replaceChildren();const query=document.getElementById('knowledgeSearch').value.trim().toLowerCase();
  const visible=records.filter(row=>[row.name,row.description,row.category,row.file.name].join(' ').toLowerCase().includes(query));
  document.getElementById('knowledgeEmpty').hidden=visible.length!==0;
  visible.forEach(record=>{const row=el('tr');const state=el('span',record.validatedOn?'Validated':'Pending','knowledge-state'+(record.validatedOn?' validated':''));
    const fileCell=el('td');fileCell.append(el('span',record.name,'knowledge-file'));
    const contentType=el('td',record.category || 'Other');
    const validation=el('td');validation.append(state);const actions=el('td','','knowledge-actions');actions.append(button('Open',()=>openDetails(record)),button('Edit',()=>openEditor(record)),button('Delete',()=>deleteRecord(record),'knowledge-danger'),button(record.validatedOn?'Validated':'Validate',()=>validateRecord(record)));actions.lastChild.disabled=!!record.validatedOn;
    [record.serial,fileCell,contentType,record.description,validation,record.validatedOn?new Date(record.validatedOn).toLocaleString():'—',record.validatedBy||'—',actions].forEach(value=>row.append(value instanceof Node?value:el('td',String(value))));body.append(row);});
}

export function renderKnowledgeCentre() {
  const view = document.getElementById('view-knowledge');
  if (!view) {
    console.error('Knowledge Centre view container was not found.');
    return;
  }
  try {
    const viewport = document.querySelector('.main-viewport');
    if (viewport && view.parentElement === viewport && viewport.firstElementChild !== view) viewport.insertBefore(view, viewport.firstElementChild);
    document.querySelectorAll('.home-module-card, .module-card-v2, .coming-soon-panel').forEach(card => {
      const title = card.querySelector('h3, h1, strong')?.textContent?.trim();
      if (title === 'Knowledge Centre' && !view.contains(card)) {
        card.dataset.knowledgeLegacyHidden = 'true';
        card.style.setProperty('display', 'none', 'important');
      }
    });
    injectStyles();
    const needsBuild = !initialized || !document.getElementById('knowledgeRows') || !document.getElementById('knowledgeAdd');
    if (needsBuild) {
      const shell = el('div', '', 'knowledge-shell');
      shell.innerHTML = `<div class="knowledge-head"><div><h1>Knowledge Centre</h1><p>Manage guides, SOPs, training files and reference documents.</p></div><button type="button" class="knowledge-add" id="knowledgeAdd"><span aria-hidden="true">+</span>Add content</button></div><section class="knowledge-card"><div class="knowledge-toolbar"><input id="knowledgeSearch" type="search" placeholder="Search content" aria-label="Search content"></div><p id="knowledgeStatus" class="knowledge-status" role="status"></p><div class="knowledge-table-wrap"><table class="knowledge-table"><thead><tr><th>Serial no</th><th>Content name</th><th>Content type</th><th>Description</th><th>Validation</th><th>Validated on</th><th>Validated by</th><th>Actions</th></tr></thead><tbody id="knowledgeRows"></tbody></table><div id="knowledgeEmpty" class="knowledge-empty" hidden>No content uploaded. Use Add content to upload the first document.</div></div></section>`;
      view.replaceChildren(shell);
      records = loadRecords();
      if (!contentDialog?.isConnected || !detailDialog?.isConnected) buildDialogs();
      document.getElementById('knowledgeAdd').addEventListener('click', () => openEditor());
      document.getElementById('knowledgeSearch').addEventListener('input', renderTable);
      initialized = true;
    }
    renderTable();
  } catch (error) {
    console.error('Knowledge Centre initialization failed:', error);
    const fallback = el('div', '', 'knowledge-shell');
    fallback.innerHTML = `<section class="knowledge-card"><h1>Knowledge Centre</h1><p class="knowledge-status" data-error="true">Knowledge Centre could not initialize: ${String(error?.message || error)}</p><button type="button" class="primary" id="knowledgeRetry">Retry</button></section>`;
    view.replaceChildren(fallback);
    document.getElementById('knowledgeRetry')?.addEventListener('click', () => { initialized = false; renderKnowledgeCentre(); });
  }
}

