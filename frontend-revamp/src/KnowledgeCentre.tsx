import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { WorkspaceDialog } from "./WorkspaceDialog";
import {
  KNOWLEDGE_ACCEPT, KNOWLEDGE_CATEGORIES, deleteKnowledge, fileFormat, filterKnowledge,
  knowledgeBlob, knowledgeSummary, listKnowledge, saveKnowledge, validateKnowledgeFile, validateKnowledge,
} from "./knowledge";
import type { KnowledgeDraft, KnowledgeRecord, KnowledgeStatus } from "./knowledge";

const emptyDraft = (): KnowledgeDraft => ({ name: "", description: "", category: "Runbook" });
const message = (error: unknown) => error instanceof Error ? error.message : String(error);
const dateLabel = (value: string | null) => value ? new Date(value).toLocaleString() : "Pending review";

function KnowledgeIcon({ kind }: { kind: "total" | "validated" | "pending" | "file" | "video" | "search" }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" width="18" height="18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {kind === "total" ? <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v7c0 1.66 3.58 3 8 3s8-1.34 8-3V5M4 12v7c0 1.66 3.58 3 8 3s8-1.34 8-3v-7" /></>
      : kind === "validated" ? <path d="m5 12 4 4L19 6" /> : kind === "pending" ? <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>
        : kind === "video" ? <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m10 9 5 3-5 3z" /></>
          : kind === "search" ? <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>
            : <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h6" /></>}
  </svg>;
}

function KnowledgeDetails({ record, onClose }: { record: KnowledgeRecord; onClose: () => void }) {
  const [url, setUrl] = useState("");
  const downloadOnly = /\.(pdf|docx|txt)$/i.test(record.file.name);
  const [viewFile, setViewFile] = useState(record.file.type.startsWith("video/"));
  const [error, setError] = useState("");
  useEffect(() => {
    if (downloadOnly) return;
    let cancelled = false, objectUrl = "";
    void knowledgeBlob(record).then(async blob => {
      objectUrl = URL.createObjectURL(blob);
      if (!cancelled) { setUrl(objectUrl); }
      else URL.revokeObjectURL(objectUrl);
    }).catch(reason => { if (!cancelled) setError(message(reason)); });
    return () => { cancelled = true; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [record, downloadOnly]);
  const type = record.file.type;
  return <WorkspaceDialog title={record.name} subtitle={record.file.name} icon={<KnowledgeIcon kind={record.file.type.startsWith("video/") ? "video" : "file"} />} wide className="knowledge-dialog" onClose={onClose}>
    <div className="vendor-detail-metadata">
      <div><span>Content type</span><strong>{record.category}</strong></div>
      <div><span>File format</span><strong>{fileFormat(record.file.name)}</strong></div>
    </div>
    <section className="knowledge-description"><h3>Description</h3><p>{record.description}</p></section>
    {error && <p role="alert" className="data-notice">{error}</p>}
    {downloadOnly && <p>Download only. Document contents are not scanned or previewed; open only trusted files.</p>}
    {!downloadOnly && viewFile && url && <section className="knowledge-preview" aria-label="File preview">
      {type.startsWith("video/") ? <>
        <video src={url} controls playsInline preload="metadata" aria-label={`Watch ${record.name}`}
          onError={() => setError("This browser cannot play this video format. Download the video to open it in a supported player.")} />
        <p>Use the player controls for playback, volume, seeking and full screen.</p>
      </> : type.startsWith("image/") ? <img src={url} alt={record.name} />
        : <p>This file format needs a compatible application. Download the file to view it.</p>}
    </section>}
    <div className="knowledge-actions">
      {!downloadOnly && <button type="button" className="button button--primary" disabled={!url} onClick={() => setViewFile(true)}>View file</button>}
      <a className="button button--secondary" href={downloadOnly ? record.file.url : url || undefined} download={record.file.name}
        aria-disabled={!downloadOnly && !url} onClick={event => { if (!downloadOnly && !url) event.preventDefault(); }}>{type.startsWith("video/") ? "Download video" : "Download file"}</a>
      <button type="button" className="button button--secondary" onClick={onClose}>Close</button>
    </div>
  </WorkspaceDialog>;
}

export function KnowledgeCentre() {
  const [records, setRecords] = useState<KnowledgeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<KnowledgeStatus>("All");
  const [view, setView] = useState<"Grid" | "List">("Grid");
  const [editor, setEditor] = useState<{ original: KnowledgeRecord | null; requestId: string } | null>(null);
  const [draft, setDraft] = useState<KnowledgeDraft>(emptyDraft);
  const [otherCategory, setOtherCategory] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState("");
  const [details, setDetails] = useState<KnowledgeRecord | null>(null);
  const [action, setAction] = useState<{ kind: "validate" | "delete"; record: KnowledgeRecord } | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [adminKey, setAdminKey] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    let controller: AbortController | null = null;
    const load = () => {
      controller?.abort();
      const current = new AbortController();
      controller = current;
      void listKnowledge(current.signal).then(rows => { if (active && !current.signal.aborted) { setRecords(rows); setError(""); } })
        .catch(reason => { if (active && !current.signal.aborted) setError(message(reason)); })
        .finally(() => { if (active && !current.signal.aborted) setLoading(false); });
    };
    load();
    globalThis.addEventListener("itom-knowledge-changed", load);
    globalThis.addEventListener("focus", load);
    return () => {
      active = false; controller?.abort();
      globalThis.removeEventListener("itom-knowledge-changed", load);
      globalThis.removeEventListener("focus", load);
    };
  }, [refresh]);

  function edit(record: KnowledgeRecord | null) {
    setAdminKey("");
    const known = !record || KNOWLEDGE_CATEGORIES.some(value => value === record.category);
    setDraft(record ? {
      name: record.name, description: record.description, category: known ? record.category : "Other",
    } : emptyDraft());
    setOtherCategory(known ? "" : record!.category);
    setFile(null); setDialogError(""); setEditor({ original: record, requestId: crypto.randomUUID().replaceAll("-", "") }); setNotice("");
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!editor) return;
    setBusy(true); setDialogError("");
    try {
      await saveKnowledge({ ...draft, category: draft.category === "Other" ? otherCategory : draft.category }, file, editor.original, editor.requestId, adminKey);
      setEditor(null); setAdminKey(""); setNotice("Content saved in the portal database.");
    } catch (reason) { setDialogError(message(reason)); }
    finally { setBusy(false); }
  }
  async function performAction(event: FormEvent) {
    event.preventDefault();
    if (!action) return;
    setBusy(true); setDialogError("");
    try {
      if (action.kind === "delete") await deleteKnowledge(action.record, adminKey);
      else await validateKnowledge(action.record, reviewer, adminKey);
      setNotice(action.kind === "delete" ? "Content and its file deleted." : "Content validated. Reviewer name is self-reported.");
      setAction(null); setAdminKey("");
    } catch (reason) { setDialogError(message(reason)); }
    finally { setBusy(false); }
  }
  const summary = knowledgeSummary(records), visible = filterKnowledge(records, search, status);
  const badge = (row: KnowledgeRecord) => <span className={`vendor-validation vendor-validation--${row.validatedOn ? "validated" : "pending"}`}>{row.validatedOn ? "Validated" : "Pending"}</span>;
  const actions = (row: KnowledgeRecord) => <div className="knowledge-actions">
    <button type="button" className="button button--primary" onClick={() => setDetails(row)}>Open</button>
    <button type="button" className="button button--secondary" onClick={() => edit(row)}>Edit</button>
    <button type="button" className="button button--secondary vendor-delete" onClick={() => { setAdminKey(""); setDialogError(""); setAction({ kind: "delete", record: row }); }}>Delete</button>
    <button type="button" className="button button--secondary" disabled={!!row.validatedOn}
      onClick={() => { setReviewer(""); setAdminKey(""); setDialogError(""); setAction({ kind: "validate", record: row }); }}>{row.validatedOn ? "Validated" : "Validate"}</button>
  </div>;
  return <div className="knowledge-workspace">
    <section className="workspace-hero knowledge-hero">
      <div><p className="eyebrow">SHARED OPERATIONS KNOWLEDGE</p><h1>Knowledge workspace</h1>
        <p className="hero__subtitle">Find, govern, and maintain trusted operational content in one place.</p></div>
      <button type="button" className="button" disabled={loading || !!error} onClick={() => edit(null)}>+ Add content</button>
    </section>
    <div className="knowledge-actions">
      <button type="button" className="button button--secondary" disabled={busy || loading} onClick={() => setRefresh(value => value + 1)}>Refresh library</button>
    </div>
    {error && <p role="alert" className="data-notice">{error} <button type="button" className="text-button" onClick={() => setRefresh(value => value + 1)}>Retry database</button></p>}
    {notice && <p role="status" className="vendor-notice">{notice}</p>}
    <section className="knowledge-summary" aria-label="Content summary">
      {([
        ["Total content", summary.total, "Across the knowledge library", "total"],
        ["Validated", summary.validated, "Ready for operational use", "validated"],
        ["Pending review", summary.pending, "Awaiting validation", "pending"],
      ] as const).map(([label, count, note, kind]) => <article className={`panel knowledge-summary-card knowledge-summary-card--${kind}`} key={label}>
        <span className="knowledge-summary-icon"><KnowledgeIcon kind={kind} /></span>
        <div><span>{label}</span><strong>{loading || error ? "—" : count}</strong><p>{note}</p></div>
      </article>)}
    </section>
    <section className="panel knowledge-library" aria-label="Content library" aria-busy={loading}>
      <div className="knowledge-library-heading">
        <div><p className="eyebrow">CONTENT LIBRARY</p><h2>Operational resources</h2></div>
        <label className="knowledge-search"><KnowledgeIcon kind="search" /><input aria-label="Search knowledge content" type="search" placeholder="Search content, type, or file" maxLength={200}
          value={search} onChange={event => setSearch(event.target.value)} /></label>
      </div>
      <div className="knowledge-library-toolbar">
        <div className="knowledge-tabs" aria-label="Validation filter">{(["All", "Validated", "Pending"] as const).map(value =>
          <button type="button" key={value} aria-pressed={status === value} onClick={() => setStatus(value)}>{value}</button>)}</div>
        <div><span>{error ? "Storage unavailable" : loading ? "Loading library" : `Showing ${visible.length} of ${records.length}`}</span><div role="group" aria-label="Content view">
          {(["Grid", "List"] as const).map(value => <button type="button" key={value} aria-pressed={view === value} onClick={() => setView(value)}>{value}</button>)}
        </div></div>
      </div>
      {loading ? <div className="empty-state">Loading portal content…</div> : error ? <div className="empty-state">Content library unavailable. Retry the database connection.</div> : visible.length === 0 ?
        <div className="empty-state">{records.length ? "No content matches these filters." : "No knowledge content yet. Add your first operational resource."}</div> :
        view === "Grid" ? <div className="knowledge-grid">{visible.map(row => <article className="knowledge-card" key={row.id}>
          <div className="knowledge-card-heading"><span className="knowledge-file-icon"><KnowledgeIcon kind={row.file.type.startsWith("video/") ? "video" : "file"} /></span>
            <div><span>{row.category}</span><h3>{row.name}</h3><small>{row.file.name} · {fileFormat(row.file.name)}</small></div>{badge(row)}</div>
          <p className="knowledge-card-description">{row.description}</p>
          <div className="knowledge-card-review"><div><span>Validated by</span><strong>{row.validatedBy || "Not assigned"}</strong></div>
            <div><span>Last validation</span><strong>{dateLabel(row.validatedOn)}</strong></div></div>
          {actions(row)}
        </article>)}</div> : <div className="vendor-table-scroll"><table className="vendor-table knowledge-table">
          <thead><tr>{["S.NO", "CONTENT NAME", "CONTENT TYPE", "DESCRIPTION", "VALIDATION", "VALIDATED ON", "VALIDATED BY", "ACTIONS"].map(label => <th key={label}>{label}</th>)}</tr></thead>
          <tbody>{visible.map(row => <tr key={row.id}><td>{row.serial}</td><td><strong>{row.name}</strong><small>{row.file.name}</small></td>
            <td>{row.category}</td><td className="knowledge-table-description">{row.description}</td><td>{badge(row)}</td>
            <td>{dateLabel(row.validatedOn)}</td><td>{row.validatedBy || "Not assigned"}</td><td>{actions(row)}</td></tr>)}</tbody>
        </table></div>}
    </section>
    {editor && <WorkspaceDialog title={editor.original ? "Edit content" : "Add content"} subtitle="Complete the content details below." icon={<KnowledgeIcon kind="file" />} wide busy={busy} className="knowledge-dialog" onClose={() => { setEditor(null); setAdminKey(""); }}>
      <form onSubmit={event => void submit(event)}><fieldset disabled={busy} className="knowledge-form">
        <div className="knowledge-form-grid">
          <label>Content name *<input aria-label="Content name *" required maxLength={160} value={draft.name} placeholder="Enter content name" onChange={event => setDraft({ ...draft, name: event.target.value })} /></label>
          <label>Content type *<select aria-label="Content type *" value={draft.category} onChange={event => setDraft({ ...draft, category: event.target.value })}>{KNOWLEDGE_CATEGORIES.map(value => <option key={value}>{value}</option>)}</select></label>
          {draft.category === "Other" && <label className="knowledge-form-full">Other category *<input aria-label="Other category *" required maxLength={100} value={otherCategory} onChange={event => setOtherCategory(event.target.value)} /></label>}
          <label className="knowledge-form-full">Description *<textarea aria-label="Description *" required maxLength={4000} placeholder="Describe this content" value={draft.description} onChange={event => setDraft({ ...draft, description: event.target.value })} /></label>
          <label>Upload file {editor.original ? "(replace optional)" : "*"}<input aria-label={`Upload file ${editor.original ? "(replace optional)" : "*"}`} type="file" accept={KNOWLEDGE_ACCEPT} required={!editor.original} onChange={event => {
            const chosen = event.target.files?.[0] ?? null; setDialogError("");
            try { if (chosen) validateKnowledgeFile(chosen); setFile(chosen); }
            catch (reason) { setFile(null); event.target.value = ""; setDialogError(message(reason)); }
          }} /><small>{file?.name || editor.original?.file.name || "Supported documents, images and videos up to 5 MiB."}</small></label>
          <label>File format<input aria-label="File format" readOnly value={file ? fileFormat(file.name) : editor.original ? fileFormat(editor.original.file.name) : ""} placeholder="Derived from file" /></label>
          {editor.original && <label>CMDB admin key<input aria-label="CMDB admin key" type="password" autoComplete="off" required value={adminKey} onChange={event => setAdminKey(event.target.value)} /></label>}
        </div>
        {editor.original && <small>Editing resets validation to Pending. Review updated content using the library's Validate action.</small>}
        {dialogError && <p role="alert" className="data-notice">{dialogError}</p>}
        <div className="knowledge-actions knowledge-form-actions"><button type="button" className="button button--secondary" onClick={() => { setEditor(null); setAdminKey(""); }}>Cancel</button>
          <button type="submit" className="button button--primary">{busy ? "Saving…" : editor.original ? "Save changes" : "Add content"}</button></div>
      </fieldset></form>
    </WorkspaceDialog>}
    {details && <KnowledgeDetails record={details} onClose={() => setDetails(null)} />}
    {action && <WorkspaceDialog title={action.kind === "delete" ? "Delete content" : "Validate content"} busy={busy} className="knowledge-dialog" onClose={() => { setAction(null); setAdminKey(""); }}>
      <form onSubmit={event => void performAction(event)}>
        <p>{action.kind === "delete" ? `Delete ${action.record.name} and its stored file? This cannot be undone.` : `Validate ${action.record.name}?`}</p>
        {action.kind === "validate" && <label className="vendor-reviewer">Validated by<input aria-label="Validated by" required maxLength={128} value={reviewer} disabled={busy} onChange={event => setReviewer(event.target.value)} /><small>Reviewer name is self-reported, not an authenticated identity.</small></label>}
        <label className="vendor-reviewer">CMDB admin key<input aria-label="CMDB admin key" type="password" autoComplete="off" required value={adminKey} disabled={busy} onChange={event => setAdminKey(event.target.value)} /><small>Use the same administration key as CMDB. It is not saved in browser storage.</small></label>
        {dialogError && <p role="alert" className="data-notice">{dialogError}</p>}
        <div className="knowledge-actions"><button type="button" className="button button--secondary" disabled={busy} onClick={() => { setAction(null); setAdminKey(""); }}>Cancel</button>
          <button type="submit" className="button button--primary" disabled={busy}>{action.kind === "delete" ? "Delete" : "Validate"}</button></div>
      </form>
    </WorkspaceDialog>}
  </div>;
}
