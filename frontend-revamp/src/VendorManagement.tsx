import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { WorkspaceDialog as VendorDialog } from "./WorkspaceDialog";
import { attachmentViewUrl } from "./attachmentPreview";
import {
  readVendorFile, validateVendorDraft, vendorRequest, vendorSubmissionBody,
} from "./vendors";
import type { VendorDetail, VendorDraft, VendorFile, VendorRecord } from "./vendors";

type VendorPage = {
  items: VendorRecord[];
  total: number;
  page: number;
  page_size: number;
  next_serial: number;
};
type EditData = VendorDetail & { draft: VendorDraft; sop_file: VendorFile | null };
const emptyDraft = (): VendorDraft => ({
  vendor: "", method: "", steps: [{ what_to_do: "", how_to_do: "", image: null }],
});
const requestId = () => crypto.randomUUID().replaceAll("-", "");
const errorMessage = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);
const dateLabel = (value: string | null) => value ? new Date(value).toLocaleString() : "—";

function VendorAttachmentPreview({ attachment, onClose }: {
  attachment: { name: string; url: string }; onClose: () => void;
}) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = "";
    void fetch(attachment.url, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error(`Attachment could not be loaded (${response.status}).`);
      const blob = await response.blob();
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob); setUrl(objectUrl);
    }).catch(reason => { if (!controller.signal.aborted) setError(errorMessage(reason)); });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [attachment]);
  return <VendorDialog title="Screenshot preview" wide onClose={onClose}>
    <p>{attachment.name}</p>
    {error && <p role="alert" className="data-notice">{error}</p>}
    {url ? <section className="knowledge-preview">
      <img src={url} alt={attachment.name} />
    </section> : !error && <p role="status">Loading attachment…</p>}
    <a className="button button--secondary" href={attachment.url} download={attachment.name}>Download image</a>
  </VendorDialog>;
}

export function VendorManagement() {
  const [view, setView] = useState<"list" | "form">("list");
  const [result, setResult] = useState<VendorPage | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draft, setDraft] = useState<VendorDraft>(emptyDraft);
  const [editing, setEditing] = useState<VendorRecord | null>(null);
  const [existingSop, setExistingSop] = useState<VendorFile | null>(null);
  const [submissionId, setSubmissionId] = useState(requestId);
  const [fileReads, setFileReads] = useState(0);
  const [busy, setBusy] = useState(false);
  const [details, setDetails] = useState<VendorDetail | null>(null);
  const [preview, setPreview] = useState<{ name: string; url: string } | null>(null);
  const [action, setAction] = useState<{ kind: "validate" | "delete"; item: VendorRecord } | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [adminKey, setAdminKey] = useState("");
  const [sopPrompt, setSopPrompt] = useState(false);
  const [attachSop, setAttachSop] = useState(false);
  const [sopFile, setSopFile] = useState<File | null>(null);
  const [dialogError, setDialogError] = useState("");
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void vendorRequest<VendorPage>(`?search=${encodeURIComponent(search)}&page=${page}&page_size=25`, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setResult(data); })
      .catch((reason: unknown) => { if (!controller.signal.aborted) { setResult(null); setError(errorMessage(reason)); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [page, refresh, search]);

  function newForm() {
    setAdminKey("");
    setDraft(emptyDraft()); setEditing(null); setExistingSop(null);
    setSubmissionId(requestId()); setView("form"); setError(""); setNotice("");
  }
  function clearForm() {
    setAdminKey("");
    setDraft(emptyDraft()); setSubmissionId(requestId()); setError("");
    setExistingSop(null); formRef.current?.reset();
  }
  async function openSubmission(item: VendorRecord, edit: boolean) {
    setBusy(true); setError(""); setNotice("");
    try {
      if (edit) {
        setAdminKey("");
        const data = await vendorRequest<EditData>(`/${item.id}?include_files=true`);
        setDraft(data.draft); setExistingSop(data.sop_file); setEditing(data);
        setSubmissionId(requestId()); setView("form");
      } else setDetails(await vendorRequest<VendorDetail>(`/${item.id}`));
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  function updateStep(index: number, key: "what_to_do" | "how_to_do", value: string) {
    setDraft((previous) => ({
      ...previous, steps: previous.steps.map((step, i) => i === index ? { ...step, [key]: value } : step),
    }));
  }
  async function chooseImage(index: number, file: File | undefined) {
    setError("");
    if (!file) {
      setDraft((previous) => ({ ...previous, steps: previous.steps.map((step, i) => i === index ? { ...step, image: null } : step) }));
      return;
    }
    setFileReads((count) => count + 1);
    try {
      const image = await readVendorFile(file, true);
      setDraft((previous) => ({ ...previous, steps: previous.steps.map((step, i) => i === index ? { ...step, image } : step) }));
    } catch (reason) {
      setError(errorMessage(reason));
      setDraft((previous) => ({ ...previous, steps: previous.steps.map((step, i) => i === index ? { ...step, image: null } : step) }));
    } finally { setFileReads((count) => count - 1); }
  }
  function submit(event: FormEvent) {
    event.preventDefault(); setError(""); setNotice("");
    try {
      validateVendorDraft(draft);
      setDialogError(""); setSopFile(null); setAttachSop(false); setSopPrompt(true);
    } catch (reason) { setError(errorMessage(reason)); }
  }
  async function save(withSop: boolean) {
    setBusy(true); setDialogError("");
    try {
      if (withSop && !sopFile) throw new Error("Choose an SOP file before saving.");
      const sop = withSop && sopFile ? await readVendorFile(sopFile, false) : existingSop;
      const body = vendorSubmissionBody(draft, submissionId, sop);
      await vendorRequest<VendorRecord>(editing ? `/${editing.id}` : "", {
        method: editing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json", ...(editing ? { Authorization: `Bearer ${adminKey}` } : {}) },
        body: JSON.stringify({ ...body, ...(editing ? { expected_revision: editing.revision } : {}) }),
      });
      setSopPrompt(false); setView("list"); setRefresh((value) => value + 1);
      setNotice(editing ? "Submission updated. Validation reset to Pending." : "Vendor submission saved.");
      setDraft(emptyDraft()); setEditing(null); setExistingSop(null); setSubmissionId(requestId());
      setAdminKey("");
    } catch (reason) { setDialogError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  async function performAction(event: FormEvent) {
    event.preventDefault();
    if (!action) return;
    setBusy(true); setDialogError("");
    try {
      if (action.kind === "delete") {
        await vendorRequest(`/${action.item.id}?expected_revision=${action.item.revision}`, { method: "DELETE", headers: { Authorization: `Bearer ${adminKey}` } });
        setNotice("Submission deleted.");
      } else {
        await vendorRequest(`/${action.item.id}/validate`, {
          method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${adminKey}` },
          body: JSON.stringify({ reviewer: reviewer.trim(), expected_revision: action.item.revision }),
        });
        setNotice("Submission validated. Reviewer name is self-reported, not an authenticated identity.");
      }
      setAction(null); setAdminKey(""); setPage(1); setRefresh((value) => value + 1);
    } catch (reason) { setDialogError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  return (
    <div className="vendor-workspace">
      {view === "list" ? (
        <>
          <section className="workspace-hero vendor-hero">
            <div><p className="eyebrow">PARTNER OPERATIONS</p><h1>Vendor Management</h1>
              <p className="hero__subtitle">Review submissions, validation details, screenshots, and SOPs.</p></div>
            <button type="button" className="button" onClick={newForm} disabled={busy || loading || !result}>+ Fill vendor form</button>
          </section>
          <section className="vendor-submissions panel" aria-label="Vendor submissions">
            <div className="vendor-table-toolbar">
              <input type="search" aria-label="Search vendors" placeholder="Search vendors" maxLength={200}
                value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} />
              <span>{result ? `${result.total} vendor submissions` : "Submissions unavailable"}</span>
            </div>
            <div className="vendor-table-scroll" aria-busy={loading}>
              <table className="vendor-table">
                <thead><tr>{["S.NO", "VENDOR NAME", "METHOD", "STEPS", "VALIDATION", "VALIDATED ON", "VALIDATED BY", "ACTIONS"].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
                <tbody>{!loading && result?.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.serial}</td><td><strong>{item.vendor}</strong></td><td>{item.method}</td>
                    <td><span className="vendor-step-badge">{item.step_count} {item.step_count === 1 ? "step" : "steps"}{item.sop_name ? " · SOP" : ""}</span></td>
                    <td><span className={`vendor-validation vendor-validation--${item.validation.toLowerCase()}`}>{item.validation}</span></td>
                    <td>{dateLabel(item.validated_on)}</td>
                    <td>{item.validated_by || "—"}</td>
                    <td><div className="vendor-row-actions">
                      <button type="button" className="button button--primary" disabled={busy} onClick={() => void openSubmission(item, false)}>Open submission</button>
                      <button type="button" className="button button--secondary" disabled={busy} onClick={() => void openSubmission(item, true)}>Edit</button>
                      <button type="button" className="button button--secondary" disabled={busy || item.validation === "Validated"}
                        onClick={() => { setAdminKey(""); setAction({ kind: "validate", item }); setReviewer(""); setDialogError(""); }}>
                        {item.validation === "Validated" ? "Validated" : "Validate"}
                      </button>
                      <button type="button" className="button button--secondary vendor-delete" disabled={busy}
                        onClick={() => { setAdminKey(""); setAction({ kind: "delete", item }); setDialogError(""); }}>Delete</button>
                    </div></td>
                  </tr>
                ))}</tbody>
              </table>
              {loading && <div className="empty-state" role="status">Loading vendor submissions…</div>}
              {!loading && result?.total === 0 && <div className="empty-state">No vendor submissions{search ? " match this search" : " yet"}.{!search && " Fill the vendor form to add one."}</div>}
            </div>
            {result && result.total > 25 && <div className="table-footer">
              <span>Page {page} of {Math.ceil(result.total / 25)}</span>
              <div className="vendor-row-actions">
                <button type="button" className="button button--secondary" disabled={loading || page === 1} onClick={() => setPage((value) => value - 1)}>Previous</button>
                <button type="button" className="button button--secondary" disabled={loading || page * 25 >= result.total} onClick={() => setPage((value) => value + 1)}>Next</button>
              </div>
            </div>}
          </section>
        </>
      ) : (
        <>
          <header className="vendor-form-heading"><h1>{editing ? "Edit vendor" : "Add vendor"}</h1><p>Complete the vendor details and submit.</p></header>
          <form ref={formRef} className="vendor-form panel" onSubmit={submit}>
            <fieldset disabled={busy || fileReads > 0 || sopPrompt}>
              <div className="vendor-form-columns vendor-form-column-labels" aria-hidden="true">
                <span>S.No</span><span>Vendor name</span><span>Method</span><span>Steps</span>
              </div>
              <div className="vendor-form-columns">
                <span className="vendor-serial" title="Display sequence updates when submissions are added or deleted.">{editing?.serial ?? result?.next_serial ?? "Auto"}</span>
                <input aria-label="Vendor name" placeholder="Vendor name" required maxLength={100}
                  value={draft.vendor} onChange={(event) => setDraft((previous) => ({ ...previous, vendor: event.target.value }))} />
                <input aria-label="Method" placeholder="Enter method" required maxLength={80}
                  value={draft.method} onChange={(event) => setDraft((previous) => ({ ...previous, method: event.target.value }))} />
                <div className="vendor-form-steps">
                  {draft.steps.map((step, index) => (
                    <section className="vendor-form-step" key={index} aria-label={`Step ${index + 1}`}>
                      <div className="vendor-form-step__header"><strong>Step {index + 1}</strong>
                        <button type="button" className="vendor-delete" disabled={draft.steps.length === 1}
                          onClick={() => setDraft((previous) => ({ ...previous, steps: previous.steps.filter((_, i) => i !== index) }))}>Remove</button></div>
                      <div className="vendor-step-fields">
                        <label>What to do *<textarea required maxLength={2000} aria-label={`Step ${index + 1} What to do`} value={step.what_to_do}
                          onChange={(event) => updateStep(index, "what_to_do", event.target.value)} /></label>
                        <label>How to do *<textarea required maxLength={2000} aria-label={`Step ${index + 1} How to do`} value={step.how_to_do}
                          onChange={(event) => updateStep(index, "how_to_do", event.target.value)} /></label>
                      </div>
                      <label className="vendor-image-field">Screenshot / image (optional)
                        <input type="file" accept="image/png,image/jpeg,image/webp" aria-label={`Step ${index + 1} Screenshot`}
                          onChange={(event) => void chooseImage(index, event.target.files?.[0])} />
                        <small>PNG, JPEG or WebP, maximum 1.5 MB</small>
                      </label>
                      {step.image && <div className="vendor-selected-file"><span>{step.image.name}</span>
                        <button type="button" onClick={() => void chooseImage(index, undefined)}>Remove image</button></div>}
                    </section>
                  ))}
                  <button type="button" disabled={draft.steps.length >= 30}
                    onClick={() => setDraft((previous) => ({ ...previous, steps: [...previous.steps, { what_to_do: "", how_to_do: "", image: null }] }))}>+ Add step</button>
                </div>
              </div>
              {editing && <label className="vendor-reviewer">CMDB admin key<input aria-label="CMDB admin key" type="password" autoComplete="off" required value={adminKey} onChange={event => setAdminKey(event.target.value)} /><small>Editing requires the shared key; it is not saved in browser storage.</small></label>}
              <div className="vendor-form-actions">
                <button type="submit" className="button button--primary">Submit</button>
                <button type="button" className="button button--secondary" onClick={clearForm}>Clear</button>
                <button type="button" className="button button--secondary" onClick={() => { setAdminKey(""); setView("list"); setError(""); }}>Back to submissions</button>
              </div>
            </fieldset>
            {fileReads > 0 && <p role="status">Reading screenshot…</p>}
          </form>
        </>
      )}
      {error && <div className="data-notice" role="alert">{error} <button type="button" className="text-button" onClick={() => setRefresh((value) => value + 1)}>Retry</button></div>}
      {notice && <p className="vendor-notice" role="status">{notice}</p>}

      {sopPrompt && <VendorDialog title="Do you want to attach SOP?" busy={busy} onClose={() => setSopPrompt(false)}>
        <p>Attach an optional SOP, or save without adding one.{editing && existingSop ? ` Existing SOP "${existingSop.name}" will be kept unless replaced.` : ""}</p>
        {dialogError && <p className="data-notice" role="alert">{dialogError}</p>}
        {attachSop ? <div className="vendor-sop-picker">
          <label>SOP file<input type="file" accept=".pdf,.docx,.txt" disabled={busy} onChange={(event) => setSopFile(event.target.files?.[0] ?? null)} /></label>
          <small>PDF, DOCX or TXT, maximum 10 MB.</small>
          <button type="button" className="button button--primary" disabled={busy || !sopFile} onClick={() => void save(true)}>{busy ? "Saving…" : "Attach SOP and save"}</button>
        </div> : <div className="vendor-row-actions">
          <button type="button" className="button button--primary" disabled={busy} onClick={() => setAttachSop(true)}>Yes, attach SOP</button>
          <button type="button" className="button button--secondary" disabled={busy} onClick={() => void save(false)}>{busy ? "Saving…" : "No, save submission"}</button>
        </div>}
        <button type="button" className="button button--secondary vendor-dialog-cancel" disabled={busy} onClick={() => setSopPrompt(false)}>Cancel</button>
      </VendorDialog>}

      {details && <VendorDialog title="Submission details" wide onClose={() => setDetails(null)}>
        <p className="vendor-detail-subtitle">{details.vendor} · {details.method} · {details.step_count} {details.step_count === 1 ? "step" : "steps"}</p>
        <div className="vendor-detail-metadata">
          {[["VENDOR NAME", details.vendor], ["METHOD", details.method]].map(([label, value]) => (
            <div key={label}><span>{label}</span><strong>{value}</strong></div>
          ))}
        </div>
        <h3 className="vendor-detail-section-title">Steps</h3>
        {details.steps.map((step, index) => <section className="vendor-detail-step" key={index}>
          <h3><span>{index + 1}</span>Step {index + 1}</h3>
          <div className="vendor-detail-metadata"><div><span>WHAT TO DO</span><p>{step.what_to_do}</p></div><div><span>HOW TO DO</span><p>{step.how_to_do}</p></div></div>
          {step.image && <div className="vendor-detail-image"><h4>Screenshot / Image</h4>
            <button type="button" className="vendor-image-preview" aria-label={`Enlarge Step ${index + 1} screenshot`}
              onClick={() => setPreview(step.image!)}><img src={step.image.url} alt={`Step ${index + 1}: ${step.image.name}`} /></button>
          </div>}
        </section>)}
        <h3 className="vendor-detail-section-title">SOP</h3>
        {details.sop ? <div className="vendor-row-actions">
          <a className="button button--primary" href={attachmentViewUrl(details.sop.url, details.sop.name)} target="_blank" rel="noopener noreferrer">View SOP</a>
        </div> : <p>No SOP attached.</p>}
      </VendorDialog>}
      {preview && <VendorAttachmentPreview attachment={preview} onClose={() => setPreview(null)} />}
      {action && <VendorDialog title={action.kind === "delete" ? "Delete submission" : "Validate submission"} busy={busy} onClose={() => { setAdminKey(""); setAction(null); }}>
        <form onSubmit={(event) => void performAction(event)}>
          <p>{action.kind === "delete" ? `Delete submission ${action.item.serial} for ${action.item.vendor}? Its screenshots and SOP will be removed.` : `Confirm your review of ${action.item.vendor}.`}</p>
          {action.kind === "validate" && <label className="vendor-reviewer">Reviewer name<input aria-label="Reviewer name" required maxLength={128} value={reviewer} disabled={busy} onChange={(event) => setReviewer(event.target.value)} /><small>Recorded as a self-reported reviewer, not an authenticated identity.</small></label>}
          <label className="vendor-reviewer">CMDB admin key<input aria-label="CMDB admin key" type="password" autoComplete="off" required value={adminKey} disabled={busy} onChange={event => setAdminKey(event.target.value)} /><small>The shared key is not saved in browser storage.</small></label>
          {dialogError && <p className="data-notice" role="alert">{dialogError}</p>}
          <div className="vendor-row-actions"><button type="submit" className="button button--primary" disabled={busy}>{busy ? "Saving…" : action.kind === "delete" ? "Delete" : "Validate"}</button>
            <button type="button" className="button button--secondary" disabled={busy} onClick={() => { setAdminKey(""); setAction(null); }}>Cancel</button></div>
        </form>
      </VendorDialog>}
    </div>
  );
}
