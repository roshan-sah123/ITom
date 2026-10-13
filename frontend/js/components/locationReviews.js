import { itomApi } from '../api.js?v=9';
import { escapeHtml, formatNumber } from '../utils.js';

const statusName = status => ({PENDING:'Pending',APPROVED:'Approved',REJECTED:'Rejected'}[status] || 'Pending');
const statusTone = status => status === 'APPROVED' ? 'healthy' : status === 'REJECTED' ? 'critical' : 'warning';
const reviewedAt = raw => raw ? new Date(/Z$|[+-]\d\d:\d\d$/.test(raw) ? raw : raw+'Z').toLocaleString() : 'Not recorded';

export function openLocationReviews(host, onClose) {
  let page=1, data=null, selected=null, saving=false, changed=false, generation=0, historyGeneration=0, closed=false, timer;
  host.hidden=false;
  host.innerHTML=`<div class="location-health-heading"><div><h3>Location mapping review</h3><p>Review a device prefix or source alias. Saving re-evaluates device assignments from that source.</p></div><button id="reviewClose" type="button" class="btn-filter-reset">← Back to location health</button></div>
    <p class="location-health-note">Approved rules confirm an assignment. Pending assignments need review and cannot supply a location score. Rejected rules do not assign a location. Existing legacy approvals have no recorded reviewer/date.</p>
    <p id="reviewCounts" class="location-health-note" role="status"></p>
    <div class="grid-toolbar"><label>Status<select id="reviewStatus" class="filter-select"><option value="PENDING">Pending</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option><option value="">All statuses</option></select></label><label>Source<select id="reviewSource" class="filter-select"><option value="">All sources</option><option value="INTUNE">Intune</option><option value="SOLARWINDS">SolarWinds</option></select></label><label>Search<input id="reviewSearch" type="search" class="filter-select" placeholder="Prefix, alias or location"></label><button id="reviewReload" type="button" class="btn-filter-reset">Reload rules</button></div>
    <div class="grid-scroll"><table class="itom-table"><caption class="sr-only">Location mapping review queue</caption><thead><tr><th scope="col">Source key</th><th scope="col">Location</th><th scope="col">Approval</th><th scope="col">Linked devices</th><th scope="col">Reviewer</th><th scope="col">Last review</th></tr></thead><tbody id="reviewRules"></tbody></table></div>
    <div class="grid-footer"><button id="reviewPrev" type="button" class="btn-filter-reset">Previous</button><span id="reviewPage"></span><button id="reviewNext" type="button" class="btn-filter-reset">Next</button></div>
    <p class="location-health-note">Linked devices use current assignment provenance. A review can also affect overlapping source fields. Human reviewer names are recorded as entered; this local portal has no sign-in.</p>
    <section id="reviewEditor" class="location-review-editor" hidden aria-label="Mapping decision"></section>`;
  const element=id=>host.querySelector('#'+id);
  element('reviewClose').onclick=()=>{ if(saving)return;clearTimeout(timer);generation++;historyGeneration++;closed=true;host.hidden=true;onClose(changed); };
  element('reviewReload').onclick=()=>{page=1;loadQueue();};
  for (const id of ['reviewStatus','reviewSource']) element(id).onchange=()=>{page=1;loadQueue();};
  element('reviewSearch').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{page=1;loadQueue();},250);};
  element('reviewPrev').onclick=()=>{page--;loadQueue();};
  element('reviewNext').onclick=()=>{page++;loadQueue();};

  async function loadQueue() {
    const request=++generation;
    const params={page,page_size:25,search:element('reviewSearch').value};
    if(element('reviewStatus').value)params.status=element('reviewStatus').value;
    if(element('reviewSource').value)params.source=element('reviewSource').value;
    element('reviewRules').innerHTML='<tr><td colspan="6">Loading review queue…</td></tr>';
    element('reviewPrev').disabled=true;element('reviewNext').disabled=true;
    try {
      const response=await itomApi.getLocationReviewRules(params);
      if(request!==generation || host.hidden || closed)return;
      data=response.data;
      if(page>data.total_pages && page>1){page=data.total_pages;return loadQueue();}
      element('reviewCounts').textContent=`All enabled rules: ${formatNumber(data.counts.PENDING)} pending · ${formatNumber(data.counts.APPROVED)} approved · ${formatNumber(data.counts.REJECTED)} rejected${data.write_enabled ? '' : ' · Read only: decisions require the local portal'}`;
      element('reviewRules').innerHTML=data.items.length ? data.items.map(rule=>`<tr><td><button type="button" class="table-location-link" data-rule="${escapeHtml(rule.id)}">${escapeHtml(rule.match_key)}</button><small class="review-source">${escapeHtml(rule.source_system)}</small></td><td>${escapeHtml(rule.location_name || 'Not assigned')}</td><td><span class="status-pill status-${statusTone(rule.approval_status)}">${statusName(rule.approval_status)}</span>${rule.legacy_approval ? '<small class="review-source">Legacy approval</small>' : ''}</td><td>${formatNumber(rule.devices)}</td><td>${escapeHtml(rule.reviewed_by || 'Not recorded')}</td><td>${escapeHtml(reviewedAt(rule.reviewed_at))}</td></tr>`).join('') : '<tr><td colspan="6">No rules match these filters.</td></tr>';
      host.querySelectorAll('button[data-rule]').forEach(button=>button.onclick=()=>renderEditor(data.items.find(rule=>rule.id===button.dataset.rule)));
      element('reviewPage').textContent=`${formatNumber(data.total)} rules · Page ${page} of ${data.total_pages}`;
      element('reviewPrev').disabled=page<=1;element('reviewNext').disabled=page>=data.total_pages;
    } catch(error) {
      if(request!==generation || host.hidden || closed)return;
      element('reviewRules').innerHTML='<tr><td colspan="6" class="inline-error">Review queue unavailable. Reload rules to retry.</td></tr>';
      element('reviewCounts').textContent='Review counts are unavailable; this does not mean there are no pending rules.';
    }
  }

  async function loadHistory(id) {
    const request=++historyGeneration;
    try {
      const response=await itomApi.getLocationReviewHistory(id);
      if(request!==historyGeneration || selected?.id!==id || host.hidden || closed)return;
      const rows=response.data.items;
      element('reviewHistory').innerHTML=rows.length ? `<h4>Decision history</h4><ol>${rows.map(row=>`<li><strong>${escapeHtml(row.before.approval_status)} → ${escapeHtml(row.after.approval_status)}</strong><p>${escapeHtml(row.reviewed_by)} · ${escapeHtml(reviewedAt(row.reviewed_at))}</p><p>Location: ${escapeHtml(row.before.location_name || 'Not assigned')} → ${escapeHtml(row.after.location_name || 'Not assigned')}</p>${row.comment ? `<p>${escapeHtml(row.comment)}</p>` : ''}</li>`).join('')}</ol>` : '<p>No recorded decisions yet. Legacy approvals have no historical reviewer/date.</p>';
    } catch(error) { if(request===historyGeneration && selected?.id===id && !host.hidden && !closed)element('reviewHistory').textContent='Decision history unavailable.'; }
  }

  function renderEditor(rule) {
    if(saving)return;
    selected=rule;
    const editor=element('reviewEditor');editor.hidden=false;
    editor.innerHTML=`<h3 id="reviewEditorTitle" tabindex="-1">Review ${escapeHtml(rule.match_key)}</h3><p>${escapeHtml(rule.source_system)} · ${formatNumber(rule.devices)} linked devices</p><p id="reviewLastDecision">${statusName(rule.approval_status)} · ${escapeHtml(rule.reviewed_by || 'Reviewer not recorded')} · ${escapeHtml(reviewedAt(rule.reviewed_at))}</p>${rule.review_note ? `<p class="location-review-note">Source note: ${escapeHtml(rule.review_note)}</p>` : ''}
      <form id="reviewForm" class="location-review-form"><label>Reporting location<select id="reviewLocation" class="filter-select"><option value="">Not assigned</option>${data.locations.map(location=>`<option value="${escapeHtml(location.id)}">${escapeHtml(location.name)}</option>`).join('')}</select></label><label>Approval status<select id="reviewDecision" class="filter-select"><option value="PENDING">Pending</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option></select></label><label>Reviewer name<input id="reviewReviewer" class="filter-select" required maxlength="128" autocomplete="name" placeholder="Your name"></label><label>Review reason<textarea id="reviewComment" maxlength="512" rows="3" placeholder="Required for rejection; optional for approval"></textarea></label><p class="location-health-note">The review date is recorded by the server when you save. Source notes are informational and do not set approval.</p><button id="reviewSave" type="submit" class="btn-filter-reset" ${data.write_enabled ? '' : 'disabled'}>Save review</button></form><p id="reviewMessage" role="status"></p><div id="reviewHistory"></div>`;
    element('reviewLocation').value=rule.location_id || '';
    element('reviewDecision').value=rule.approval_status;
    element('reviewDecision').onchange=()=>{element('reviewComment').required=element('reviewDecision').value==='REJECTED';};
    element('reviewComment').required=rule.approval_status==='REJECTED';
    element('reviewForm').onsubmit=save;
    element('reviewEditorTitle').focus({preventScroll:true});
    editor.scrollIntoView({behavior:'instant',block:'start'});
    loadHistory(rule.id);
  }

  async function save(event) {
    event.preventDefault();if(saving)return;
    if(element('reviewDecision').value==='APPROVED' && !element('reviewLocation').value){element('reviewMessage').textContent='Choose a reporting location before approving.';return;}
    const body={status:element('reviewDecision').value,reviewer:element('reviewReviewer').value.trim(),location_id:element('reviewLocation').value || null,expected_revision:selected.revision,comment:element('reviewComment').value.trim() || null};
    saving=true;element('reviewSave').disabled=true;element('reviewClose').disabled=true;
    element('reviewMessage').textContent='Saving decision and refreshing assignments…';
    try {
      const response=await itomApi.saveLocationReview(selected.id,body);
      changed=true;selected=response.data.rule;
      element('reviewMessage').textContent=`${statusName(selected.approval_status)}. ${formatNumber(response.data.changed_assignments)} device assignments refreshed.`;
      element('reviewLastDecision').textContent=`${statusName(selected.approval_status)} · ${selected.reviewed_by} · ${reviewedAt(selected.reviewed_at)}`;
      await loadQueue();await loadHistory(selected.id);
    } catch(error) {
      element('reviewMessage').textContent=error.status===409 ? 'The rule changed or a sync/review is running. Reload rules and reopen the mapping before retrying.' : error.status===422 ? 'Check the reviewer name, location and rejection reason. The decision was not saved.' : error.status===403 ? 'Decisions are available only from this local portal.' : 'The decision could not be saved. Reload the queue to verify its status before retrying.';
    } finally { saving=false;element('reviewSave').disabled=!data?.write_enabled;element('reviewClose').disabled=false; }
  }

  loadQueue();
}
