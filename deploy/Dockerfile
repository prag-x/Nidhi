# One-container demo deployment (Render, Railway or any Docker host).
# The web app is built into the API image and the demonstration data is loaded while the image is built, so the
# service starts in seconds. Every restart returns the demo to its clean starting state.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
# Tesseract reads scanned FDR copies and photos (OCR, on this server).
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
# Letters carry a QR code pointing at this address; set it to the address the service is published at.
ARG PUBLIC_BASE_URL=https://nidhi-signalnine-hgxy.onrender.com
ENV NIDHI_PUBLIC_BASE_URL=${PUBLIC_BASE_URL}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    NIDHI_DATABASE_URL=sqlite:////app/data/nidhi.db \
    NIDHI_MODEL_DIR=/app/data/models \
    NIDHI_UPLOAD_DIR=/app/data/uploads \
    NIDHI_STATIC_DIR=/app/static \
    NIDHI_DEMO_MODE=true \
    NIDHI_TIMEZONE=Asia/Kolkata
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/static
# Load the demonstration dataset at build time (development settings, so no secret key is needed yet).
# Stored files are encrypted at rest (AES-256-GCM). The demo image makes its own random key at build time, since the
# demo data is loaded at build time too; a real deployment passes NIDHI_FILE_KEY from its secret store instead.
ENV NIDHI_FILE_KEY_FILE=/app/data/file.key
RUN mkdir -p /app/data/uploads /app/data/samples \
    && python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())" > /app/data/file.key \
    && NIDHI_ENVIRONMENT=development python -m app.cli migrate \
    && NIDHI_ENVIRONMENT=development python -m app.cli seed --if-empty --samples /app/data/samples
ENV NIDHI_ENVIRONMENT=production
EXPOSE 8000
# Render and Railway pass the port in $PORT. One worker: live updates and the timeline sweep run in-process.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*' --timeout-graceful-shutdown 5"]
