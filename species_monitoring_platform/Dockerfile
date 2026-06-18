FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend
COPY species_monitoring_platform/frontend/package.json species_monitoring_platform/frontend/package-lock.json* ./
RUN npm ci
COPY species_monitoring_platform/frontend/ ./
RUN npm run build


FROM python:3.11-slim AS python-builder

WORKDIR /build/python
COPY species_monitoring_platform/backend/requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt && \
    pip install --no-cache-dir --prefix=/install birdnetlib


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    WEB_CONCURRENCY=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libsndfile1 \
    tini && \
    rm -rf /var/lib/apt/lists/*

COPY --from=python-builder /install /usr/local

WORKDIR /app
COPY shared/ /app/shared/
COPY species_monitoring_platform/backend/ /app/backend/
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist/

RUN useradd -r -m -d /home/appuser -s /usr/sbin/nologin appuser && \
    mkdir -p /app/data /app/backend/data /app/backend/checkpoints /var/log/bird_sound_platform && \
    chown -R appuser:appuser /app /home/appuser /var/log/bird_sound_platform

USER appuser
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=40s \
    CMD curl -f "http://127.0.0.1:${PORT:-8000}/api/health" || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1}"]
