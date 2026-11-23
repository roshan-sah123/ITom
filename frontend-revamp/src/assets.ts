export type AssetCategory = "server" | "network" | "telecom";

export function assetReviewLabel(category: AssetCategory, validated: boolean): string {
  return validated ? (category === "network" ? "Verified" : "Validated") : "Pending";
}

export const assetWorkbookSources: Array<{
  category: AssetCategory;
  label: string;
  kind: AssetCategory;
  tone: string;
}> = [
  { category: "server", label: "Servers", kind: "server", tone: "blue" },
  {
    category: "network",
    label: "Network devices",
    kind: "network",
    tone: "green",
  },
  { category: "telecom", label: "Telecom", kind: "telecom", tone: "amber" },
];

export type AssetSummaryItem = {
  category: AssetCategory;
  label: string;
  data_available: boolean;
  total: number | null;
  column_count?: number;
  error?: string;
  validated?: number;
  pending?: number;
  last_import?: { at: string; updated: number; added: number; removed?: number } | null;
};

export function assetImportLabel(item: AssetSummaryItem): string | null {
  const latest = item.last_import;
  const at = latest ? new Date(latest.at) : null;
  if (!latest || !at || Number.isNaN(at.getTime())) return null;
  const date = at.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const removed = latest.removed ? ` · ${latest.removed.toLocaleString("en-US")} removed` : "";
  return `Excel update ${date} · ${latest.updated.toLocaleString("en-US")} updated · ${latest.added.toLocaleString("en-US")} added${removed}`;
}

export type AssetSummary = {
  data_available: boolean;
  items: AssetSummaryItem[];
};

export type CostCenterReference = {
  data_available: boolean;
  source_file: string | null;
  columns: string[];
  items: Array<{ source_row: number; values: Record<string, string | number | null> }>;
  total: number;
};

export type AssetRow = Record<string, string | number | boolean | null>;

export type AssetInventory = {
  category: AssetCategory;
  columns: string[];
  items: AssetRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export function assetCount(source: {
  data_available: boolean;
  total: number | null;
}): string {
  const total = source.total;
  if (
    !source.data_available ||
    typeof total !== "number" ||
    !Number.isFinite(total)
  )
    return "—";
  return total.toLocaleString("en-US");
}

export function assetExportRows(inventory: AssetInventory): string[][] {
  return inventory.items.map((item) =>
    inventory.columns.map((column) => {
      const value = item[column];
      return value == null ? "" : String(value);
    }),
  );
}

export type AssetCell = { index: number; header: string; value: string | number | boolean | null };
export function assetCellDisplay(category: AssetCategory, header: string, value: AssetCell["value"]): string {
  if (value == null || value === "") return "—";
  const text = String(value);
  if ((category === "network" && /^(?:eol(?:\s+date)?|amc\s+end\s+date|(?:workbook\s+)?validated\s+on)$/i.test(header.trim()))
    || (category === "server" && /^(?:eol|amc\s+(?:start|end)\s+date|workbook\s+validated\s+on)$/i.test(header.trim()))
    || (category === "telecom" && /^amc\s+(?:status|end\s+date)$/i.test(header.trim()))) {
    const match = /^(\d{4}-\d{2}-\d{2})[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$/.exec(text);
    if (match) return match[1];
  }
  return text;
}
export type AssetReview = { header: string; value: AssetCell["value"]; validated_at: string; validated_by: string };
export type AssetRecord = {
  id: string; name: string; category: AssetCategory; source_file: string; source_sheet: string;
  source_row: number; data: AssetCell[]; field_reviews: Record<string, AssetReview>;
  is_validated: boolean; validated_at: string | null; validated_by: string | null; revision: number;
};
export type AssetRecordPage = {
  category: AssetCategory; columns: string[]; source_sheet: string; items: AssetRecord[];
  total: number; page: number; page_size: number; total_pages: number;
};
export async function assetRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1/assets${path}`, options);
  if (!response.ok) {
    const body = await response.json() as { detail?: unknown };
    throw new Error(typeof body.detail === "string" ? body.detail : `Inventory request failed (${response.status}).`);
  }
  return response.status === 204 ? undefined as T : await response.json() as T;
}
export function editedAssetValue(original: AssetCell["value"], text: string): AssetCell["value"] {
  if (text === "") return null;
  if (typeof original === "number" && Number.isFinite(Number(text))) return Number(text);
  if (typeof original === "boolean" && ["true", "false"].includes(text)) return text === "true";
  return text;
}
