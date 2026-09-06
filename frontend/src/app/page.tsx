"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  createComparisonJob,
  pollJobUntilDone,
  type JobStatus,
  type JobStatusResponse,
} from "@/lib/api";
import { FileSlot } from "@/components/FileSlot";
import { ResultsPanel } from "@/components/ResultsPanel";

type UiStatus = "idle" | JobStatus | "error";

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "Queued…",
  processing: "Comparing…",
  done: "Done",
  failed: "Failed",
};

export default function Home() {
  const [original, setOriginal] = useState<File | null>(null);
  const [modified, setModified] = useState<File | null>(null);
  const [status, setStatus] = useState<UiStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<JobStatusResponse | null>(null);

  // Cancels any in-flight poll loop when the user starts a new comparison
  // (or navigates away) — otherwise an old poll could still be running
  // when a new one starts, and both would try to update state.
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => () => abortRef.current?.abort(), []);

  const isRunning = status === "queued" || status === "processing";
  const canCompare = original && modified && !isRunning;

  async function handleCompare() {
    if (!original || !modified) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setStatus("queued");
    setError(null);
    setResult(null);

    try {
      const job = await createComparisonJob(original, modified);
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
      setError(err instanceof ApiError ? err.message : "Something went wrong comparing these files.");
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
          Upload two documents.
          <br />
          See exactly what changed.
        </h1>
        <p className="mt-3 max-w-xl text-sm text-muted">
          Text, Markdown, PDF, Word, Excel, CSV, PowerPoint, and image
          comparison — with OCR for scans, font/style comparison, visual
          comparison for PDFs, and a meaning-level view that goes beyond
          word-for-word diffing.
        </p>
      </header>

      <section className="grid gap-6 sm:grid-cols-2">
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
      </section>

      <div className="flex items-center gap-4">
        <button
          onClick={handleCompare}
          disabled={!canCompare}
          className="rounded-sm bg-ink px-6 py-3 text-sm font-medium text-paper transition-opacity disabled:cursor-not-allowed disabled:opacity-30"
        >
          {isRunning ? STATUS_LABEL[status] : "Compare documents"}
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
          <p className="font-medium">We couldn&apos;t compare these files.</p>
          <p className="mt-1 text-mark-remove/90">{error}</p>
        </div>
      )}

      {status === "done" && result && <ResultsPanel result={result} />}
    </div>
  );
}
