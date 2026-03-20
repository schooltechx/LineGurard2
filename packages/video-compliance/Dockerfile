# ─────────────────────────────────────────────────────────────
# Stage 1: build dependencies
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps สำหรับ PyAV (ffmpeg) และ Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        ffmpeg \
        libavcodec-dev \
        libavformat-dev \
        libavutil-dev \
        libswscale-dev \
        libjpeg-dev \
        libpng-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ─────────────────────────────────────────────────────────────
# Stage 2: runtime image
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# ffmpeg runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# คัดลอก installed packages จาก builder
COPY --from=builder /install /usr/local

# คัดลอก source code
COPY app/ ./app/

# สร้างโฟลเดอร์สำหรับ SQLite DB
RUN mkdir -p /data && chmod 777 /data

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OLLAMA_BASE_URL=http://ollama:11434 \
    OLLAMA_MODEL=qwen2.5vl:3b \
    OLLAMA_TIMEOUT=180

# mount point สำหรับ persistent DB
VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
