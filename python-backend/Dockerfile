# Multi-stage Dockerfile — UrjaRakshak python-backend
# Python 3.11 / FastAPI

# ─────────────────────────────────────────────────────────────────────
# Stage 1: build dependencies
# ─────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ─────────────────────────────────────────────────────────────────────
# Stage 2: production image
# ─────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Non-root user
RUN useradd -m -u 1000 urja \
    && mkdir -p /app /app/logs \
    && chown -R urja:urja /app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /home/urja/.local

# Copy application source
COPY --chown=urja:urja . .

ENV PATH=/home/urja/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production

USER urja

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
