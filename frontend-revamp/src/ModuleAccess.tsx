import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { WorkspaceDialog } from "./WorkspaceDialog";

export function ModuleAccess({ children }: { children: ReactNode }) {
  const [authorized, setAuthorized] = useState(false);
  const [local, setLocal] = useState(false);
  const [network, setNetwork] = useState(false);
  const [checking, setChecking] = useState(true);
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const [promptOpen, setPromptOpen] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setChecking(true);
    setError("");
    void fetch("/api/v1/modules/access", { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]), cache: "no-store" })
      .then(async response => {
        const body = await response.json();
        if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Module access could not be checked.");
        if (!controller.signal.aborted) {
          setAuthorized(body.authorized === true);
          setLocal(body.local === true);
          setNetwork(body.network === true);
        }
      })
      .catch(reason => { if (!controller.signal.aborted) { setAuthorized(false); setError(reason instanceof Error ? reason.message : "Module access could not be checked."); } })
      .finally(() => { if (!controller.signal.aborted) setChecking(false); });
    return () => controller.abort();
  }, [retry]);

  async function unlock() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/v1/modules/access", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key }), signal: AbortSignal.timeout(15000),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Module access could not be opened.");
      setKey("");
      setRetry(value => value + 1);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Module access could not be opened."); }
    finally { setBusy(false); }
  }

  async function lock() {
    setBusy(true);
    try {
      const response = await fetch("/api/v1/modules/access", { method: "DELETE", signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw new Error("Module access could not be locked. Retry.");
      setAuthorized(false);
      setPromptOpen(true);
      setKey("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Module access could not be locked."); }
    finally { setBusy(false); }
  }

  if (checking) return <p role="status">Checking module access...</p>;
  if (authorized) return <>
    {!local && !network && <div className="vendor-table-toolbar">
      <span>Shared module access is open for this browser session.</span>
      <button className="button button--secondary" type="button" disabled={busy} onClick={() => void lock()}>Lock shared modules</button>
      <button className="button button--secondary" type="button" disabled={busy} onClick={() => setRetry(value => value + 1)}>Recheck module access</button>
      {error && <p role="alert">{error}</p>}
    </div>}
    {children}
  </>;
  return <section className="knowledge-workspace">
    <h1>Shared module access</h1>
    <p>Enter the shared access key to view and submit Vendor, Knowledge and Assets content. Administration still requires its separate key.</p>
    <button type="button" className="button button--secondary" onClick={() => setRetry(value => value + 1)}>Retry access check</button>
    {!promptOpen && <button type="button" className="button button--primary" onClick={() => setPromptOpen(true)}>Enter access key</button>}
    {!promptOpen && error && <p role="alert">{error}</p>}
    {promptOpen && <WorkspaceDialog title="Open shared modules" busy={busy} onClose={() => { setKey(""); setPromptOpen(false); }}>
      <form className="vendor-reviewer" onSubmit={event => { event.preventDefault(); void unlock(); }}>
        <label>Shared module access key
          <input type="password" autoComplete="off" required maxLength={256} value={key} onChange={event => setKey(event.target.value)} />
        </label>
        {error && <p role="alert" className="data-notice">{error}</p>}
        <button type="submit" className="button" disabled={busy}>Open modules</button>
      </form>
    </WorkspaceDialog>}
  </section>;
}
