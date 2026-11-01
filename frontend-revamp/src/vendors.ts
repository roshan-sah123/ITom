export type VendorFile = { name: string; data: string };
export type VendorStep = {
  what_to_do: string;
  how_to_do: string;
  image?: VendorFile | null;
};
export type VendorDraft = { vendor: string; method: string; steps: VendorStep[] };
export type VendorRecord = {
  id: number;
  serial: number;
  vendor: string;
  method: string;
  step_count: number;
  sop_name: string | null;
  validation: "Pending" | "Validated";
  validated_by: string | null;
  validated_on: string | null;
  revision: number;
};
export type VendorDetail = VendorRecord & {
  steps: Array<{
    what_to_do: string;
    how_to_do: string;
    image: { name: string; url: string } | null;
  }>;
  sop: { name: string; url: string } | null;
};

export function validateVendorDraft(draft: VendorDraft): void {
  for (const [text, label, limit] of [
    [draft.vendor, "Vendor name", 100],
    [draft.method, "Method", 80],
  ] as const) {
    if (!text.trim() || text.length > limit || /\p{C}/u.test(text))
      throw new Error(`${label} is required, up to ${limit} characters without control characters.`);
  }
  if (!draft.steps.length || draft.steps.length > 30)
    throw new Error("Provide 1–30 steps.");
  for (const step of draft.steps) {
    if (!step.what_to_do.trim() || !step.how_to_do.trim())
      throw new Error("What to do and How to do are required for every step.");
    if (step.what_to_do.length > 2000 || step.how_to_do.length > 2000)
      throw new Error("Each step field is limited to 2,000 characters.");
  }
}

export function vendorSubmissionBody(draft: VendorDraft, requestId: string, sop: VendorFile | null) {
  validateVendorDraft(draft);
  return { ...draft, request_id: requestId, sop, steps: draft.steps.map((step) => ({ ...step, image: step.image ?? null })) };
}

export async function vendorRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1/vendors/submissions${path}`, {
    ...options,
    headers: { Accept: "application/json", ...options.headers },
    signal: options.signal
      ? AbortSignal.any([options.signal, AbortSignal.timeout(30000)])
      : AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    const body = await response.json() as { detail?: string; error?: string };
    throw new Error(typeof body.detail === "string" ? body.detail : body.error ?? `Vendor request failed (HTTP ${response.status}).`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export async function readVendorFile(file: File, image: boolean): Promise<VendorFile> {
  const maximum = image ? 1.5 * 1024 * 1024 : 10 * 1024 * 1024;
  const extensions = image ? /\.(png|jpe?g|webp)$/i : /\.(pdf|docx|txt)$/i;
  if (!file.size || file.size > maximum || !extensions.test(file.name))
    throw new Error(image ? "Choose PNG, JPEG or WebP, maximum 1.5 MB." : "Choose PDF, DOCX or TXT, maximum 10 MB.");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("File could not be read. Choose it again."));
    reader.onload = () => {
      if (typeof reader.result !== "string" || !reader.result.includes(","))
        reject(new Error("File encoding failed."));
      else resolve({ name: file.name, data: reader.result.split(",")[1] });
    };
    reader.readAsDataURL(file);
  });
}
