FROM python:3.12-slim AS base
# Tesseract reads scanned FDR copies and photos (OCR, on this server).
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN useradd --create-home --uid 10001 nidhi
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY alembic.ini pyproject.toml ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# Strip Windows line endings in case the repo was checked out on Windows.
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /data/uploads /data/samples /data/models && chown -R nidhi /data
USER nidhi
ENV NIDHI_UPLOAD_DIR=/data/uploads NIDHI_MODEL_DIR=/data/models
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=600s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status==200 else 1)"
ENTRYPOINT ["docker-entrypoint.sh"]
# One worker: the live-update broker and the periodic checks run in-process (see README "Scaling").
# Live-update streams never close on their own, so bound the graceful shutdown.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-graceful-shutdown", "10"]
