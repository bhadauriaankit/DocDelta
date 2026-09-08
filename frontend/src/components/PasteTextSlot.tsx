"use client";

type Props = {
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  maxLength?: number;
  disabled?: boolean;
};

export function PasteTextSlot({
  label,
  placeholder,
  value,
  onChange,
  maxLength = 100_000,
  disabled = false,
}: Props) {
  const isOverLimit = value.length > maxLength;
  const wordCount = value.trim() ? value.trim().split(/\s+/).length : 0;

  return (
    <div
      className={[
        "group relative flex min-h-56 flex-col justify-between rounded-sm border p-4 transition-colors",
        isOverLimit
          ? "border-mark-remove bg-mark-remove-bg/20"
          : "border-paper-line bg-white focus-within:border-ink/40",
      ].join(" ")}
    >
      <div className="flex items-center justify-between border-b border-paper-line/60 pb-2">
        <span className="font-serif text-xs uppercase tracking-[0.2em] text-muted">
          {label}
        </span>
        {value.length > 0 && !disabled && (
          <button
            type="button"
            onClick={() => onChange("")}
            className="text-xs text-mark-remove underline decoration-dotted underline-offset-4 hover:opacity-80"
          >
            Clear
          </button>
        )}
      </div>

      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        rows={8}
        className="my-2 w-full flex-1 resize-y bg-transparent text-sm leading-relaxed text-ink placeholder:text-muted/60 focus:outline-none"
      />

      <div className="flex items-center justify-between border-t border-paper-line/60 pt-2 text-xs text-muted">
        <span>
          {wordCount.toLocaleString()} {wordCount === 1 ? "word" : "words"}
        </span>
        <span className={isOverLimit ? "font-medium text-mark-remove" : ""}>
          {value.length.toLocaleString()} / {maxLength.toLocaleString()} chars
        </span>
      </div>
    </div>
  );
}
