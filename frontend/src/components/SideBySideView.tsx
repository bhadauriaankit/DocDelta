import type { DiffSegment, ParagraphMatch } from "@/lib/api";

function FallbackOriginalColumn({ segments }: { segments: DiffSegment[] }) {
  return (
    <p className="whitespace-pre-wrap font-sans text-base leading-8 text-ink">
      {segments.map((seg, i) => {
        if (seg.type === "added") return null;
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

function FallbackModifiedColumn({ segments }: { segments: DiffSegment[] }) {
  return (
    <p className="whitespace-pre-wrap font-sans text-base leading-8 text-ink">
      {segments.map((seg, i) => {
        if (seg.type === "removed") return null;
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

function OriginalCell({ match }: { match: ParagraphMatch }) {
  if (match.type === "added") {
    return (
      <div className="flex h-full min-h-[3rem] items-center justify-center rounded-[2px] border border-dashed border-paper-line/80 bg-paper/40 p-3 text-xs italic text-muted/60 select-none">
        (Not present in original)
      </div>
    );
  }

  if (match.type === "removed") {
    return (
      <p className="whitespace-pre-wrap font-sans text-base leading-relaxed text-mark-remove line-through decoration-2">
        {match.original}
      </p>
    );
  }

  if (match.type === "exact_match") {
    return (
      <p className="whitespace-pre-wrap font-sans text-base leading-relaxed text-ink/80">
        {match.original}
      </p>
    );
  }

  const segments = match.segments ?? [];
  if (segments.length === 0) {
    return (
      <p className="whitespace-pre-wrap font-sans text-base leading-relaxed text-ink/80">
        {match.original}
      </p>
    );
  }

  return (
    <p className="whitespace-pre-wrap font-sans text-base leading-relaxed text-ink">
      {segments.map((seg, i) => {
        if (seg.type === "added") return null;
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

function ModifiedCell({ match }: { match: ParagraphMatch }) {
  if (match.type === "removed") {
    return (
      <div className="flex h-full min-h-[3rem] items-center justify-center rounded-[2px] border border-dashed border-paper-line/80 bg-paper/40 p-3 text-xs italic text-muted/60 select-none">
        (Removed in modified)
      </div>
    );
  }

  if (match.type === "added") {
    return (
      <p className="whitespace-pre-wrap font-sans text-base leading-relaxed text-mark-add underline decoration-mark-add decoration-2 underline-offset-2">
        {match.modified}
      </p>
    );
  }

  if (match.type === "exact_match") {
    return (
      <p className="whitespace-pre-wrap font-sans text-base leading-relaxed text-ink/80">
        {match.modified}
      </p>
    );
  }

  const segments = match.segments ?? [];
  if (segments.length === 0) {
    return (
      <p className="whitespace-pre-wrap font-sans text-base leading-relaxed text-ink">
        {match.modified}
      </p>
    );
  }

  return (
    <p className="whitespace-pre-wrap font-sans text-base leading-relaxed text-ink">
      {segments.map((seg, i) => {
        if (seg.type === "removed") return null;
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

export function SideBySideView({
  segments,
  matches,
}: {
  segments: DiffSegment[];
  matches?: ParagraphMatch[];
}) {
  const visibleMatches = (matches ?? []).filter(
    (m) => Boolean(m.original?.trim() || m.modified?.trim())
  );
  const hasMatches = visibleMatches.length > 0;

  return (
    <div className="rounded-sm border border-paper-line bg-white p-6">
      <div className="mb-4 grid grid-cols-1 gap-6 border-b border-paper-line pb-3 sm:grid-cols-2">
        <div className="text-xs uppercase tracking-[0.15em] text-muted">Original</div>
        <div className="text-xs uppercase tracking-[0.15em] text-muted sm:border-l sm:border-paper-line sm:pl-6">
          Modified
        </div>
      </div>

      {hasMatches ? (
        <div className="space-y-4">
          {visibleMatches.map((match, i) => (
            <div
              key={i}
              className={[
                "rounded-sm border p-3.5 transition-colors",
                match.type === "exact_match"
                  ? "border-paper-line/60 bg-white"
                  : match.type === "added"
                  ? "border-mark-add/30 bg-mark-add-bg/10"
                  : match.type === "removed"
                  ? "border-mark-remove/30 bg-mark-remove-bg/10"
                  : "border-mark-replace/30 bg-white shadow-xs",
              ].join(" ")}
            >
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                <div className="min-w-0">
                  <OriginalCell match={match} />
                </div>
                <div className="min-w-0 border-t border-paper-line/70 pt-3 sm:border-l sm:border-t-0 sm:pl-6 sm:pt-0">
                  <ModifiedCell match={match} />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <div>
            <FallbackOriginalColumn segments={segments} />
          </div>
          <div className="border-t border-paper-line pt-6 sm:border-l sm:border-t-0 sm:pl-6 sm:pt-0">
            <FallbackModifiedColumn segments={segments} />
          </div>
        </div>
      )}

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
