export type AssetCategory = "server" | "network" | "telecom";

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
};

export type AssetSummary = {
  data_available: boolean;
  items: AssetSummaryItem[];
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
