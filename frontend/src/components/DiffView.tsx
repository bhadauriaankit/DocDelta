import type { DiffSegment } from "@/lib/api";

function Segment({ seg, index }: { seg: DiffSegment; index: number }) {
  switch (seg.type) {
    case "equal":
      return <span key={index}>{seg.original}</span>;
    case "added":
      return (
        <span
          key={index}
          className="rounded-[2px] bg-mark-add-bg px-0.5 text-mark-add underline decoration-mark-add decoration-2 underline-offset-2"
        >
          {seg.modified}
        </span>
      );
    case "removed":
      return (
        <span
          key={index}
          className="rounded-[2px] bg-mark-remove-bg px-0.5 text-mark-remove line-through decoration-2"
        >
          {seg.original}
        </span>
      );
    case "replaced":
      return (
        <span key={index} className="whitespace-pre-wrap">
          <span className="rounded-[2px] bg-mark-remove-bg px-0.5 text-mark-remove line-through decoration-2">
            {seg.original}
          </span>
          <span className="mx-0.5 text-muted">→</span>
          <span className="rounded-[2px] bg-mark-replace-bg px-0.5 text-mark-replace underline decoration-mark-replace decoration-2 underline-offset-2">
            {seg.modified}
          </span>
        </span>
      );
    default:
      return null;
  }
}

export function DiffView({ segments }: { segments: DiffSegment[] }) {
  return (
    <div className="rounded-sm border border-paper-line bg-white p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs uppercase tracking-[0.15em] text-muted">
          Word-by-word comparison
        </div>
        <div className="flex flex-wrap gap-4 text-xs text-muted">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-[2px] bg-mark-add" /> Added
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-[2px] bg-mark-remove" /> Removed
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-[2px] bg-mark-replace" /> Replaced
          </span>
        </div>
      </div>
      <p className="whitespace-pre-wrap font-sans text-base leading-8 text-ink">
        {segments.map((seg, i) => (
          <Segment key={i} seg={seg} index={i} />
        ))}
      </p>
    </div>
  );
}
