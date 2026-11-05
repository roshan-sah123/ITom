
export const KNOWLEDGE_CATEGORIES = [
  "SOP", "Runbook", "Technical Document", "Reference Document", "Diagram",
  "Training Video", "Training Presentation", "User Guide", "Policy / Standard",
  "Troubleshooting Guide", "Other",
] as const;
const KNOWLEDGE_FILE_TYPE = "application/octet-stream";
export const KNOWLEDGE_FILE_ACCEPT = ".docx,.pdf,.pptx,.txt,.mp4,.webm,.mov";
export type KnowledgeStatus = "All" | "Validated" | "Pending";
export type KnowledgeDraft = { name: string; description: string; category: string };
export type KnowledgeRecord = KnowledgeDraft & {
  id: string; serial: number; revision: number;
  file: { name: string; type: string; size: number; url: string };
  validatedOn: string | null; validatedBy: string;
};
type SearchableContent = KnowledgeDraft & { file: { name: string }; validatedOn: string | null };
export function knowledgeSummary(rows: { validatedOn: string | null }[]) {
  const validated = rows.filter(row => !!row.validatedOn).length;
  return { total: rows.length, validated, pending: rows.length - validated };
}
export function filterKnowledge<T extends SearchableContent>(rows: T[], query: string, status: KnowledgeStatus): T[] {
  const term = query.trim().toLocaleLowerCase();
  return rows.filter(row => (status === "All" || !!row.validatedOn === (status === "Validated"))
    && [row.name, row.description, row.category, row.file.name].some(value => value.toLocaleLowerCase().includes(term)));
}
export function fileFormat(name: string) { return name.split(".").pop()?.toUpperCase() || "FILE"; }
export function validateKnowledgeDraft(draft: KnowledgeDraft) {
  for (const [label, value, limit] of [
    ["Content name", draft.name, 160], ["Description", draft.description, 4000], ["Content type", draft.category, 100],
  ] as const) {
    if (!value.trim() || value.trim().length > limit) throw new Error(`${label} must contain 1–${limit} characters.`);
  }
}
export function validateKnowledgeFile(file: Pick<File, "name" | "type" | "size">) {
  const extension = file.name.toLowerCase().match(/\.[^.]+$/)?.[0];
  if (!extension || !KNOWLEDGE_FILE_ACCEPT.split(",").includes(extension))
    throw new Error("Choose DOCX, PDF, PPTX, TXT or an MP4, WebM or MOV video. Excel files are not supported.");
  if (file.size <= 0 || file.size > 5 * 1024 * 1024)
    throw new Error("Choose a non-empty file up to 5 MiB.");
  return KNOWLEDGE_FILE_TYPE;
}
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1/knowledge/content${path}`, {
    ...options, signal: options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(30000)]) : AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    const body = await response.json() as { detail?: unknown };
    throw new Error(typeof body.detail === "string" ? body.detail : `Knowledge request failed (${response.status}).`);
  }
  return response.status === 204 ? undefined as T : response.json();
}
function notify() { globalThis.dispatchEvent(new Event("itom-knowledge-changed")); }
export async function listKnowledge(signal?: AbortSignal): Promise<KnowledgeRecord[]> {
  const rows: KnowledgeRecord[] = [];
  let page = 1;
  while (true) {
    const result = await request<{ items: KnowledgeRecord[]; total_pages: number }>(`?page=${page}&page_size=100`, { signal });
    rows.push(...result.items);
    if (page >= result.total_pages) return rows;
    page++;
  }
}
function fileBody(file: File): Promise<{ name: string; type: string; data: string }> {
  const type = validateKnowledgeFile(file);
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("File could not be read. Choose it again."));
    reader.onload = () => {
      if (typeof reader.result !== "string" || !reader.result.includes(",")) reject(new Error("File encoding failed."));
      else resolve({ name: file.name, type, data: reader.result.split(",")[1] });
    };
    reader.readAsDataURL(file);
  });
}
export async function saveKnowledge(draft: KnowledgeDraft, file: File | null, original: KnowledgeRecord | null, requestId: string, key = "") {
  validateKnowledgeDraft(draft);
  if (!file && !original) throw new Error("Choose a file.");
  if (original && !key) throw new Error("Enter the CMDB admin key.");
  const row = await request<KnowledgeRecord>(original ? `/${original.id}` : "", {
    method: original ? "PUT" : "POST", headers: { "Content-Type": "application/json", ...(original ? { Authorization: `Bearer ${key}` } : {}) },
    body: JSON.stringify({ name: draft.name.trim(), description: draft.description.trim(), category: draft.category.trim(),
      file: file ? await fileBody(file) : null,
      ...(original ? { expected_revision: original.revision } : { request_id: requestId }) }),
  });
  notify(); return row;
}
export async function validateKnowledge(record: KnowledgeRecord, reviewer: string, key: string) {
  if (!reviewer.trim()) throw new Error("Enter a reviewer name.");
  if (!key) throw new Error("Enter the CMDB admin key.");
  await request(`/${record.id}/validate`, { method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
    body: JSON.stringify({ reviewer: reviewer.trim(), expected_revision: record.revision }) });
  notify();
}
export async function deleteKnowledge(record: KnowledgeRecord, key: string) {
  if (!key) throw new Error("Enter the CMDB admin key.");
  await request(`/${record.id}?expected_revision=${record.revision}`, { method: "DELETE", headers: { Authorization: `Bearer ${key}` } }); notify();
}
