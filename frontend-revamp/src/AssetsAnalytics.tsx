import { useEffect, useRef, useState } from "react";
import { getJson } from "./api";
import { downloadCsv, number } from "./data";
import { WorkspaceDialog } from "./WorkspaceDialog";
import {
  assetCount,
  assetRequest,
  editedAssetValue,
  assetWorkbookSources,
} from "./assets";
import type {
  AssetCategory,
  AssetRecord,
  AssetRecordPage,
  AssetCell,
  AssetSummary,
  AssetSummaryItem,
} from "./assets";

type AssetIconKind = AssetCategory;

function AssetIcon({ kind }: { kind: AssetIconKind }) {
  if (kind === "server")
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <rect x="4" y="4" width="16" height="6" rx="1.5" />
        <rect x="4" y="14" width="16" height="6" rx="1.5" />
        <path d="M8 7h.01M8 17h.01" />
      </svg>
    );
  if (kind === "network")
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <rect x="3" y="8" width="18" height="9" rx="2" />
        <path d="M7 12h.01M11 12h.01M15 12h.01M7 17v3m10-3v3M7 4v4m10-4v4" />
      </svg>
    );
  if (kind === "telecom")
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M6 4h12v16H6zM9 8h6M9 12h6M10 17h4" />
      </svg>
    );
  return null;
}

function errorText(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

function WorkbookInventoryDialog({
  category,
  label,
  onClose,
  onChange,
}: {
  category: AssetCategory;
  label: string;
  onClose: () => void;
  onChange: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [fullScreen, setFullScreen] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [retry, setRetry] = useState(0);
  const [inventory, setInventory] = useState<AssetRecordPage | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [enablePrompt, setEnablePrompt] = useState(false);
  const [adminToken, setAdminToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [actor, setActor] = useState("");
  const [dialogError, setDialogError] = useState("");
  const [notice, setNotice] = useState("");
  const [editor, setEditor] = useState<{ record: AssetRecord | null; fieldIndex?: number } | null>(null);
  const [rowName, setRowName] = useState("");
  const [data, setData] = useState<AssetCell[]>([]);
  const [action, setAction] = useState<{ kind: "validate" | "delete"; record: AssetRecord } | null>(null);
  const headers = () => ({ "Content-Type": "application/json", ...(adminToken ? { Authorization: `Bearer ${adminToken}` } : {}) });

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (search.trim()) params.set("search", search.trim());
    setLoading(true);
    setError("");
    setInventory(null);
    void assetRequest<AssetRecordPage>(
      `/records/${category}?${params.toString()}`,
      { signal: controller.signal },
    )
      .then((result) => {
        if (!controller.signal.aborted) setInventory(result);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(errorText(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [category, page, pageSize, retry, search]);

  async function exportAll() {
    if (!inventory) return;
    setExporting(true);
    setError("");
    try {
      const params = new URLSearchParams({
        page: "1",
        page_size: "100",
        ...(search.trim() ? { search: search.trim() } : {}),
      });
      const firstPage = await assetRequest<AssetRecordPage>(
        `/records/${category}?${params.toString()}`,
      );
      const exportRows = (result: AssetRecordPage) => result.items.map(row => [
        ...row.data.map(cell => cell.value == null ? "" : String(cell.value)),
        row.is_validated ? "Validated" : "Pending", row.validated_by ?? "", row.validated_at ?? "",
      ]);
      const rows = exportRows(firstPage);
      for (let requestedPage = 2; requestedPage <= firstPage.total_pages; requestedPage++) {
        params.set("page", String(requestedPage));
        const result = await assetRequest<AssetRecordPage>(
          `/records/${category}?${params.toString()}`,
        );
        rows.push(...exportRows(result));
      }
      downloadCsv(`${category}-inventory.csv`, [...firstPage.columns, "Validation", "Validated by", "Validated on"], rows);
    } catch (reason) {
      setError(`CSV export failed. ${errorText(reason)}`);
    } finally {
      setExporting(false);
    }
  }

  function openEditor(record: AssetRecord | null, fieldIndex?: number) {
    setEditor({ record, fieldIndex }); setRowName(record?.name ?? "");
    setData(record?.data.map(cell => ({ ...cell })) ?? inventory!.columns.map((header, index) => ({ index, header, value: null })));
    setActor(""); setDialogError("");
  }
  async function enableEditing() {
    setBusy(true); setDialogError("");
    try {
      await assetRequest("/admin/check", { headers: headers() });
      setEditMode(true); setEnablePrompt(false);
    } catch (reason) { setDialogError(errorText(reason)); }
    finally { setBusy(false); }
  }
  async function change(kind: "save" | "validate" | "validate-field" | "delete") {
    const record = editor?.record ?? action?.record;
    setBusy(true); setDialogError("");
    try {
      if (!actor.trim()) throw new Error("Enter the operator or reviewer name. Names are self-reported.");
      let path = `/records/${category}${record ? `/${record.id}` : ""}`;
      const body = { actor: actor.trim(), ...(record ? { expected_revision: record.revision } : {}) };
      if (kind === "save") {
        await assetRequest(path, { method: record ? "PUT" : "POST", headers: headers(), body: JSON.stringify({
          ...body, name: rowName.trim(), data, ...(!record ? { source_sheet: inventory!.source_sheet } : {}),
        }) });
      } else {
        if (kind === "validate") path += "/validate";
        if (kind === "validate-field") path += `/fields/${editor!.fieldIndex}/validate`;
        await assetRequest(path, { method: kind === "delete" ? "DELETE" : "POST", headers: headers(), body: JSON.stringify(body) });
      }
      setEditor(null); setAction(null); setPage(1); setRetry(value => value + 1); onChange();
      setNotice(kind === "save" ? "Inventory saved. Changed cells require review." : kind === "delete" ? "Inventory record deleted." : "Inventory validated. Reviewer name is self-reported.");
    } catch (reason) { setDialogError(errorText(reason)); }
    finally { setBusy(false); }
    }

  const start = inventory && inventory.total > 0
    ? (inventory.page - 1) * inventory.page_size + 1
    : 0;
  const end = inventory
    ? Math.min(inventory.page * inventory.page_size, inventory.total)
    : 0;

  return (<>
    <dialog
      aria-labelledby="asset-inventory-title"
      className={`asset-inventory-dialog${fullScreen ? " asset-inventory-dialog--fullscreen" : ""}`}
      ref={dialogRef}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="asset-dialog__header">
        <div>
          <p className="eyebrow">ASSET INVENTORY</p>
          <h2 id="asset-inventory-title">{label}</h2>
        </div>
        <div className="asset-dialog__actions">
          <span className="asset-record-count">
            {inventory ? `${number(inventory.total)} records` : "Loading inventory"}
          </span>
          <button type="button" className="button button--primary" disabled={!inventory || busy} onClick={() => openEditor(null)}>+ Add data</button>
          <button
            className="button button--secondary"
            disabled={!inventory || inventory.total === 0 || exporting}
            onClick={() => void exportAll()}
            type="button"
          >
            {exporting ? "Exporting…" : "Export CSV"}
          </button>
          <button type="button" className="button button--secondary" disabled={loading || busy} onClick={() => {
            if (editMode) setEditMode(false);
            else { setDialogError(""); setEnablePrompt(true); }
          }}>{editMode ? "Done editing" : "Edit mode"}</button>
        </div>
        <div className="asset-dialog__window-controls">
          <button
            aria-label={fullScreen ? `Restore ${label} inventory size` : `Full screen ${label} inventory`}
            aria-pressed={fullScreen}
            title={fullScreen ? "Restore size" : "Full screen"}
            className="asset-dialog__close"
            onClick={() => setFullScreen(value => !value)}
            type="button"
          >
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d={fullScreen ? "M9 3v6H3m18 0h-6V3M3 15h6v6m6 0v-6h6" : "M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"} />
            </svg>
          </button>
          <button
            aria-label={`Close ${label} inventory`}
            title="Close"
            className="asset-dialog__close"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </div>
        {notice && <p role="status" className="vendor-notice">{notice}</p>}
      </div>

      <div className="asset-dialog__toolbar">
        <label className="table-search asset-dialog__search">
          <span aria-hidden="true">⌕</span>
          <input
            aria-label={`Search ${label} inventory`}
            maxLength={200}
            placeholder={`Search ${label.toLowerCase()} inventory`}
            type="search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </label>
        <label className="asset-page-size">
          <span>Rows</span>
          <select
            aria-label="Rows per page"
            className="button button--secondary"
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value));
              setPage(1);
            }}
          >
            {[10, 25, 50, 100, 150, 200].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && (
        <div className="data-notice" role="alert">
          {error}{" "}
          <button
            className="text-button"
            onClick={() => setRetry((value) => value + 1)}
            type="button"
          >
            Retry
          </button>
        </div>
      )}
      <div className="asset-table-wrap" aria-busy={loading}>
        {inventory && (
          <table className="asset-table">
            <thead>
              <tr>
                {inventory.columns.map((column) => (
                  <th key={column} scope="col">
                    {column}
                  </th>
                ))}
                <th>Validation</th><th>Validated by</th><th>Validated on</th>{editMode && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {inventory.items.map((row) => (
                <tr key={row.id}>
                  {row.data.map((cell) => {
                    const value = cell.value;
                    const review = row.field_reviews[String(cell.index)];
                    return (
                      <td key={cell.index} title={value == null ? undefined : String(value)}>
                        <button type="button" className={`asset-cell-button${review ? " asset-cell-button--validated" : ""}`}
                          aria-label={`Open ${cell.header} for ${row.name}`} onClick={() => openEditor(row, cell.index)}>
                          {value == null || value === "" ? "—" : String(value)}
                        </button>
                      </td>
                    );
                  })}
                  <td><span className={`vendor-validation vendor-validation--${row.is_validated ? "validated" : "pending"}`}>{row.is_validated ? "Validated" : "Pending"}</span></td>
                  <td>{row.validated_by || "—"}</td><td>{row.validated_at ? new Date(row.validated_at).toLocaleString() : "—"}</td>
                  {editMode && <td><div className="vendor-row-actions">
                    <button type="button" className="button button--secondary" onClick={() => openEditor(row)}>Edit</button>
                    <button type="button" className="button button--secondary vendor-delete" onClick={() => { setDialogError(""); setActor(""); setAction({ kind: "delete", record: row }); }}>Delete</button>
                    <button type="button" className="button button--secondary" disabled={row.is_validated}
                      onClick={() => { setDialogError(""); setActor(""); setAction({ kind: "validate", record: row }); }}>{row.is_validated ? "Validated" : "Validate"}</button>
                  </div></td>}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {loading && <div className="empty-state">Loading {label.toLowerCase()} inventory…</div>}
        {!loading && !error && inventory?.total === 0 && (
          <div className="empty-state">No records match this search.</div>
        )}
        {!loading && error && !inventory && (
          <div className="empty-state">Inventory is unavailable. Retry the request.</div>
        )}
      </div>
      <div className="asset-dialog__footer">
        <span aria-live="polite">
          {inventory
            ? `Showing ${start}–${end} of ${number(inventory.total)} records`
            : "Workbook source unavailable"}
        </span>
        <div>
          <button
            className="button button--secondary"
            disabled={loading || page <= 1}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            type="button"
          >
            Previous
          </button>
          <span>
            Page {inventory?.page ?? page} of {inventory?.total_pages ?? 1}
          </span>
          <button
            className="button button--secondary"
            disabled={loading || !inventory || page >= inventory.total_pages}
            onClick={() => setPage((value) => value + 1)}
            type="button"
          >
            Next
          </button>
        </div>
      </div>
    </dialog>
    {enablePrompt && <WorkspaceDialog title="Enable inventory editing" busy={busy} className="knowledge-dialog" onClose={() => setEnablePrompt(false)}>
      <p>Edit, Validate and Delete require the shared CMDB admin key. The key is held only while this inventory is open, never in browser storage.</p>
      <form onSubmit={event => { event.preventDefault(); void enableEditing(); }}>
        <label className="vendor-reviewer">CMDB admin key<input aria-label="CMDB admin key" type="password" autoComplete="off" required value={adminToken} onChange={event => setAdminToken(event.target.value)} /></label>
        {dialogError && <p className="data-notice" role="alert">{dialogError}</p>}
        <button type="submit" className="button button--primary" disabled={busy}>Enable editing</button>
      </form>
    </WorkspaceDialog>}
    {editor && <WorkspaceDialog title={editor.fieldIndex != null ? "Inventory cell" : editor.record ? "Edit inventory row" : "Add inventory row"}
      wide busy={busy} className="knowledge-dialog" onClose={() => setEditor(null)}>
      {editor.record && <p>{editor.record.name} · {editor.record.source_file} · {editor.record.source_sheet} · source row {editor.record.source_row || "Manual entry"}</p>}
      <form onSubmit={event => { event.preventDefault(); void change("save"); }}>
        <fieldset disabled={busy || !editMode} className="knowledge-form">
          {editor.fieldIndex == null && <label>Record name *<input aria-label="Record name *" required maxLength={512} value={rowName} onChange={event => setRowName(event.target.value)} /></label>}
          <div className="knowledge-form-grid">{data.filter(cell => editor.fieldIndex == null || cell.index === editor.fieldIndex).map(cell =>
            <label key={cell.index}>{cell.header}<input aria-label={cell.header} maxLength={10000} value={cell.value == null ? "" : String(cell.value)} onChange={event => {
              const text = event.target.value;
              setData(previous => previous.map(item => item.index === cell.index ? { ...item, value: editedAssetValue(cell.value, text) } : item));
            }} /></label>)}</div>
        </fieldset>
        {editor.fieldIndex != null && <p>{editor.record!.field_reviews[String(editor.fieldIndex)] ?
          `Reviewed by ${editor.record!.field_reviews[String(editor.fieldIndex)].validated_by} on ${new Date(editor.record!.field_reviews[String(editor.fieldIndex)].validated_at).toLocaleString()}` : "This cell is pending review."}</p>}
        {editMode && <label className="vendor-reviewer">Operator / reviewer name *<input aria-label="Operator / reviewer name *" required maxLength={128} value={actor} onChange={event => setActor(event.target.value)} /><small>Self-reported; not an authenticated identity.</small></label>}
        {dialogError && <p className="data-notice" role="alert">{dialogError}</p>}
        <div className="knowledge-actions">
          <button type="button" className="button button--secondary" disabled={busy} onClick={() => setEditor(null)}>Close</button>
          {editMode && <button type="submit" className="button button--primary" disabled={busy}>Save changes</button>}
          {editMode && editor.fieldIndex != null && <button type="button" className="button button--secondary"
            disabled={busy || JSON.stringify(data) !== JSON.stringify(editor.record!.data)}
            onClick={() => void change("validate-field")}>Validate field</button>}
        </div>
        {editMode && editor.fieldIndex != null && <small>Save a changed cell before validating it.</small>}
      </form>
    </WorkspaceDialog>}
    {action && <WorkspaceDialog title={action.kind === "delete" ? "Delete inventory row" : "Validate inventory row"} busy={busy} className="knowledge-dialog" onClose={() => setAction(null)}>
      <form onSubmit={event => { event.preventDefault(); void change(action.kind); }}>
        <p>{action.kind === "delete" ? `Delete ${action.record.name}? The source workbook will not be changed.` : `Validate every field in ${action.record.name}?`}</p>
        <label className="vendor-reviewer">Operator / reviewer name *<input aria-label="Operator / reviewer name *" required maxLength={128} value={actor} onChange={event => setActor(event.target.value)} /><small>Self-reported; not an authenticated identity.</small></label>
        {dialogError && <p className="data-notice" role="alert">{dialogError}</p>}
        <div className="knowledge-actions"><button type="button" className="button button--secondary" disabled={busy} onClick={() => setAction(null)}>Cancel</button>
          <button type="submit" className="button button--primary" disabled={busy}>{action.kind === "delete" ? "Delete" : "Validate"}</button></div>
      </form>
    </WorkspaceDialog>}
  </>);
}

export function AssetsAnalytics({
  revision,
  onRefresh,
}: {
  revision: number;
  onRefresh: () => void;
}) {
  const [summary, setSummary] = useState<AssetSummary | null>(null);
  const [summaryError, setSummaryError] = useState("");
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState<AssetCategory | null>(
    null,
  );
  const [inventoryRevision, setInventoryRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setSummaryLoading(true);
    setSummary(null);
    setSummaryError("");
    void getJson<AssetSummary>("/assets/summary", controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setSummary(result);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setSummaryError(errorText(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setSummaryLoading(false);
      });
    return () => controller.abort();
  }, [revision, inventoryRevision]);

  const sources: AssetSummaryItem[] = assetWorkbookSources.map((source) => {
    const item = summary?.items.find(
      (candidate) => candidate.category === source.category,
    );
    return (
      item ?? {
        category: source.category,
        label: source.label,
        data_available: false,
        total: null,
      }
    );
  });
  const dialogSource = assetWorkbookSources.find(
    (source) => source.category === selectedCategory,
  );

  return (
    <div className="asset-analytics">
      <section className="workspace-hero asset-hero">
        <div>
          <p className="eyebrow">ENTERPRISE INVENTORY</p>
          <h1>Assets Analytics</h1>
          <p className="hero__subtitle">
            Current infrastructure inventory across core asset categories.
          </p>
        </div>
        <div className="hero__actions">
          <button
            className="button button--secondary"
            onClick={onRefresh}
            type="button"
          >
            Reload inventory
          </button>
        </div>
      </section>

      {summaryError && (
        <div className="data-notice" role="alert">
          Asset workbook summary unavailable: {summaryError}
        </div>
      )}

      <section
        aria-label="Asset inventory summary"
        aria-busy={summaryLoading}
        className="asset-summary-grid"
      >
        {assetWorkbookSources.map((source, index) => {
          const item = sources[index];
          return (
            <button
              aria-label={`Open ${source.label} inventory`}
              className={`asset-summary-card asset-summary-card--${source.tone}`}
              key={source.category}
              onClick={() => setSelectedCategory(source.category)}
              type="button"
            >
              <span className={`asset-summary-card__icon asset-summary-card__icon--${source.tone}`}>
                <AssetIcon kind={source.kind} />
              </span>
              <span className="asset-summary-card__label">{source.label}</span>
              <strong>{summaryLoading ? "…" : assetCount(item)}</strong>
              <span className="asset-summary-card__footer">
                {item.data_available
                  ? "Open inventory"
                  : summaryLoading
                    ? "Checking workbook"
                    : "Source unavailable"}
                <span aria-hidden="true">View records →</span>
              </span>
            </button>
          );
        })}
      </section>

      {selectedCategory && dialogSource && (
        <WorkbookInventoryDialog
          category={selectedCategory}
          label={dialogSource.label}
          onClose={() => setSelectedCategory(null)}
          onChange={() => setInventoryRevision(value => value + 1)}
        />
      )}
    </div>
  );
}
