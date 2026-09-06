import type { DiffSegment } from "@/lib/api";

function OriginalColumn({ segments }: { segments: DiffSegment[] }) {
  return (
    <p className="whitespace-pre-wrap font-sans text-base leading-8 text-ink">
      {segments.map((seg, i) => {
        if (seg.type === "added") return null; // this text doesn't exist in the original at all
        if (seg.type === "equal") return <span key={i}>{seg.original}</span>;
        return (
          <span
            key={i}
            className="rounded-[2px] bg-mark-remove-bg px-0.5 text-mark-remove line-through decoration-2"
          >
            {seg.original}
          </span>
        );
      })}
    </p>
  );
}

function ModifiedColumn({ segments }: { segments: DiffSegment[] }) {
  return (
    <p className="whitespace-pre-wrap font-sans text-base leading-8 text-ink">
      {segments.map((seg, i) => {
        if (seg.type === "removed") return null; // this text no longer exists at all
        if (seg.type === "equal") return <span key={i}>{seg.modified}</span>;
        return (
          <span
            key={i}
            className="rounded-[2px] bg-mark-add-bg px-0.5 text-mark-add underline decoration-mark-add decoration-2 underline-offset-2"
          >
            {seg.modified}
          </span>
        );
      })}
    </p>
  );
}

export function SideBySideView({ segments }: { segments: DiffSegment[] }) {
  return (
    <div className="rounded-sm border border-paper-line bg-white p-6">
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div>
          <div className="mb-3 text-xs uppercase tracking-[0.15em] text-muted">Original</div>
          <OriginalColumn segments={segments} />
        </div>
        <div className="border-t border-paper-line pt-6 sm:border-l sm:border-t-0 sm:pl-6 sm:pt-0">
          <div className="mb-3 text-xs uppercase tracking-[0.15em] text-muted">Modified</div>
          <ModifiedColumn segments={segments} />
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-4 border-t border-paper-line pt-4 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-[2px] bg-mark-remove" /> Removed from original
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-[2px] bg-mark-add" /> Added in modified
        </span>
      </div>
    </div>
  );
}
