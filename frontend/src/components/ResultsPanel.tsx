"use client";

import { useState } from "react";
import type { JobStatusResponse } from "@/lib/api";
import { buildSummary, formatSummarySentence, type TabId } from "@/lib/summary";
import { SimilarityMeter } from "@/components/SimilarityMeter";
import { DiffView } from "@/components/DiffView";
import { SideBySideView } from "@/components/SideBySideView";
import { TableDiffView } from "@/components/TableDiffView";
import { VisualDiffView } from "@/components/VisualDiffView";
import { SemanticDiffView } from "@/components/SemanticDiffView";
import { FormattingDiffView } from "@/components/FormattingDiffView";

const TAB_LABEL: Record<TabId, string> = {
  text: "Text",
  formatting: "Formatting",
  tables: "Tables",
  visual: "Pages",
  meaning: "Meaning",
};

export function ResultsPanel({ result }: { result: JobStatusResponse }) {
  const { lines, availableTabs } = buildSummary(result);
  const [activeTab, setActiveTab] = useState<TabId>(availableTabs[0] ?? "text");
  const [textView, setTextView] = useState<"side-by-side" | "inline">("side-by-side");

  if (result.similarity === undefined) return null;

  return (
    <section className="flex flex-col gap-6">
      {result.warnings && result.warnings.length > 0 && (
        <div className="rounded-sm border border-mark-replace/30 bg-mark-replace-bg px-5 py-4 text-sm text-mark-replace">
          <p className="font-medium">Heads up</p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-mark-replace/90">
            {result.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Plain-language summary — this is the first thing anyone sees,
          on purpose. The detailed tabs below are for someone who wants
          to dig in, not the default view. */}
      <div className="rounded-sm border border-paper-line bg-white p-6">
        <SimilarityMeter similarity={result.similarity} />
        <p className="mt-4 text-base leading-relaxed text-ink">{formatSummarySentence(result)}</p>

        {lines.length > 0 && (
          <ul className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
            {lines.map((l) => (
              <li key={l.tabId}>
                <button
                  onClick={() => setActiveTab(l.tabId)}
                  className="text-ink underline decoration-muted decoration-dotted underline-offset-4 hover:decoration-ink"
                >
                  {l.count} {l.count === 1 ? l.label : `${l.label}s`}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {availableTabs.length > 1 && (
        <div className="flex flex-wrap gap-1 border-b border-paper-line">
          {availableTabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={[
                "rounded-t-sm border-b-2 px-4 py-2.5 text-sm font-medium transition-colors",
                activeTab === tab ? "border-ink text-ink" : "border-transparent text-muted hover:text-ink",
              ].join(" ")}
            >
              {TAB_LABEL[tab]}
            </button>
          ))}
        </div>
      )}

      <div>
        {activeTab === "text" && result.segments && (
          <div className="flex flex-col gap-3">
            <div className="flex justify-end gap-1">
              <button
                onClick={() => setTextView("side-by-side")}
                className={[
                  "rounded-sm px-3 py-1.5 text-xs font-medium transition-colors",
                  textView === "side-by-side" ? "bg-ink text-paper" : "text-muted hover:text-ink",
                ].join(" ")}
              >
                Side by side
              </button>
              <button
                onClick={() => setTextView("inline")}
                className={[
                  "rounded-sm px-3 py-1.5 text-xs font-medium transition-colors",
                  textView === "inline" ? "bg-ink text-paper" : "text-muted hover:text-ink",
                ].join(" ")}
              >
                Inline
              </button>
            </div>
            {textView === "side-by-side" ? (
              <SideBySideView segments={result.segments} />
            ) : (
              <DiffView segments={result.segments} />
            )}
          </div>
        )}
        {activeTab === "formatting" && result.formatting_diff && (
          <FormattingDiffView changes={result.formatting_diff.changes} />
        )}
        {activeTab === "tables" && result.table_diff && <TableDiffView diff={result.table_diff} />}
        {activeTab === "visual" && result.visual_diff && <VisualDiffView pages={result.visual_diff} />}
        {activeTab === "meaning" && result.semantic_diff && <SemanticDiffView diff={result.semantic_diff} />}
      </div>
    </section>
  );
}
