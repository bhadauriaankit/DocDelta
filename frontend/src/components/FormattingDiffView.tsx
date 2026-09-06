import type { FormattingChange } from "@/lib/api";

const PROPERTY_LABEL: Record<string, string> = {
  font: "Font",
  size: "Size",
  bold: "Bold",
  italic: "Italic",
  underline: "Underline",
  color: "Color",
};

function formatValue(prop: string, value: unknown): string {
  if (value === null || value === undefined) return "default";
  if (typeof value === "boolean") return value ? "on" : "off";
  if (prop === "size") return `${value}pt`;
  if (prop === "color") return `#${value}`;
  return String(value);
}

function ChangeCard({ change }: { change: FormattingChange }) {
  const properties = Object.entries(change.changed_properties);

  return (
    <div className="rounded-sm border border-paper-line bg-white p-4">
      <p className="mb-2 text-sm text-ink/80">{change.original_text ?? change.modified_text}</p>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {properties.map(([prop, { from, to }]) => (
          <span key={prop} className="text-mark-replace">
            <span className="text-muted">{PROPERTY_LABEL[prop] ?? prop}:</span>{" "}
            {formatValue(prop, from)} → {formatValue(prop, to)}
          </span>
        ))}
      </div>
    </div>
  );
}

export function FormattingDiffView({ changes }: { changes: FormattingChange[] }) {
  const notable = changes.filter((c) => c.type === "changed");

  return (
    <div className="flex flex-col gap-4">
      <div className="text-xs uppercase tracking-[0.15em] text-muted">
        Font & style changes
      </div>
      <p className="text-xs text-muted">
        Only paragraphs where the text is the same but the font, size, or
        style changed are shown here. Wording changes are on the Text tab.
      </p>

      {notable.length === 0 ? (
        <p className="text-sm text-muted">No font or style changes detected.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {notable.map((change, i) => (
            <ChangeCard key={i} change={change} />
          ))}
        </div>
      )}
    </div>
  );
}
