FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-luatex \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-lang-polish \
    lmodern \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir flask jinja2

COPY sanitizer.py compiler.py app.py ./
COPY templates/ ./templates/

EXPOSE 5002

CMD ["python", "app.py"]