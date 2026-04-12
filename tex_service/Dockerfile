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

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY sanitizer.py compiler.py app.py pdf_service.py ./
COPY templates/ ./templates/

# Konfiguracja bezpieczeństwa TeX: openin_any=p, openout_any=p, shell_escape=f
# Plik jest kopiowany do katalogu przeszukiwanego przez kpsewhich TEXMFLOCAL.
COPY texmf.cnf /etc/texmf/texmf.d/99-security.cnf
RUN update-updmap --quiet 2>/dev/null || true && \
    texhash 2>/dev/null || true

# Weryfikacja wersji LuaLaTeX — wymagana >= 1.17.0 (naprawa CVE-2023-32700).
# Jeśli wersja jest za stara, build się nie powiedzie.
RUN lualatex --version | head -1 && \
    python3 -c " \
import subprocess, re, sys; \
out = subprocess.check_output(['lualatex','--version'], text=True); \
m = re.search(r'Version (\d+\.\d+)', out); \
ver = tuple(int(x) for x in m.group(1).split('.')) if m else (0,0); \
sys.exit(0) if ver >= (1, 17) else sys.exit(f'LuaLaTeX {m.group(1) if m else \"?\"}  < 1.17.0 — CVE-2023-32700')"

# Bezpieczeństwo: dedykowany nieuprzywilejowany użytkownik (nie root).
# LuaLaTeX potrzebuje /tmp do plików pomocniczych — tmpfs montowany
# jest w docker-compose, więc chown /tmp nie jest wymagany.
RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --no-create-home appuser \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 5002

CMD ["gunicorn", "--bind", "0.0.0.0:5002", "--workers", "2", "--timeout", "120", "app:app"]