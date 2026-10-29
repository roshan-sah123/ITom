export type ScoreMode = "combined" | "infrastructure" | "endpoints";
export type ScoreEvidence = { value: number | null; status?: string; reason?: string | null };
export type ComponentEvidence = { value?: number | null; numerator?: number; denominator?: number; usable?: boolean; reason?: string | null };

export function scorePriority(mode: ScoreMode, score?: ScoreEvidence): string {
  if (mode !== "combined" || score?.value == null) return "—";
  return score.status === "critical" ? "P1" : score.status === "warning" ? "P2" : "—";
}

export function componentEvidence(component?: ComponentEvidence): string {
  if (!component?.usable || component.value == null) return component?.reason ? `Unavailable: ${component.reason}` : "Unavailable";
  const value = `${component.value.toLocaleString("en-US", { maximumFractionDigits: 2 })}%`;
  return component.numerator != null && component.denominator != null ? `${value} (${component.numerator} / ${component.denominator})` : value;
}
