type Props = {
  similarity: number; // 0..1
};

export function SimilarityMeter({ similarity }: Props) {
  const pct = Math.round(similarity * 1000) / 10;
  const color =
    pct >= 90 ? "var(--mark-add)" : pct >= 60 ? "var(--mark-replace)" : "var(--mark-remove)";

  return (
    <div className="flex items-center gap-4">
      <div className="font-serif text-4xl tabular-nums" style={{ color }}>
        {pct}%
      </div>
      <div className="flex-1">
        <div className="mb-1 text-xs uppercase tracking-[0.15em] text-muted">
          Overall similarity
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-paper-line">
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${pct}%`, background: color }}
          />
        </div>
      </div>
    </div>
  );
}
