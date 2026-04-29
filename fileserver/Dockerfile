FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./

RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --no-create-home appuser \
    && mkdir -p /data/files \
    && chown -R appuser:appgroup /app /data

USER appuser

CMD ["gunicorn", "--bind", "0.0.0.0:5003", "--workers", "2", "app:app"]
