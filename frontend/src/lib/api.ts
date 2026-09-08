const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type DiffSegment = {
  type: "equal" | "added" | "removed" | "replaced";
  original: string;
  modified: string;
};

export type CellChange = {
  row: number;
  col: number;
  original: string;
  modified: string;
};

export type TableRowDiff = {
  type: "equal" | "added" | "removed" | "modified";
  original?: string[];
  modified?: string[];
  cell_changes: CellChange[];
};

export type TableDiff = {
  name: string;
  stats: Record<string, number>;
  rows: TableRowDiff[];
};

export type SpreadsheetDiff = {
  tables: TableDiff[];
  added_tables: string[];
  removed_tables: string[];
};

export type DifferenceRegion = {
  id: string;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  diff_type: "text" | "layout" | "image" | "table";
  severity: "high" | "medium" | "low";
  pixel_count: number;
  percentage: number;
};

export type PageVisualDebugInfo = {
  original_dims: [number, number];
  modified_dims: [number, number];
  dpi: number;
  page_size_name: string;
  scale_factor: number;
  canvas_dims: [number, number];
  alignment_offset: [number, number];
  diff_threshold: number;
  changed_pixels: number;
  total_pixels: number;
  changed_percentage: number;
};

export type PageVisualDiff = {
  page: number;
  similarity: number;
  confidence_score?: number;
  status?: "compared" | "only_in_original" | "only_in_modified";
  diff_image_key: string;
  original_image_key?: string;
  modified_image_key?: string;
  diff_only_image_key?: string;
  regions?: DifferenceRegion[];
  debug_info?: PageVisualDebugInfo;
};

export type ParagraphMatch = {
  type: "exact_match" | "minor_wording_change" | "semantically_similar" | "meaningful_change" | "major_change" | "added" | "removed";
  original?: string;
  modified?: string;
  similarity?: number;
  confidence?: "high" | "low";
  segments?: DiffSegment[];
};

export type SemanticDiff = {
  provider: string;
  matches: ParagraphMatch[];
  stats: Record<string, number>;
};

export type FormattingChangeDetail = { from: unknown; to: unknown };

export type FormattingChange = {
  type: "unchanged" | "changed" | "added" | "removed";
  original_text?: string;
  modified_text?: string;
  changed_properties: Record<string, FormattingChangeDetail>;
};

export type FormattingDiff = {
  changes: FormattingChange[];
  stats: Record<string, number>;
};

export type JobStatus = "queued" | "processing" | "done" | "failed";

export type JobStatusResponse = {
  id: string;
  status: JobStatus;
  similarity?: number;
  stats?: Record<string, number>;
  segments?: DiffSegment[];
  warnings?: string[];
  table_diff?: SpreadsheetDiff;
  visual_diff?: PageVisualDiff[];
  semantic_diff?: SemanticDiff;
  formatting_diff?: FormattingDiff;
  error?: string;
};

/** Builds the URL for a diff image returned in `visual_diff`. The backend
 * only serves keys matching "diffs/<uuid>.png" through this route (see
 * GET /files/{key} in main.py) — it can't be used to fetch an uploaded
 * original document. */
export function getFileUrl(storageKey: string): string {
  return `${API_URL}/files/${storageKey}`;
}

export class ApiError extends Error {}

async function parseErrorOrThrow(res: Response, fallback: string): Promise<never> {
  const body = await res.json().catch(() => null);
  throw new ApiError(body?.detail ?? `${fallback} (${res.status})`);
}

/** Phase 4: uploading now just starts a background job — it does NOT wait
 * for the comparison to finish. Call pollJobUntilDone() with the returned
 * id to get the actual result. */
export async function createComparisonJob(
  original: File,
  modified: File
): Promise<{ id: string; status: JobStatus }> {
  const form = new FormData();
  form.append("original", original);
  form.append("modified", modified);

  const res = await fetch(`${API_URL}/jobs`, { method: "POST", body: form });
  if (!res.ok) return parseErrorOrThrow(res, "Could not start comparison");
  return res.json();
}

/** Starts a background comparison job from two raw text strings via
 * POST /jobs/text. Returns the same { id, status } response as file upload. */
export async function createComparisonJobFromText(
  originalText: string,
  modifiedText: string
): Promise<{ id: string; status: JobStatus }> {
  const res = await fetch(`${API_URL}/jobs/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      original_text: originalText,
      modified_text: modifiedText,
    }),
  });
  if (!res.ok) return parseErrorOrThrow(res, "Could not start comparison");
  return res.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(`${API_URL}/jobs/${jobId}`);
  if (!res.ok) return parseErrorOrThrow(res, "Could not fetch job status");
  return res.json();
}

/** Polls GET /jobs/{id} every `intervalMs` until the job reaches "done" or
 * "failed". `onUpdate` fires on every poll (including intermediate
 * "queued"/"processing" states) so the caller can show live progress.
 *
 * Accepts an AbortSignal so callers can cancel an in-flight poll loop —
 * important in React, where the user might start a *new* comparison (or
 * navigate away) while an old one is still polling. Without this, two
 * poll loops could end up racing to update the same state.
 */
export async function pollJobUntilDone(
  jobId: string,
  onUpdate: (job: JobStatusResponse) => void,
  { intervalMs = 1000, signal }: { intervalMs?: number; signal?: AbortSignal } = {}
): Promise<JobStatusResponse | null> {
  while (!signal?.aborted) {
    const job = await getJobStatus(jobId);
    if (signal?.aborted) return null;
    onUpdate(job);
    if (job.status === "done" || job.status === "failed") {
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return null;
}
