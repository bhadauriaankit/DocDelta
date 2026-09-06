"use client";

import { useRef, useState } from "react";

type Props = {
  label: string;
  hint: string;
  file: File | null;
  onSelect: (file: File | null) => void;
};

export function FileSlot({ label, hint, file, onSelect }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const dropped = e.dataTransfer.files?.[0];
        if (dropped) onSelect(dropped);
      }}
      onClick={() => inputRef.current?.click()}
      className={[
        "group relative flex h-56 cursor-pointer flex-col items-center justify-center gap-2 rounded-sm border px-6 text-center transition-colors",
        dragOver
          ? "border-mark-replace bg-mark-replace-bg"
          : "border-paper-line bg-white hover:border-ink/40",
      ].join(" ")}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".txt,.md,.pdf,.docx,.xlsx,.csv,.pptx,.png,.jpg,.jpeg"
        className="hidden"
        onChange={(e) => onSelect(e.target.files?.[0] ?? null)}
      />

      <span className="font-serif text-xs uppercase tracking-[0.2em] text-muted">
        {label}
      </span>

      {file ? (
        <>
          <span className="max-w-full truncate font-mono text-sm text-ink">
            {file.name}
          </span>
          <span className="text-xs text-muted">
            {(file.size / 1024).toFixed(1)} KB — click or drop to replace
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onSelect(null);
              if (inputRef.current) inputRef.current.value = "";
            }}
            className="mt-1 text-xs text-mark-remove underline decoration-dotted underline-offset-4"
          >
            Remove
          </button>
        </>
      ) : (
        <>
          <span className="text-sm text-ink/70">Drag & drop, or click to browse</span>
          <span className="text-xs text-muted">{hint}</span>
        </>
      )}
    </div>
  );
}
