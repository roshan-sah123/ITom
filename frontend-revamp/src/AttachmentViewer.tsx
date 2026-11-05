import { useEffect, useRef, useState } from "react";
import { GlobalWorkerOptions, getDocument } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { previewEndpoint, previewText } from "./attachmentPreview";

GlobalWorkerOptions.workerSrc = workerUrl;

function PdfPages({ bytes }: { bytes: Uint8Array }) {
  const container = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let active = true;
    const loading = getDocument({ data: bytes.slice(), useSystemFonts: true });
    const element = container.current;
    setError(""); setReady(false);
    void loading.promise.then(async document => {
      if (document.numPages > 150) throw new Error("Preview unavailable: this document exceeds the 150-page preview limit.");
      for (let index = 1; index <= document.numPages && active; index++) {
        const page = await document.getPage(index);
        if (!active || !element) return;
        const original = page.getViewport({ scale: 1 });
        const scale = Math.min(1.4, Math.sqrt(6_000_000 / (original.width * original.height)));
        const viewport = page.getViewport({ scale });
        const canvas = window.document.createElement("canvas");
        canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
        canvas.setAttribute("role", "img"); canvas.setAttribute("aria-label", `Page ${index} of ${document.numPages}`);
        element.append(canvas);
        await page.render({ canvas, viewport }).promise;
        page.cleanup();
      }
      if (active) setReady(true);
    }).catch(reason => {
      if (active) {
        element?.replaceChildren();
        setError(reason instanceof Error ? reason.message : "Preview unavailable: the PDF could not be displayed.");
      }
    });
    return () => { active = false; void loading.destroy(); element?.replaceChildren(); };
  }, [bytes]);
  return <>
    {!ready && !error && <p role="status">Rendering document pages...</p>}
    {error && <p role="alert" className="data-notice">{error}</p>}
    <div ref={container} className="attachment-pdf-pages" aria-label="Document pages" />
  </>;
}

export default function AttachmentViewer() {
  const params = new URLSearchParams(window.location.search);
  const path = params.get("attachment") || "";
  const name = params.get("name") || "Attachment";
  const [preview, setPreview] = useState<{ bytes: Uint8Array; type: string; url: string } | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let url = "";
    setPreview(null); setError("");
    void (async () => {
      // Do not start a conversion for an effect canceled by React StrictMode.
      await Promise.resolve();
      if (controller.signal.aborted) return;
      const response = await fetch(previewEndpoint(path), {
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(60000)]),
      });
      if (!response.ok) {
        const body: { detail?: unknown } = await response.json();
        throw new Error(typeof body.detail === "string" ? body.detail : `Preview unavailable (${response.status}).`);
      }
      const type = response.headers.get("content-type")?.split(";")[0] || "";
      if (type !== "application/pdf" && type !== "text/plain" && !/^(image\/(png|jpeg|webp|gif)|video\/(mp4|webm|quicktime))$/.test(type))
        throw new Error("Preview unavailable for this file format.");
      const bytes = new Uint8Array(await response.arrayBuffer());
      if (controller.signal.aborted) return;
      url = URL.createObjectURL(new Blob([bytes], { type }));
      setPreview({ bytes, type, url });
    })().catch(reason => {
      if (!controller.signal.aborted)
        setError(reason instanceof Error ? reason.message : "Preview unavailable. Please retry.");
    });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [path, retry]);
  return <main className="attachment-viewer">
    <header className="panel"><div><p className="eyebrow">ATTACHMENT VIEWER</p><h1>{name}</h1></div>
      <button type="button" className="button button--secondary" onClick={() => setRetry(value => value + 1)}>Retry preview</button>
    </header>
    {error ? <p role="alert" className="data-notice">{error}</p> : !preview ? <p role="status">Preparing preview...</p>
      : preview.type === "application/pdf" ? <PdfPages bytes={preview.bytes} />
        : preview.type === "text/plain" ? <pre className="panel attachment-text">{previewText(preview.bytes)}</pre>
          : preview.type.startsWith("image/") ? <img className="attachment-image" src={preview.url} alt={name}
            onError={() => setError("Preview unavailable: this image could not be displayed.")} />
            : <video className="attachment-video" src={preview.url} controls controlsList="nodownload" playsInline
              onError={() => setError("Preview unavailable: this browser cannot play this video format.")} />}
  </main>;
}
