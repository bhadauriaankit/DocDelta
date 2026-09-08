# DocCompare AI

A document comparison platform, built in phases as a learning project for a
modern full-stack toolchain (Next.js, FastAPI, Celery, Postgres, MinIO,
Docker, Kubernetes). See `docs/roadmap.md` for the full phase-by-phase plan.

**Current status: Compare Modes + Paste-to-Compare** (on top of
Phase 7 & style comparison) — text/PDF/DOCX/XLSX/CSV/PPTX/image
comparison with OCR, page-level visual comparison for PDFs, row/cell
table diffing, paragraph semantic comparison, and font/style diffing.
Now features two top-level presentation modes (Content vs Appearance)
and direct clipboard paste-to-compare without saving files first — all
running on the async Postgres + Celery/Redis + MinIO pipeline.

---

## Project structure

```
doccompare-ai/
├── backend/
│   ├── app/
│   │   ├── main.py        # API: /health, POST /jobs, POST /jobs/text, GET /jobs/{id}
│   │   ├── diff_engine.py # deterministic word-level diff (difflib)
│   │   ├── schemas.py     # Pydantic request/response models
│   │   ├── config.py      # settings, read from env vars
│   │   ├── db.py          # SQLAlchemy engine/session setup + schema-staleness check
│   │   ├── db_models.py   # Document, ComparisonJob, DifferenceResult
│   │   ├── storage.py     # MinioStorage / InMemoryStorage
│   │   ├── celery_app.py  # Celery app config
│   │   ├── tasks.py       # the background comparison task
│   │   ├── table_diff.py  # row/cell-level diff for spreadsheet-like tables
│   │   ├── visual_diff.py # page-level visual (SSIM) diff for PDF vs PDF
│   │   ├── semantic_diff.py # paragraph-level meaning-based comparison
│   │   ├── formatting_diff.py # font/size/bold/italic/color comparison (DOCX/PDF)
│   │   ├── embeddings.py  # pluggable similarity providers (TF-IDF default)
│   │   └── parsers/       # format detection + text/pdf/docx/xlsx/csv/pptx/image extraction
│   ├── requirements.txt          # default deps — no heavy ML dependencies
│   ├── requirements-semantic.txt # OPTIONAL: real sentence-embeddings upgrade
│   └── tests/             # pytest suite (130 tests, no external services needed)
├── frontend/         Next.js 15 + TypeScript + Tailwind v4
│   └── src/
│       ├── app/page.tsx       # main comparison page (job create + poll, file/paste toggle)
│       ├── components/        # FileSlot, PasteTextSlot, ResultsPanel (modes + tabbed detail), SideBySideView, DiffView, FormattingDiffView, TableDiffView, VisualDiffView, SemanticDiffView
│       └── lib/
│           ├── api.ts         # typed API client
│           └── summary.ts     # plain-language summary + tab availability logic
├── docker-compose.yml  # postgres, redis, minio, backend, worker, frontend
└── docs/
    └── roadmap.md    # full 11-phase roadmap
```

## Running with Docker (recommended)

```bash
docker compose up --build
```

That's it — frontend at `http://localhost:3000`, backend at
`http://localhost:8000`. Both run their framework's dev server with hot
reload against your local source (bind-mounted into the containers), so
editing files on your host updates the running app immediately.

Stop with `Ctrl+C`, or `docker compose down` to remove the containers.

To rebuild after changing dependencies (`requirements.txt` / `package.json`):

```bash
docker compose up --build
```

### Production images

Each Dockerfile has a `prod` stage (lean, no dev/test tooling, runs as a
non-root user) that isn't wired into `docker-compose.yml` yet — Compose is
for local dev only. You can still build and run them directly:

```bash
docker build --target prod -t doccompare-backend ./backend
docker run -p 8000:8000 doccompare-backend

docker build --target prod --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 -t doccompare-frontend ./frontend
docker run -p 3000:3000 doccompare-frontend
```

These `prod` targets are what Phase 8 (Kubernetes) will actually deploy.

## Running locally without Docker

Up through Phase 3 this was straightforward. **From Phase 4 on, this is
no longer realistic** — the backend needs Postgres, Redis, and MinIO all
reachable, plus a separate Celery worker process. Docker Compose is the
supported path now. If you really want to run everything natively (e.g.
Postgres/Redis installed via Homebrew, a local MinIO binary), the pieces
are:

```bash
# terminal 1: API
cd backend && source .venv/bin/activate
DATABASE_URL=postgresql+psycopg2://doccompare:doccompare@localhost:5432/doccompare \
REDIS_URL=redis://localhost:6379/0 \
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=doccompare MINIO_SECRET_KEY=doccompare123 \
  uvicorn app.main:app --reload --port 8000

# terminal 2: worker
cd backend && source .venv/bin/activate
DATABASE_URL=... REDIS_URL=... MINIO_ENDPOINT=... \
  celery -A app.celery_app worker --loglevel=info

# terminal 3: frontend
cd frontend && cp .env.local.example .env.local && npm install && npm run dev
```

Running tests doesn't need any of this — see below.

## What Phase 1 does (and deliberately doesn't)

- Accepts two `.txt` or `.md` files, up to 5 MB each
- Computes a word-level diff with Python's `difflib`, entirely in-memory
- Returns a similarity score (0–1) plus added/removed/replaced/equal segments
- No database, no auth, no background jobs — those come in Phase 4+.

## What Phase 2 adds

- `backend/Dockerfile` and `frontend/Dockerfile` — both multi-stage, each
  with a `dev` target (hot reload, used by Compose) and a `prod` target
  (lean, non-root, no dev tooling — this is what Kubernetes will deploy
  eventually in Phase 8)
- `docker-compose.yml` — one command (`docker compose up --build`) brings
  up both services networked together
- `.dockerignore` in each service so build contexts don't ship
  `node_modules`, `.venv`, or `.git`
- `frontend/next.config.ts` now sets `output: "standalone"` so the prod
  image only ships the trimmed server bundle, not the full `node_modules`

**Note on `NEXT_PUBLIC_API_URL`:** it's set to `http://localhost:8000`
even inside Docker, not `http://backend:8000`. That's not a typo — the
frontend's `fetch()` calls run in the *user's browser*, which has no idea
what the Docker network or the `backend` service name are. Only true
server-to-server calls (which this app doesn't have yet) would use the
Docker service name.

## What Phase 3 adds

- `app/parsers/` — a small plug-in system for document formats:
  - `detection.py` — figures out the real format from **magic bytes**, not
    the filename. A `.pdf` that isn't really a PDF, or a `.docx` that's
    secretly just some other zip, gets a clear error instead of crashing
    deep inside a parser.
  - `pdf_parser.py` (PyMuPDF) — extracts text page by page. Password-
    protected PDFs get a friendly rejection; PDFs with almost no
    extractable text (likely scanned) get flagged as a **warning**, not an
    error — the comparison still runs, since OCR is a Phase 6 concern.
  - `docx_parser.py` (python-docx) — extracts paragraph text in order,
    including table cell text.
  - `registry.py` — the single `extract_text(filename, bytes)` entrypoint
    the API calls; adding a new format later (Phase 5) means adding one
    parser module and one branch here.
- Comparison accepts `.pdf` and `.docx` alongside `.txt`/`.md`, and can
  mix formats freely (compare a PDF against a DOCX, for example).
- The result gained a `warnings` field, surfaced in the UI as a banner
  (e.g. "this PDF looks scanned").
- File size limit raised from 5MB to 20MB now that PDFs/DOCX are in play.
- Two real bugs caught by tests during this phase, both fixed: PyMuPDF's
  actual exception type for a corrupted PDF didn't match what the code
  assumed, and python-docx raises `zipfile.BadZipFile` directly (not its
  own `PackageNotFoundError`) for input that isn't a zip at all. Both are
  now caught explicitly with tests locking in the behavior.

## What Phase 4 adds

This is the biggest architectural jump so far — five services instead of
two, and the API is now asynchronous.

- **`POST /jobs`** replaces `POST /compare`. It stores both files and
  returns *immediately* with a job id and `status: "queued"` — it does
  not wait for the comparison to finish. **`GET /jobs/{id}`** is how you
  get the result, by polling until `status` becomes `"done"` or
  `"failed"`.
- **PostgreSQL** — three tables (`app/db_models.py`): `Document` (one row
  per uploaded file), `ComparisonJob` (status tracking), `DifferenceResult`
  (the actual diff output, 1:1 with a finished job).
- **Celery + Redis** — the actual parsing/diffing work (unchanged from
  Phase 3) now runs in a separate `worker` container, not the API
  process. This is *why* uploads return instantly regardless of file size.
- **MinIO** — uploaded file bytes live here now, not just in a request's
  memory. `app/storage.py` is a small abstraction (`ObjectStorage`) with
  two implementations: `MinioStorage` for real use, `InMemoryStorage` for
  tests. **Important limitation, learned the hard way while building
  this**: `InMemoryStorage` is a plain Python dict — it only works when
  the API and worker are the *same process*. Tests get away with this
  because `CELERY_TASK_ALWAYS_EAGER=true` runs the "worker" synchronously
  in-process. Outside of tests, always use `STORAGE_BACKEND=minio`
  (the Docker Compose default) — the app now warns loudly at startup if
  it detects the unsafe combination.
- **Frontend polling** — `lib/api.ts` gained `createComparisonJob()` +
  `pollJobUntilDone()`; the UI shows queued → processing → done and
  cancels any in-flight poll loop (`AbortController`) if you start a new
  comparison before the old one finishes.

### Running tests

The full pytest suite (116 tests) needs **no external services** — it
swaps in SQLite (in-memory) for Postgres and `InMemoryStorage` for MinIO,
and runs Celery in "eager" mode (synchronous, in-process) instead of
needing a real worker. See `tests/conftest.py`. This is deliberate: fast
feedback while coding shouldn't require `docker compose up` first.

```bash
cd backend
source .venv/bin/activate
python -m pytest -v
```

### Verifying the real pipeline (Postgres + Redis + MinIO, separate processes)

This is what `docker compose up --build` gives you. Worth understanding
what's actually happening: the API container creates a job row and
uploads bytes to MinIO, then returns. A *completely separate* `worker`
container picks up the task from Redis, downloads the same bytes from
MinIO, runs the Phase 3 parsing/diffing logic, and writes the result back
to Postgres. The frontend polls until it sees `"done"`.

You can watch this happen: `docker compose logs -f worker` while
submitting a comparison in the browser shows the task being received and
completed in real time.

### ⚠️ If you already ran Phase 4: reset your database volume

Phase 5 adds a new column (`table_diff`) to the `difference_results`
table. This project uses `Base.metadata.create_all()` for schema setup
(see `app/db.py`) rather than a real migration tool — deliberately, to
avoid introducing Alembic before it's actually needed (see the note in
`db.py`). The consequence: `create_all()` only creates *missing* tables,
it never alters existing ones. If your Postgres data volume already has
Phase 4's `difference_results` table (without `table_diff`), new
comparisons will fail with `column "table_diff" of relation
"difference_results" does not exist`.

Fix: wipe the dev database volume and let it get recreated fresh.

```bash
docker compose down -v   # -v removes the named volumes, including postgres_data
docker compose up --build
```

This is safe for local dev data (there's nothing here you need to keep),
but it's exactly the kind of thing a real migration tool exists to avoid
in production — worth keeping in mind as a preview of why Alembic earns
its place eventually.

## What Phase 5 adds

- **Three new formats**: `.xlsx` (openpyxl), `.csv` (stdlib `csv`), and
  `.pptx` (python-pptx) — detected by magic bytes like Phase 3's formats,
  not just extension.
- **`app/table_diff.py`** — row-and-cell-level diffing for spreadsheet
  data, not just flattened text. Uses the same `difflib.SequenceMatcher`
  LCS approach as the Phase 1 text diff engine, just one level up: each
  *row* is treated as one token. This correctly isolates a row inserted
  in the middle (surrounding rows stay `"equal"`, only the new row shows
  as `"added"`) and handles unequal-length replace blocks by pairing rows
  positionally and treating leftovers as genuine additions/removals.
  **What it deliberately doesn't do**: detect a single row that moved far
  away as one "moved" operation — that would need similarity-scored
  matching across every row pair, not just nearby ones. Documented as a
  scope boundary in the module itself, not a hidden gap.
- **`ExtractedDocument.tables`** — a new optional field alongside the
  existing flattened `text`. XLSX sheets, a CSV's rows, and any tables
  found inside PPTX slides all populate this; plain text/PDF/DOCX leave
  it empty.
- **Job results gain `table_diff`** — populated only when *both*
  documents have tables. Comparing a CSV against a `.txt` file still
  works (both produce `text`), but table-diffing is skipped with an
  explanatory warning rather than silently doing nothing.
- **A deliberate deviation from the original spec**: CSV parsing uses
  Python's stdlib `csv` module instead of pandas, which the initial
  master prompt suggested. Reasoning is in `csv_parser.py`'s docstring —
  pandas infers column dtypes (a column of `"1"`, `"2"`, `"3"` becomes
  `int64`; an empty cell becomes `NaN`), which would silently create
  false differences before comparison even starts. Exact-value diffing
  needs exact-string reading, not type inference.
- **Frontend**: `TableDiffView.tsx` shows sheet/table names, added/removed
  sheets, and row-level changes with inline cell highlighting
  (`old → new`). When a table diff is present, the flattened text diff is
  collapsed into a `<details>` — spreadsheet text, once flattened, reads
  quite badly (confirmed this while testing a real Postgres-backed run:
  a two-cell change in one row produced a confusing multi-line "replace"
  block in the text view, while the table view showed it cleanly as one
  modified row with one changed cell).

### Testing notes specific to this phase

The table-diff algorithm got isolated unit tests *before* being wired
into the API — middle-row insertion, unequal-length replace blocks,
multi-sheet add/remove, rows of mismatched width — all in
`tests/test_table_diff.py`, independent of any parser or HTTP layer. Once
that held up, `tests/test_phase5_parsers.py` and the new cases in
`tests/test_api.py` cover the full pipeline: real generated XLSX/CSV/PPTX
files through `POST /jobs` → `GET /jobs/{id}` → correct `table_diff` in
the response.

Beyond the pytest suite, this phase's persistence path (a new JSON
column, `table_diff`) was also verified against a genuinely running
Postgres + Redis + S3-protocol-compatible server, across separate API and
worker processes — the same verification approach used for Phase 4,
repeated here because a new column type (nested JSON, not just flat
values) was a real, if small, risk of Postgres/SQLite behaving
differently.

## What Phase 6 adds

- **OCR** (Tesseract, via `pytesseract`) in two places:
  - `pdf_parser.py` — a PDF with no usable embedded text layer (Phase 3's
    "this looks scanned" case) now actually gets OCR'd, page by page,
    instead of just producing a warning. Capped at 20 pages per document
    to keep processing time reasonable on very long scans.
  - `image_parser.py` (new) — standalone `.png`/`.jpg`/`.jpeg` files are
    now a supported format. Unlike PDFs, every image goes through OCR
    unconditionally — there's no "real text layer" to check first.
  - Both always attach an explicit warning that OCR was used and accuracy
    may be lower than native text — this isn't a one-time caveat, it's
    surfaced on every comparison that used it, in line with the "never
    pretend uncertain results are 100% accurate" principle from the
    original spec.
- **`app/visual_diff.py`** — page-level visual comparison, PDF vs PDF
  only. Renders each page to an image (PyMuPDF) and scores similarity
  with SSIM (structural similarity, via scikit-image) rather than raw
  pixel-difference percentage — SSIM better reflects perceptual
  similarity, so sub-pixel rendering differences don't score as "totally
  different" the way naive pixel diffing would. A red-highlight overlay
  image is generated per page showing roughly where it changed.
  **Documented scope boundary**: pages are matched by position (page 1
  vs page 1), not content — an inserted page shifts everything after it,
  which will show every later page as "changed" even if its actual
  content didn't move. Same category of tradeoff as the row/sheet
  matching limitations in `table_diff.py`.
- **`GET /files/{key}`** — a new endpoint to serve the generated diff
  images to the frontend. Deliberately locked down: a regex only allows
  keys matching `diffs/<uuid>.png`, so this route can never be used to
  read back an uploaded original document (which lives under a different
  key prefix in the same MinIO bucket) — tested explicitly, including
  path-traversal attempts. This is the first place in the project the
  frontend talks to object storage at all (indirectly, through the
  backend) rather than only ever uploading to it.
- Job results gain `visual_diff`, populated only when both documents are
  PDFs — same "only when applicable, explicit skip otherwise" pattern as
  `table_diff`.
- **Frontend**: `VisualDiffView.tsx` shows each compared page with its
  similarity percentage and the red-highlight diff image, placed above
  the table/text diffs in the results view since it's usually the most
  immediately informative view for a PDF-vs-PDF comparison.

### ⚠️ Another schema change — reset your database volume again

Same situation as Phase 5: this phase adds a `visual_diff` column to
`difference_results`, and `create_all()` still won't alter an existing
table. If you're upgrading from a Phase 5 volume:

```bash
docker compose down -v
docker compose up --build
```

This will keep happening at each phase that changes the schema until
Alembic (or another real migration tool) gets introduced — see the
Phase 4 note on why that's a deliberate, not-yet-paid-down tradeoff.

### Testing notes specific to this phase

Tesseract (the actual OCR engine, not just the `pytesseract` Python
wrapper) had to be installed as a real system package for any of this to
be testable — `apt-get install tesseract-ocr`, added to *both* Dockerfile
stages (`dev` and `prod` don't share their `apt-get` steps, which is easy
to miss since they share almost everything else). All OCR tests run
against the real binary, not a mock — including one that catches a
realistic OCR quirk: a rendered word came back slightly mangled by real
Tesseract during test-writing, which is exactly why the code treats OCR
output as "best effort with a warning," never as ground truth.

`visual_diff.py` was unit-tested in isolation first (identical PDFs score
>0.99 similarity, visually different ones score lower, page-count
mismatches and different page sizes don't crash) using a fake storage
function injected as a parameter — no real or fake object store needed
to test the comparison logic itself. The `/files/{key}` endpoint's
security properties (rejecting `uploads/*` keys, path traversal, wrong
extensions) are tested explicitly, not just its happy path.

## What Phase 7 adds

- **`app/semantic_diff.py`** — paragraph-level comparison that matches
  paragraphs by *similarity*, not position (a paragraph that moved is
  still recognized as "the same paragraph, maybe reworded," not compared
  against whatever happens to sit at the same index), then classifies
  each matched pair into a tier: exact match, minor wording change,
  similar meaning, meaningful change, major change. Unmatched paragraphs
  come back as added/removed. Exact string matches are found *before* any
  similarity model runs at all — a deterministic check is strictly more
  trustworthy than a model's opinion for the one case where it's free to
  check, in line with "use AI only where it adds real value."
- **`app/embeddings.py`** — a pluggable similarity-provider abstraction.
  This is the part of the phase that changed the most from the original
  plan, for a real reason discovered while building it, not a shortcut:

  **What happened**: the roadmap called for local sentence-transformer
  embeddings. Installing that package pulled in the full **CUDA/GPU**
  build of PyTorch by default — several GB of `nvidia-*` wheels started
  downloading before even reaching the actual embedding model, on a
  project meant to run in Docker Desktop on a machine with no GPU to use
  any of it. It nearly filled this project's build environment before the
  install even finished.

  **What shipped instead**: TF-IDF + cosine similarity (`scikit-learn`)
  as the **default** — fully local, no downloads, no GPU dependency,
  installs in seconds. It's genuinely useful, but it's lexical
  (word-overlap) similarity, not true meaning-based similarity — a
  paraphrase sharing almost no words with the original ("the deadline is
  Friday" vs "must be done by end of week") will score as quite
  different, even though a human (or real embeddings) would recognize
  them as saying nearly the same thing. This limitation is tested
  explicitly (`test_tfidf_known_limitation_pure_paraphrase_scores_low`)
  rather than glossed over.

  **The upgrade path, if you want real embeddings**: see
  `backend/requirements-semantic.txt` — install PyTorch's CPU-only wheel
  first, then the optional requirements file, then set
  `SEMANTIC_PROVIDER=sentence-transformers`. If that model can't load for
  any reason (not installed, no internet for the one-time ~90MB
  download), the app logs why and falls back to TF-IDF automatically —
  comparisons keep working either way. This fallback behavior is
  genuinely tested (not just the TF-IDF path in isolation): a test
  actually sets `SEMANTIC_PROVIDER=sentence-transformers` in an
  environment where the package isn't installed and confirms the real
  import failure is caught and handled.
- **Confidence labeling**: each semantic match gets `"high"` or `"low"`
  confidence based on how close its similarity score sits to a tier
  boundary — a score of 0.79 (just under the 0.80 "similar meaning"
  cutoff) is a much shakier classification than 0.95, and the response
  says so rather than presenting every tier assignment as equally solid.
  Deterministic classifications (`exact_match`, `added`, `removed`) leave
  confidence as `null` — confidence describes a model's uncertainty, and
  applying it to a fact that isn't a model judgment would misrepresent
  what's actually going on.
- **Frontend**: `SemanticDiffView.tsx` shows each non-exact paragraph
  match side by side with its tier, similarity percentage, and confidence
  — and an explicit note when running on the TF-IDF provider, so the
  limitation above isn't just documented in a README nobody reads, it's
  visible in the UI.

### Testing notes specific to this phase

`test_embeddings.py` and `test_semantic_diff.py` were both written and
run in isolation before any wiring into the job pipeline — same
discipline as `table_diff.py` and `visual_diff.py` in earlier phases. One
test's expectation was wrong on the first run: a reworded sentence with
heavy word overlap ("submit" vs "submitted") scored lower than expected
because TF-IDF has no stemming — different word forms count as entirely
different tokens. That's real, correct TF-IDF behavior, not a bug, so the
test's expectation was corrected to match reality (and the reasoning
written into the test itself) rather than the code being bent to fit a
wrong assumption.

## Font & style comparison, and a UI overhaul (feedback-driven, not a numbered phase)

Two changes made in direct response to feedback after trying Phase 7: the
comparison view was hard to actually use, and font/style comparison
("view font and all possible type") was missing entirely. Both landed
together since they touch the same results view.

### `app/formatting_diff.py` — font/size/bold/italic/color comparison

### ⚠️ Yet another schema change

This adds a `formatting_diff` column to `difference_results`, same as
every prior phase that added a new comparison type. If upgrading from an
existing volume:

```bash
docker compose down -v
docker compose up --build
```


- Scoped to **DOCX and PDF only** — a "font" is a meaningful, reliably
  extractable concept for a word-processor document or a PDF's rendered
  text. It isn't really meaningful for XLSX/CSV, and PPTX slide
  formatting is a reasonable future extension, not covered here.
- Works at **paragraph** granularity, not per-run/per-span — reports the
  dominant font/size/color for a paragraph and whether *any* text in it
  is bold/italic, rather than diffing every individual run. Run
  boundaries between two versions of a document rarely line up cleanly
  even when the visible formatting looks identical, so per-run diffing
  is a meaningfully harder problem — documented as a scope boundary, not
  silently attempted and gotten wrong.
- Reuses the same paragraph-matching approach as `semantic_diff.py`
  (exact-match first, then similarity-based greedy matching) — but with
  one addition: below a similarity floor, two paragraphs are treated as
  unrelated (one removed, one added) rather than paired at all. Reporting
  "font changed from X to Y" between two paragraphs that aren't really
  the same content would be actively misleading, not just imprecise —
  worth a stricter rule than semantic_diff.py needs, since that module's
  output is a similarity *score* (an honest "very different" is fine)
  rather than a specific formatting claim (which implies "this is the
  same text").
- **Verified empirically, not assumed**: PyMuPDF's bold/italic detection
  relies on specific bit flags in each text span (`1<<4` for bold,
  `1<<1` for italic) that aren't obviously documented. Before writing any
  code, a real PDF was generated with `Helvetica`, `Helvetica-Bold`, and
  `Helvetica-Oblique` text and the actual flag values were printed and
  checked — the assumed bits were correct, but they were confirmed
  against real output, not copied from memory.

### UI overhaul — `ResultsPanel.tsx` and `lib/summary.ts`

The direct complaint was that results were "very bad, no one can
understand easily" — everything (text diff, table diff, visual diff,
semantic diff) was stacked in one long scroll, in a monospace font that
reads as "built for developers," with no plain-language starting point.

- **`lib/summary.ts`** builds a one-sentence, plain-language summary from
  numbers that were already in the response — "These documents are 87%
  similar. We found 5 text changes, 2 formatting changes, and 1 table
  change." — nothing here is AI-generated, it's just counting existing
  stats in one place instead of making someone piece it together from
  five separate sections.
- **`ResultsPanel.tsx`** replaces the old stacked-sections layout with a
  summary card (always visible) plus tabs (Text / Formatting / Tables /
  Pages / Meaning) that only appear when that comparison type actually
  ran — a plain-text comparison doesn't show an empty "Tables" tab. Each
  count in the summary is clickable and jumps straight to that tab.
- **`DiffView.tsx`** dropped `font-mono` for the main comparison text in
  favor of normal prose typography with more line-height — the
  monospace styling was a leftover from the "editorial redline" visual
  design and reads as source code, not a document. The color-coded
  added/removed/replaced highlighting stayed; only the base font changed.
- **`FormattingDiffView.tsx`** — new component showing font/style changes
  as plain sentences ("Font: Calibri → Arial", "Bold: off → on") rather
  than raw property dumps.
- **`SideBySideView.tsx`** — a second round of feedback after trying the
  tabbed layout: seeing one merged inline redline still wasn't as clear
  as seeing both full documents at once. This renders the Text tab as
  two columns (Original | Modified) by default, built from the exact
  same `segments` array `DiffView` already used — no new backend data
  needed. Removed text is struck through in the left column and simply
  doesn't appear on the right; added text is highlighted in the right
  column and doesn't appear on the left. A toggle switches back to the
  single-column inline view for anyone who prefers it. **Documented
  scope boundary**: this isn't line-synchronized scrolling (a genuinely
  harder problem — word-level diff segments don't map cleanly onto fixed
  line numbers on both sides) — it's two parallel highlighted texts, not
  a scroll-locked dual pane like a code review tool.

### A confusing failure mode, fixed at the source

Running this locally surfaced a real gap: adding `formatting_diff`
(above) meant yet another new database column, and — as documented
repeatedly through this README — this project's schema setup
(`create_all()`, no migration tool yet) only creates missing tables, it
never alters an existing one. Without a reset, the worker accepted jobs,
ran the *entire* comparison successfully (text diff, semantic diff,
formatting diff all completed), and only failed at the very last step —
writing the result to Postgres — with a `psycopg2.errors.UndefinedColumn`
buried in a worker stack trace. That's a genuinely confusing thing to
debug: the failure has nothing to do with *why* it looks like it failed.

Fix: **`app.db.check_schema_up_to_date()`**, called at startup by both
the API (`main.py`'s `lifespan`) and the worker
(`celery_app.py`'s `worker_process_init` signal) — not just once. It
compares the live database's actual columns against what the ORM models
expect using SQLAlchemy's inspector, and raises a clear `RuntimeError`
immediately if anything's missing, naming the exact table and column and
repeating the fix (`docker compose down -v`). Now a stale schema
crash-loops the container with an obvious message at startup instead of
looking healthy until the first real job's last step. Tested by actually
building a deliberately "old" table (missing a column) with a separate
throwaway SQLite engine and confirming the check catches it — not just
testing that a correctly-created schema passes.

## Enhancement (September 2026): Comparison Modes + Paste-to-Compare

Two user-experience improvements built on top of the Phase 7 foundation:
separating results by user intent ("did the substance change" vs "did it
look different") and removing file-upload friction for quick clipboard
comparisons.

### Feature 1: Comparison Mode Toggle — "Content" vs "Appearance"

Previously, all available tabs (Text, Formatting, Tables, Pages, Meaning)
were displayed in a single flat bar. A contract lawyer reviewing language
changes had to look past font styles and visual layouts; a designer
checking brand consistency had to navigate through semantic diffs.

- **`Content` mode** focuses on substance: **Text**, **Meaning**, and
  **Tables**.
- **`Appearance` mode** focuses on styling: **Formatting** (fonts/styles)
  and **Pages** (visual layout diffs).
- **Default state**: Every new comparison defaults to `Content` mode.
- **Dynamic tab filtering**: `buildSummary()` in `lib/summary.ts` now
  buckets tabs into `contentTabs` and `appearanceTabs`, showing only tabs
  that both match the active mode *and* have actual differences.
- **Graceful empty states**: When a comparison yields no differences for a
  mode (for example, comparing plain `.txt` files has no formatting or
  visual pages), the toggle option is disabled with a clear title tooltip,
  and if selected, renders an informative empty state explaining why,
  preventing dead-end blank panels.
- **Interactive summary jump**: The top summary card remains
  mode-agnostic ("These documents are 87% similar. We found..."), and
  clicking any individual count jumps straight to that tab while
  automatically switching to the appropriate mode.

### Feature 2: Paste-to-Compare (direct text input)

Uploading files added unnecessary friction when users simply wanted to
compare two snippets or paragraphs already copied to their clipboard.

- **Home page toggle**: Segmented control (`Upload files | Paste text`)
  lets users seamlessly switch between drag-and-drop file uploads and
  direct text entry.
- **`PasteTextSlot.tsx`**: Matches the exact visual language of
  `FileSlot.tsx` (bordered paper card, tracking header labels, matching
  proportions) with live word counts and character counts.
- **Input boundary (100,000 characters per side)**: Capped to comfortably
  accommodate ~15,000–20,000 words (the size of a lengthy legal agreement
  or multi-chapter draft) while bounding payload memory. Exceeding the
  limit triggers both client-side visual warnings and a server-side
  HTTP 413 Payload Too Large error mirroring `MAX_FILE_SIZE_BYTES`.
- **Backend adapter (`POST /jobs/text`)**: Accepts JSON body
  `{ "original_text": str, "modified_text": str }`. Reuses an extracted
  `_create_job_and_enqueue()` helper that stores UTF-8 bytes under
  synthetic filenames (`pasted-original.txt` / `pasted-modified.txt`) in
  `ObjectStorage`. The downstream Celery task, format detection, diffing,
  and Postgres persistence execute without a single line changed.
- **Typed client**: `createComparisonJobFromText()` in `lib/api.ts` funnels
  into the existing `pollJobUntilDone()` polling loop.
- **Side-by-side / Inline toggle**: Automatically works for pasted text
  since the adapter produces standard `segments` array in the job result.

### Testing & Verification

- **Pytest suite expanded to 126 tests** (no external services needed):
  - `test_create_text_job_happy_path`: verifies 202 Accepted and job queued.
  - `test_create_text_job_oversized_input_rejection`: confirms HTTP 413
    rejection for >100k characters on either original or modified side.
  - `test_create_text_job_empty_string_handling`: ensures both empty and
    single-sided empty inputs complete cleanly with correct similarity and
    segments without 500 errors.
  - `test_create_text_job_end_to_end_diff_and_none_fields`: confirms text
    diff segments are produced while `formatting_diff`, `visual_diff`, and
    `table_diff` are safely `None`.
  - `test_create_text_job_validation_error`: confirms HTTP 422 for missing
    payload fields.
- **Frontend build**: TypeScript compilation and Next.js static build
  passed with 0 errors.

## Fix (September 2026): Side-by-Side View Misalignment

Fixes an issue where comparing documents with structural formatting differences (e.g. DOCX vs. PDF extractions of legal contracts, or documents with inserted clauses) displayed unrelated clauses opposite each other in the side-by-side Text view.

### The Problem

When comparing a DOCX and PDF version of the same document, the side-by-side view showed unrelated clauses horizontally aligned on the same row. For example, the left column showed clauses `1.11`, `1.11.1`, and `1.11.2` (marked as removed) while the right column at that exact horizontal position showed clauses `1.8` and `1.9` (completely unrelated content).

### Root Cause

Previously, `SideBySideView.tsx` rendered both columns by iterating through the single flat `segments` array produced by the word-level `difflib.SequenceMatcher` in `diff_engine.py`. The left column rendered segments where `type != "added"`, while the right column rendered segments where `type != "removed"`.

Because PDF text extractors and DOCX parsers segment whitespace, lines, and structural blocks differently (or when paragraphs are added/deleted earlier in a document), the token counts skipped on either side diverged quickly. As diff segments accumulated down the page, the left and right columns drifted vertically out of sync, displaying unrelated sections on the same row.

### Solution: Paragraph-Aligned Rows with Word-Level Sub-Diffs (Option B)

Rather than rendering two independent columns from a flat token stream, the side-by-side view now aligns horizontally by **paragraph matches** (`semantic_diff.matches`), computing word-level diffs specifically within each matched row:

1. **Word-Level Sub-Diffs per Match (`app/semantic_diff.py` & `schemas.py`)**:
   - `ParagraphMatch` model extended with `segments: list[DiffSegment]`.
   - For identical paragraphs (`match_type == "exact"`), emits a single `equal` segment without redundant diff computation.
   - For reworded or modified paragraphs (`match_type in ("reworded", "major_change")`), executes `diff_engine.compare_text(original, modified)` to compute word-level diffs bounded strictly within that paragraph pair.
   - For single-sided changes (`match_type == "added"` or `"removed"`), emits an `added` or `removed` segment.
2. **Document-Flow Match Ordering (`_order_matches()`)**:
   - Matches previously clustered all exact matches at the top of the list. They are now arranged in true reading order using original document positions, with added paragraphs placed via linear interpolation relative to surrounding content.
3. **Aligned Grid Component (`SideBySideView.tsx`)**:
   - Renders synchronized horizontal rows (`OriginalCell` and `ModifiedCell`):
     - **Matched / Changed rows**: Left cell shows original text, right cell shows modified text. Changed words are highlighted in-place (red strike-through on original, green highlight on modified) using `match.segments`.
     - **Removed paragraphs**: Left cell displays deleted text; right cell shows a clear `(Removed in modified)` placeholder gap.
     - **Added paragraphs**: Left cell shows a `(Not present in original)` placeholder gap; right cell displays added text.
   - **Graceful Fallback**: If semantic matches are unavailable (e.g. semantic comparison disabled or not computed), automatically falls back to legacy segment-based rendering (`FallbackOriginalColumn` / `FallbackModifiedColumn`).
   - `DiffView.tsx` (Inline View) remains unchanged, continuing to render the document-level diff sequence.

### Performance & Scaling

Computing word-level diffs on individual paragraph pairs scales linearly with document length ($O(N \cdot k^2)$, where $k$ is average paragraph length) and avoids the quadratic overhead of global token diffs on large documents. A synthetic test with 120 paragraphs (over 40,000 words) executes in under 0.8 seconds.

### Testing & Verification

- **Pytest suite expanded to 130 tests**:
  - `test_paragraph_match_includes_word_level_segments`: verifies `segments` field population across exact, reworded, added, and removed paragraph pairs.
  - `test_matches_preserve_document_order`: confirms matches retain linear document sequence instead of clustering exact matches.
  - `test_long_document_performance_and_scaling`: tests 120 paragraphs for correctness and sub-second performance.
  - `test_semantic_diff_response_includes_segments_in_matches`: verifies the API schema correctly serializes `segments` inside `semantic_diff.matches`.
- **Frontend Build**: TypeScript type-checking and Next.js static build compile cleanly with 0 errors.

## Next up: Phase 8

Kubernetes — taking the now five-service Docker Compose setup and
learning to run it on a local cluster (k3d or minikube), starting with
raw manifests before reaching for Helm.
