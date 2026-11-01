import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

export function WorkspaceDialog({ title, children, onClose, busy = false, wide = false, className = "", icon, subtitle }: {
  title: string; children: ReactNode; onClose: () => void; busy?: boolean; wide?: boolean; className?: string;
  icon?: ReactNode; subtitle?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => { if (dialog?.open) dialog.close(); };
  }, []);
  return (
    <dialog ref={ref} className={`vendor-dialog${wide ? " vendor-dialog--wide" : ""} ${className}`}
      aria-label={title} onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
      <div className="vendor-dialog__header">
        {icon}
        <div className="workspace-dialog-heading"><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
        <button type="button" aria-label={`Close ${title}`} disabled={busy} onClick={onClose}>×</button>
      </div>
      {children}
    </dialog>
  );
}
