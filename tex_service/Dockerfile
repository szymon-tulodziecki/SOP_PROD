FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUTF8=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-luatex \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-lang-polish \
    fonts-dejavu \
    fonts-liberation \
    lmodern \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY sanitizer.py compiler.py app.py check_lualatex_version.py ./
COPY templates/ ./templates/

# Konfiguracja bezpieczeństwa TeX: openin_any=p, openout_any=p, shell_escape=f
# Plik jest kopiowany do katalogu przeszukiwanego przez kpsewhich TEXMFLOCAL.
COPY texmf.cnf /etc/texmf/texmf.d/99-security.cnf
# Konfiguracja TeX + weryfikacja wersji LuaLaTeX (>= 1.17.0, CVE-2023-32700) + użytkownik nieuprzywilejowany
RUN update-updmap --quiet 2>/dev/null || true \
    && texhash 2>/dev/null || true \
    && lualatex --version | head -1 \
    && python3 check_lualatex_version.py \
    && addgroup --system appgroup \
    && adduser --system --ingroup appgroup --no-create-home appuser \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 5002

CMD ["gunicorn", "--bind", "0.0.0.0:5002", "--workers", "2", "--timeout", "120", "app:app"]
