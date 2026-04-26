# ════════════════════════════════════════════════════════════════════
#  DeepNova v6 · Dockerfile (multi-stage para Railway / VPS)
# ════════════════════════════════════════════════════════════════════
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencias de sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instalar deps Python primero (mejor cache)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copiar código
COPY . .

# Variables runtime
ENV PORT=8000 \
    LOG_LEVEL=INFO

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:${PORT}/api/ping || exit 1

# Arranque (gunicorn ya en requirements.txt)
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --workers 2 --timeout 120"]
