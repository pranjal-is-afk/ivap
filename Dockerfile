# ---------- Frontend build ----------
FROM node:20-bookworm-slim AS frontend

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ---------- Backend / runtime ----------
FROM python:3.11-slim-bookworm

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Frontend production build
COPY --from=frontend /app/frontend/dist frontend/dist

# Backend dependencies
COPY backend/requirements.txt backend/requirements.txt

RUN pip install --no-cache-dir \
        torch==2.3.1 \
        --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r backend/requirements.txt

# App
COPY backend/ backend/
COPY USER_MANUAL.md README.md ./

# Assets
COPY assets/videos/ assets/videos/
COPY yolo11n.pt .

RUN mkdir -p evidence assets/models \
    && chmod -R a+w evidence assets/models

ENV IBVAP_DEMO=1 \
    IBVAP_CPU_ONLY=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]