# AICOR backend service: API + SSE + freshness scheduler.
# The pipeline needs the repository layout (config/, pipeline/, data/, web/public/data).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AICOR_HOST=0.0.0.0 \
    AICOR_PORT=8000 \
    AICOR_DATA_DIR=/app/web/public/data \
    AICOR_LOG_DIR=/app/logs

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 aicor \
    && mkdir -p /app/logs \
    && chown -R aicor:aicor /app
USER aicor

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "backend"]
