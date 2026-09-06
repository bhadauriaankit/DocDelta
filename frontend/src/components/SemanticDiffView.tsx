import type { ParagraphMatch, SemanticDiff } from "@/lib/api";

const TIER_LABEL: Record<string, string> = {
  exact_match: "Exact match",
  minor_wording_change: "Minor wording change",
  semantically_similar: "Similar meaning",
  meaningful_change: "Meaningful change",
  major_change: "Major change",
  added: "Added",
  removed: "Removed",
};

const TIER_STYLE: Record<string, string> = {
  exact_match: "text-muted",
  minor_wording_change: "bg-mark-add-bg text-mark-add",
  semantically_similar: "bg-mark-add-bg text-mark-add",
  meaningful_change: "bg-mark-replace-bg text-mark-replace",
  major_change: "bg-mark-remove-bg text-mark-remove",
  added: "bg-mark-add-bg text-mark-add",
  removed: "bg-mark-remove-bg text-mark-remove",
};

function MatchCard({ match }: { match: ParagraphMatch }) {
  const showBothSides = match.original && match.modified && match.type !== "exact_match";

  return (
    <div className="rounded-sm border border-paper-line bg-white p-4">
      <div className="mb-2 flex items-center gap-2 text-xs">
        <span className={`rounded px-1.5 py-0.5 font-medium uppercase tracking-wide ${TIER_STYLE[match.type] ?? ""}`}>
          {TIER_LABEL[match.type] ?? match.type}
        </span>
        {match.similarity !== undefined && match.similarity !== null && (
          <span className="text-muted">{Math.round(match.similarity * 100)}% similar</span>
        )}
        {match.confidence && (
          <span className="text-muted">
            · {match.confidence === "high" ? "high confidence" : "low confidence — close to a category boundary"}
          </span>
        )}
      </div>

      {showBothSides ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <p className="text-sm text-ink/80">{match.original}</p>
          <p className="text-sm text-ink">{match.modified}</p>
        </div>
      ) : (
        <p className={`text-sm ${match.type === "removed" ? "text-mark-remove line-through" : "text-ink/80"}`}>
          {match.original ?? match.modified}
        </p>
      )}
    </div>
  );
}

export function SemanticDiffView({ diff }: { diff: SemanticDiff }) {
  const notable = diff.matches.filter((m) => m.type !== "exact_match");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="text-xs uppercase tracking-[0.15em] text-muted">Meaning-level comparison</div>
        <div className="text-xs text-muted">
          via {diff.provider === "tfidf" ? "word-overlap similarity" : diff.provider}
        </div>
      </div>

      {diff.provider === "tfidf" && (
        <p className="text-xs text-muted">
          This uses local word-overlap matching, not true semantic understanding — a
          paraphrase using entirely different words may show as a bigger change than
          it really is.
        </p>
      )}

      {notable.length === 0 ? (
        <p className="text-sm text-muted">Every paragraph matched exactly — no wording or meaning changes detected.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {notable.map((match, i) => (
            <MatchCard key={i} match={match} />
          ))}
        </div>
      )}
    </div>
  );
}
