FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUTF8=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu \
    fonts-liberation \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY celery_worker/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --no-create-home appuser \
    && chown -R appuser:appgroup /app

USER appuser

CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info", "--concurrency=2"]
