import type { JobStatusResponse } from "./api";

export type SummaryLine = {
  label: string;
  count: number;
  tabId: TabId;
};

export type TabId = "text" | "formatting" | "tables" | "visual" | "meaning";

export type CompareMode = "content" | "appearance";

export const CONTENT_TABS: TabId[] = ["text", "meaning", "tables"];
export const APPEARANCE_TABS: TabId[] = ["formatting", "visual"];

export const TAB_MODE_MAP: Record<TabId, CompareMode> = {
  text: "content",
  meaning: "content",
  tables: "content",
  formatting: "appearance",
  visual: "appearance",
};

/** Turns the raw comparison result into a small set of plain-language
 * counts — "5 text changes", "2 formatting changes" — and figures out
 * which detail tabs actually have something to show. Buckets tabs into
 * "content" (substance/data) and "appearance" (styling/pages) modes. */
export function buildSummary(result: JobStatusResponse): {
  lines: SummaryLine[];
  availableTabs: TabId[];
  contentTabs: TabId[];
  appearanceTabs: TabId[];
  totalChanges: number;
} {
  const lines: SummaryLine[] = [];
  const availableTabs: TabId[] = [];

  const textChanges = (result.stats?.added ?? 0) + (result.stats?.removed ?? 0) + (result.stats?.replaced ?? 0);
  if (textChanges > 0) {
    lines.push({ label: "text change", count: textChanges, tabId: "text" });
  }
  availableTabs.push("text"); // text tab always available — it's the baseline comparison

  if (result.formatting_diff) {
    availableTabs.push("formatting");
    const count = result.formatting_diff.stats.changed ?? 0;
    if (count > 0) lines.push({ label: "formatting change", count, tabId: "formatting" });
  }

  if (result.table_diff && result.table_diff.tables.length > 0) {
    availableTabs.push("tables");
    const count = result.table_diff.tables.reduce(
      (sum, t) => sum + (t.stats.added ?? 0) + (t.stats.removed ?? 0) + (t.stats.modified ?? 0),
      0
    );
    if (count > 0) lines.push({ label: "table change", count, tabId: "tables" });
  }

  if (result.visual_diff && result.visual_diff.length > 0) {
    availableTabs.push("visual");
    const count = result.visual_diff.filter((p) => p.similarity < 0.98).length;
    if (count > 0) lines.push({ label: "page that looks different", count, tabId: "visual" });
  }

  if (result.semantic_diff && result.semantic_diff.matches.length > 0) {
    availableTabs.push("meaning");
    const count = result.semantic_diff.matches.filter((m) => m.type !== "exact_match").length;
    if (count > 0) lines.push({ label: "paragraph with a meaning change", count, tabId: "meaning" });
  }

  const contentTabs = CONTENT_TABS.filter((t) => availableTabs.includes(t));
  const appearanceTabs = APPEARANCE_TABS.filter((t) => availableTabs.includes(t));

  const totalChanges = lines.reduce((sum, l) => sum + l.count, 0);
  return { lines, availableTabs, contentTabs, appearanceTabs, totalChanges };
}

function pluralize(label: string, count: number): string {
  return count === 1 ? label : `${label}s`;
}

export function formatSummarySentence(result: JobStatusResponse): string {
  const { lines, totalChanges } = buildSummary(result);
  const pct = Math.round((result.similarity ?? 0) * 1000) / 10;

  if (totalChanges === 0) {
    return `These documents are ${pct}% similar — no meaningful differences were found.`;
  }

  const parts = lines.map((l) => `${l.count} ${pluralize(l.label, l.count)}`);
  const breakdown =
    parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;

  return `These documents are ${pct}% similar. We found ${breakdown}.`;
}
