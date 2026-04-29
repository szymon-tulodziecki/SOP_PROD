FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUTF8=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-dejavu \
    fonts-liberation \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY app_admin/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bezpieczeństwo: dedykowany nieuprzywilejowany użytkownik (nie root)
RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --no-create-home appuser \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 5000

# gevent worker: współdzieli greenlets w pętli zdarzeń I/O — eliminuje blokadę
# wątku przez time.sleep w endpointach SSE przy zachowaniu --workers 2.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--worker-class", "gevent", "--worker-connections", "100", "app_admin:create_app()"]
