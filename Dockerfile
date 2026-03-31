# ============================================================================
# Sent Below - Containerized ML Training & Model Serving
# ============================================================================
# Multi-stage build:
#   Stage 1 (base)    - Python + system deps + pip packages
#   Stage 2 (train)   - Offline training pipeline with GPU support
#   Stage 3 (serve)   - FastAPI model serving endpoint (production)
#   Stage 4 (game)    - Full game with display forwarding (dev/demo)
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Base image with all Python dependencies
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

WORKDIR /app

# System deps for PyTorch and numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ai/ ai/
COPY config.py .

# ---------------------------------------------------------------------------
# Stage 2: Training pipeline (GPU-capable)
# ---------------------------------------------------------------------------
FROM base AS train

# TensorBoard for experiment tracking
RUN pip install --no-cache-dir tensorboard>=2.14.0

COPY training/ training/
COPY game/ game/
COPY main.py .

# Training output volume
VOLUME ["/app/runs", "/app/models"]

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "training.train_pipeline"]

# ---------------------------------------------------------------------------
# Stage 3: Model serving API (production deployment)
# ---------------------------------------------------------------------------
FROM base AS serve

RUN pip install --no-cache-dir fastapi>=0.104.0 uvicorn>=0.24.0

COPY serving/ serving/

# Pre-trained model volume mount
VOLUME ["/app/models"]

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

ENTRYPOINT ["uvicorn", "serving.api:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------------------------------------------------------------------------
# Stage 4: Full game (dev/demo with X11 forwarding)
# ---------------------------------------------------------------------------
FROM base AS game

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY game/ game/
COPY main.py .

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "main.py"]
