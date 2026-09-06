# syntax=docker/dockerfile:1

# ---- base: shared by both dev and prod ----
FROM python:3.12-slim AS base
WORKDIR /app

# Keep Python from writing .pyc files / buffering stdout — makes container
# logs show up immediately instead of being buffered.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        tesseract-ocr \
        libreoffice-writer-nogui \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- dev: used by docker-compose for local development ----
# Includes the full requirements.txt (test/lint tools) and runs uvicorn
# with --reload against a bind-mounted source directory (see compose file).
FROM base AS dev
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---- prod: lean image for later phases (CI build, k8s deploy) ----
# Re-installs only runtime deps (no pytest/ruff/httpx) into a fresh layer,
# and drops to a non-root user.
FROM python:3.12-slim AS prod
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libreoffice-writer-nogui \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app app

COPY requirements.txt .
RUN grep -vE "^(pytest|httpx|ruff|watchdog)" requirements.txt > requirements.prod.txt \
    && pip install --no-cache-dir -r requirements.prod.txt

COPY app ./app

USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
