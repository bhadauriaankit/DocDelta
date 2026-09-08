"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  createComparisonJob,
  createComparisonJobFromText,
  pollJobUntilDone,
  type JobStatus,
  type JobStatusResponse,
} from "@/lib/api";
import { FileSlot } from "@/components/FileSlot";
import { PasteTextSlot } from "@/components/PasteTextSlot";
import { ResultsPanel } from "@/components/ResultsPanel";

type UiStatus = "idle" | JobStatus | "error";
type InputMode = "upload" | "paste";

const MAX_PASTE_CHARS = 100_000;

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "Queued…",
  processing: "Comparing…",
  done: "Done",
  failed: "Failed",
};

export default function Home() {
  const [inputMode, setInputMode] = useState<InputMode>("upload");
  const [original, setOriginal] = useState<File | null>(null);
  const [modified, setModified] = useState<File | null>(null);
  const [originalText, setOriginalText] = useState("");
  const [modifiedText, setModifiedText] = useState("");
  const [status, setStatus] = useState<UiStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<JobStatusResponse | null>(null);

  // Cancels any in-flight poll loop when the user starts a new comparison
  // (or navigates away) — otherwise an old poll could still be running
  // when a new one starts, and both would try to update state.
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => () => abortRef.current?.abort(), []);

  const isRunning = status === "queued" || status === "processing";
  const canCompare =
    inputMode === "upload"
      ? Boolean(original && modified && !isRunning)
      : Boolean(
          originalText.trim() &&
            modifiedText.trim() &&
            !isRunning &&
            originalText.length <= MAX_PASTE_CHARS &&
            modifiedText.length <= MAX_PASTE_CHARS
        );

  async function handleCompare() {
    if (inputMode === "upload") {
      if (!original || !modified) return;
    } else {
      if (!originalText.trim() || !modifiedText.trim()) return;
      if (originalText.length > MAX_PASTE_CHARS) {
        setError(`Original text exceeds the ${MAX_PASTE_CHARS.toLocaleString()} character limit.`);
        setStatus("error");
        return;
      }
      if (modifiedText.length > MAX_PASTE_CHARS) {
        setError(`Modified text exceeds the ${MAX_PASTE_CHARS.toLocaleString()} character limit.`);
        setStatus("error");
        return;
      }
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setStatus("queued");
    setError(null);
    setResult(null);

    try {
      const job =
        inputMode === "upload"
          ? await createComparisonJob(original!, modified!)
          : await createComparisonJobFromText(originalText, modifiedText);
      setStatus(job.status);

      const final = await pollJobUntilDone(
        job.id,
        (update) => setStatus(update.status),
        { signal: controller.signal }
      );
      if (!final) return; // aborted — a newer comparison took over

      if (final.status === "failed") {
        setError(final.error ?? "Comparison failed.");
        setStatus("error");
      } else {
        setResult(final);
        setStatus("done");
      }
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : inputMode === "upload"
          ? "Something went wrong comparing these files."
          : "Something went wrong comparing this text."
      );
      setStatus("error");
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-10 px-6 py-16">
      <header className="border-b border-paper-line pb-8">
        <div className="mb-2 text-xs uppercase tracking-[0.25em] text-muted">
          DocCompare AI
        </div>
        <h1 className="font-serif text-4xl leading-tight text-ink">
          {inputMode === "upload" ? "Upload two documents." : "Paste two texts."}
          <br />
          See exactly what changed.
        </h1>
        <p className="mt-3 max-w-xl text-sm text-muted">
          {inputMode === "upload"
            ? "Text, Markdown, PDF, Word, Excel, CSV, PowerPoint, and image comparison — with OCR for scans, font/style comparison, visual comparison for PDFs, and a meaning-level view that goes beyond word-for-word diffing."
            : "Quickly compare two blocks of text, drafts, or snippets with word-level diffing and paragraph-level meaning comparison — no file upload required."}
        </p>
      </header>

      {/* Mode toggle: Upload files vs Paste text */}
      <div className="flex items-center gap-1 self-start rounded-sm border border-paper-line bg-white p-1">
        <button
          type="button"
          onClick={() => setInputMode("upload")}
          className={[
            "rounded-sm px-4 py-1.5 text-xs font-medium transition-colors",
            inputMode === "upload" ? "bg-ink text-paper shadow-xs" : "text-muted hover:text-ink",
          ].join(" ")}
        >
          Upload files
        </button>
        <button
          type="button"
          onClick={() => setInputMode("paste")}
          className={[
            "rounded-sm px-4 py-1.5 text-xs font-medium transition-colors",
            inputMode === "paste" ? "bg-ink text-paper shadow-xs" : "text-muted hover:text-ink",
          ].join(" ")}
        >
          Paste text
        </button>
      </div>

      <section className="grid gap-6 sm:grid-cols-2">
        {inputMode === "upload" ? (
          <>
            <FileSlot
              label="Original"
              hint=".txt, .md, .pdf, .docx, .xlsx, .csv, .pptx, .png, .jpg — up to 20 MB"
              file={original}
              onSelect={setOriginal}
            />
            <FileSlot
              label="Modified"
              hint=".txt, .md, .pdf, .docx, .xlsx, .csv, .pptx, .png, .jpg — up to 20 MB"
              file={modified}
              onSelect={setModified}
            />
          </>
        ) : (
          <>
            <PasteTextSlot
              label="Original"
              placeholder="Paste the original text here…"
              value={originalText}
              onChange={setOriginalText}
              maxLength={MAX_PASTE_CHARS}
              disabled={isRunning}
            />
            <PasteTextSlot
              label="Modified"
              placeholder="Paste the modified text here…"
              value={modifiedText}
              onChange={setModifiedText}
              maxLength={MAX_PASTE_CHARS}
              disabled={isRunning}
            />
          </>
        )}
      </section>

      <div className="flex items-center gap-4">
        <button
          onClick={handleCompare}
          disabled={!canCompare}
          className="rounded-sm bg-ink px-6 py-3 text-sm font-medium text-paper transition-opacity disabled:cursor-not-allowed disabled:opacity-30"
        >
          {isRunning
            ? STATUS_LABEL[status]
            : inputMode === "upload"
            ? "Compare documents"
            : "Compare text"}
        </button>
        {isRunning && (
          <span className="text-sm text-muted">
            {status === "queued"
              ? "Waiting for a worker to pick this up…"
              : "Extracting and diffing text…"}
          </span>
        )}
      </div>

      {status === "error" && error && (
        <div className="rounded-sm border border-mark-remove/30 bg-mark-remove-bg px-5 py-4 text-sm text-mark-remove">
          <p className="font-medium">
            We couldn&apos;t compare {inputMode === "upload" ? "these files" : "this text"}.
          </p>
          <p className="mt-1 text-mark-remove/90">{error}</p>
        </div>
      )}

      {status === "done" && result && <ResultsPanel key={result.id} result={result} />}
    </div>
  );
}
