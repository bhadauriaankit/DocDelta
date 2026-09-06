# DocCompare AI — Learning Roadmap & Stack Guide

**Goal of this roadmap:** treat this less like "ship a SaaS" and more like a structured curriculum that happens to produce a real, working product. Every phase adds one or two new pieces of the stack so you're never learning 10 things at once. Docker shows up early (phase 2) because it removes "works on my machine" pain immediately. Kubernetes shows up late (phase 8) because it only makes sense once you actually have more than one service worth orchestrating — learning K8s on a single-container app teaches you very little.

---

## 0. Recommended Stack (final-state target)

You don't build all of this on day one — it's the destination the phases walk you toward.

| Layer | Choice | Why this one for learning |
|---|---|---|
| Frontend | **Next.js (App Router) + TypeScript + Tailwind CSS** | Industry-standard, huge docs/community, teaches SSR + client state together |
| Frontend viewer | **PDF.js**, custom canvas/SVG overlay for diffs | Real-world PDF rendering is a genuinely useful skill |
| Backend API | **FastAPI (Python, async)** | Best Python framework for learning async + auto OpenAPI docs + Pydantic validation |
| Background jobs | **Celery + Redis** (or **RQ** if you want something simpler first) | You *need* async processing for OCR/large files — great excuse to learn task queues |
| Database | **PostgreSQL** | Store comparison jobs, metadata, users (if any). SQL fundamentals matter |
| Object/temp storage | **MinIO** (S3-compatible, self-hostable) | Learn the S3 API without paying AWS while building; swappable for real S3 later |
| Document parsing | PyMuPDF (`fitz`), `python-docx`, `openpyxl`, `python-pptx`, `BeautifulSoup4`, `pandas` | Format-specific, matches what your spec already listed |
| OCR | **Tesseract** via `pytesseract`, or **PaddleOCR** if you want better accuracy | Free, local, no API key needed |
| Semantic comparison | Local embedding model first (**sentence-transformers**), optional LLM API later | Teaches you embeddings/vector similarity before you reach for an LLM crutch |
| Containerization | **Docker + Docker Compose** | Local multi-service dev environment |
| Orchestration | **Kubernetes** — learn locally with **k3d** or **minikube**, deploy for real later with a managed service (GKE/EKS/DigitalOcean K8s) if you want | k3d is lightweight and fast to reset, ideal for learning |
| Package/deploy manifests | **Helm** | Standard for templating K8s manifests once you have more than 2-3 services |
| CI/CD | **GitHub Actions** | Free, ubiquitous, directly transferable skill |
| Observability | **Prometheus + Grafana** (metrics), **Loki** or plain structured JSON logs (logging) | Minimal viable observability stack, all open-source |
| Testing | **pytest** (backend), **Vitest/Playwright** (frontend) | Standard modern choices |
| Auth (only when needed) | **Auth via JWT + FastAPI dependencies**, or skip entirely for local-only mode | Don't build auth until phase actually needs it |

**Rule of thumb through all phases:** get something *working end-to-end* before making it *correct*, and get it *correct* before making it *fast/scalable*. Resist the urge to build the "final" architecture in phase 1.

---

## Phase 0 — Environment & Groundwork (few days)
**Goal:** dev environment ready, no app code yet.

- Set up repo structure (`frontend/`, `backend/`, `docs/`)
- Python 3.12 + `venv` or `uv`, Node 20+ with `pnpm`
- Install FastAPI + Uvicorn, get a "hello world" `/health` endpoint running
- Install Next.js + Tailwind, get a blank page rendering
- Set up pre-commit hooks (black/ruff for Python, eslint/prettier for TS)
- Initialize Git, write a basic README

**Learning focus:** tooling hygiene, nothing fancy yet.

---

## Phase 1 — MVP: Text-Only Comparison (Monolith)
**Goal:** upload two `.txt`/`.md` files, see a line-level diff. No Docker, no DB, no auth — pure local Python + browser.

- Backend: single FastAPI endpoint `/compare` that accepts two files, runs Python's built-in `difflib`
- Frontend: two upload boxes → call API → render diff (added/removed lines colored)
- No persistence — everything in-memory, request/response only

**Learning focus:** FastAPI basics, file upload handling, calling API from Next.js, a real (if primitive) diff algorithm.

**Milestone check:** you can demo "upload two text files, see word-level differences" fully working locally.

---

## Phase 2 — Containerize Early (Docker)
**Goal:** wrap what you already have in Docker before it grows more complex. This is deliberately early so Docker becomes background noise, not a scary migration later.

- Write a `Dockerfile` for the FastAPI backend
- Write a `Dockerfile` for the Next.js frontend
- Write a `docker-compose.yml` that runs both together with hot-reload volumes for dev
- Add a `.dockerignore`

**Learning focus:** multi-stage builds, image layering, container networking, volumes for dev vs. build-time copies for prod.

**Milestone check:** `docker compose up` gives you the full working app with zero manual setup steps.

---

## Phase 3 — Add PDF & DOCX Parsing
**Goal:** extend comparison beyond plain text to the two most common office formats.

- Backend: format-detection layer (by extension + MIME sniffing, not just filename trust)
- PDF text extraction via PyMuPDF
- DOCX text extraction via `python-docx`
- Normalize all formats into a common internal "extracted document" representation (this abstraction matters — design it well now, you'll extend it repeatedly)
- Improve diff to be word-level, not just line-level (e.g. using `difflib.SequenceMatcher` or a proper diff library)

**Learning focus:** the parser-adapter pattern (one interface, many implementations) — this is the extensibility principle from your spec in practice.

---

## Phase 4 — Persistence Layer (Postgres + Background Jobs)
**Goal:** comparisons become async jobs with a stored history, not just synchronous request/response.

- Add PostgreSQL container to Compose
- Add SQLAlchemy models: `ComparisonJob`, `Document`, `DifferenceResult`
- Add Redis + Celery (or RQ) container; move comparison work into a background worker
- Frontend polls (or uses websockets later) for job status: `queued → processing → done`
- Add MinIO container for temporary file storage instead of keeping files in memory/disk ad hoc

**Learning focus:** async task queues, why you separate "accept the request" from "do the work," basic ORM usage, object storage APIs.

**Milestone check:** you now have 5 containers talking to each other (frontend, backend, worker, postgres, redis, minio) — this is genuinely a distributed system now, even if small.

---

## Phase 5 — Expand Formats + Table/Spreadsheet Comparison
**Goal:** XLSX, CSV, PPTX support; structured table diffing, not just text diffing.

- `openpyxl` for XLSX (cells, formulas, sheet structure)
- `pandas` for CSV comparison (row/column-aware diffing)
- `python-pptx` for slide text/structure
- Build a dedicated table-diff algorithm (row-matching by similarity, not just index — this is a real, interesting algorithm problem)

**Learning focus:** structured data diffing is a different problem than text diffing; you'll likely implement a simple LCS-based or heuristic row-matcher.

---

## Phase 6 — OCR + Image/Visual Comparison
**Goal:** scanned documents and image-based comparison.

- Tesseract OCR integration for scanned PDFs/images
- Page rasterization (PyMuPDF can render PDF pages to images)
- Basic visual diffing: pixel-diff / structural similarity (SSIM via `scikit-image`) between rendered pages
- Frontend: side-by-side and overlay viewer modes

**Learning focus:** image processing basics, OCR pipeline tradeoffs (speed vs. accuracy), why visual diffing is fundamentally different from text diffing.

---

## Phase 7 — Semantic Comparison Layer
**Goal:** "meaning is the same but wording differs" detection.

- Start local: `sentence-transformers` embeddings + cosine similarity for paragraph-level semantic matching
- Add a confidence scoring system (embedding similarity thresholds → similarity tiers)
- Optional: pluggable LLM-based layer (OpenAI-compatible API, or local via Ollama) for generating the human-readable "AI Summary" — but keep this *separate* from the deterministic diff engine, exactly as your spec insists (AI never overrides deterministic fact-comparison)

**Learning focus:** embeddings, vector similarity, and the important architectural lesson of keeping non-deterministic AI output isolated from ground-truth comparison logic.

---

## Phase 8 — Kubernetes (Local Learning Cluster)
**Goal:** take your now-multi-service Compose setup and learn to run it on Kubernetes locally. This is where K8s actually teaches you something, because you already have real inter-service dependencies to model.

- Install **k3d** (or minikube) locally
- Write raw K8s manifests first (Deployments, Services, ConfigMaps, Secrets, PVCs) for each service — do this manually before reaching for Helm, so you understand what Helm is templating for you
- Convert Postgres/Redis/MinIO to either in-cluster StatefulSets or managed equivalents (learn both approaches)
- Set up an Ingress controller (e.g. nginx-ingress) to route frontend/backend traffic
- Package everything into a **Helm chart** once you understand the raw YAML
- Add a `values.yaml` with dev/staging/prod overrides

**Learning focus:** this is the core K8s curriculum — Pods, Deployments, Services, ConfigMaps/Secrets, PVCs, Ingress, then Helm as the templating layer on top. Don't skip the raw-manifest step; it's where the real understanding happens.

---

## Phase 9 — CI/CD + Observability
**Goal:** automate build/test/deploy, and be able to see what's happening inside the running system.

- GitHub Actions: lint → test → build Docker images → push to a registry (GHCR is free) → (optionally) deploy to your k3d/staging cluster
- Add Prometheus for metrics (FastAPI has middleware for this — `prometheus-fastapi-instrumentator`)
- Add Grafana dashboards for request latency, job queue depth, error rates
- Structured JSON logging from all services; optionally aggregate with Loki + Grafana

**Learning focus:** the full "commit → tested → deployed → observable" loop, which is what most real engineering jobs actually look like day-to-day.

---

## Phase 10 — Security Hardening + Privacy Features
**Goal:** implement the privacy-first requirements from your spec as real, working controls, not just UI copy.

- File-type validation beyond extension (magic-byte sniffing)
- File size limits, rate limiting (e.g. `slowapi` for FastAPI)
- Sandboxed parsing (run parsers with resource limits; consider running untrusted-file parsing in a locked-down subprocess or separate low-privilege container)
- Auto-delete: TTL-based cleanup job for MinIO objects and Postgres job records
- "Local-only mode" toggle that disables any network calls (including the semantic/AI layer)
- Secrets management: move API keys/DB passwords into K8s Secrets (never in images or repo)
- Add password-protected-PDF handling flow

**Learning focus:** security isn't a checkbox — it's specific implementation decisions at each layer (input validation, isolation, secret management, data retention).

---

## Phase 11 — Testing, Accuracy Benchmarking, Polish
**Goal:** the "production-quality" pass.

- Backend: `pytest` unit tests per comparison module + integration tests for the full pipeline
- Frontend: Playwright end-to-end tests for the upload→compare→export flow
- Build a small benchmark dataset (documents with known, hand-labeled differences) and measure precision/recall/F1 for your diff engine — this is the single best exercise for understanding your own system's weaknesses
- UI polish: accessibility pass (keyboard nav, ARIA labels, contrast), dark/light mode, responsive/mobile tab layout
- Export: PDF/HTML/JSON/CSV report generation

**Learning focus:** testing discipline and the humbling experience of benchmarking your own accuracy claims instead of assuming them.

---

## Suggested Pacing (if this is a side/learning project)

- Phases 0–2: 1–2 weeks (get comfortable, don't rush Docker)
- Phases 3–5: 2–4 weeks (this is where most of the "real feature" work lives)
- Phases 6–7: 2–3 weeks (OCR/visual/semantic — genuinely hard, budget more time here)
- Phase 8 (Kubernetes): 2–3 weeks dedicated — treat this almost as its own mini-course
- Phases 9–11: ongoing/iterative, can run in parallel with later feature work

Total: realistically 3–5 months at a steady part-time pace if the goal is deep understanding rather than speed.

---

## A Few Opinionated Notes

- **Don't start with microservices.** Phases 1–4 are intentionally a monolith-that-grows. Splitting into separate deployable services too early (before Phase 8) adds operational overhead with no learning payoff yet.
- **Don't reach for Kubernetes before you have Docker Compose working well.** If Compose feels shaky, K8s will feel like magic you don't understand rather than infrastructure you control.
- **Keep the AI/semantic layer swappable from day one of Phase 7.** Define an interface (`SemanticComparer.compare(a, b) -> SimilarityResult`) so local embeddings and a future LLM API are interchangeable — this mirrors the "AI layer is modular" principle in your original spec and saves you a painful rewrite later.
- **The table-diff and visual-diff algorithms in phases 5–6 are the most intellectually interesting parts of this whole project** — budget real thinking time there rather than treating them as "just another parser."

---

Want me to go deeper on any single phase — e.g. the exact FastAPI project structure for Phase 1, the Docker Compose file for Phase 4, or a walkthrough of writing raw K8s manifests for Phase 8?
