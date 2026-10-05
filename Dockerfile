# syntax=docker/dockerfile:1
#
# Open Meeting Scribe — source-only image (cloud mode).
# No torch/FunASR inside: local engine is not part of this image.
#
# Build:  docker build -t open-meeting-scribe .
# Run:    docker run -d --name oms -p 8000:8000 \
#           -e DASHSCOPE_API_KEY=sk-... \
#           -v oms-data:/app/data open-meeting-scribe

# ── Stage 1: build frontend (Vue 3 + Vite) ──
FROM node:20-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: runtime (FastAPI + built frontend) ──
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
# Replace any local build output with the freshly built one
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

RUN mkdir -p data/output data/recordings data/tasks data/uploads

EXPOSE 8000
CMD ["python", "cli.py", "server", "--host", "0.0.0.0", "--port", "8000"]
