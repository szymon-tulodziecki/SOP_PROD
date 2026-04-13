import io
import logging
import shutil
from pathlib import Path

from flask import Flask, request, send_file, jsonify

from compiler import compile_pdf, render_tex, TexCompilationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _allowed_templates() -> set[str]:
    """Zwraca nazwy plików .tex.j2 z katalogu templates."""
    return {f.name for f in TEMPLATES_DIR.glob("*.tex.j2")}


@app.route("/health")
def health():
    lualatex_ok = bool(shutil.which("lualatex"))
    templates = list(_allowed_templates())
    return jsonify({
        "status": "ok" if lualatex_ok else "degraded",
        "lualatex": lualatex_ok,
        "templates": templates,
    })


@app.route("/generuj", methods=["POST"])
def generuj():
    """
    Body JSON:
    {
        "template": "zal6_dziennik.tex.j2",
        "context":  { ... },
        "filename": "dziennik.pdf"   # opcjonalne
    }

    Odpowiedź: application/pdf (bajty pliku)
    lub        application/json z {"error": "..."} przy błędzie
    """
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Brak body JSON"}), 400

    template_name = data.get("template", "")
    context = data.get("context", {})
    filename = data.get("filename", "dokument.pdf")

    # Walidacja szablonu
    allowed = _allowed_templates()
    if template_name not in allowed:
        return jsonify({
            "error": f"Nieznany szablon: {template_name!r}",
            "available": sorted(allowed),
        }), 400

    if not isinstance(context, dict):
        return jsonify({"error": "context musi być obiektem JSON"}), 400

    try:
        pdf_bytes = compile_pdf(template_name, context)
    except TexCompilationError as e:
        logger.error("Błąd kompilacji LaTeX dla %s: %s\nLOG:\n%s", template_name, e, e.log)
        return jsonify({"error": "Błąd kompilacji dokumentu PDF."}), 500
    except Exception:
        logger.exception("Nieoczekiwany błąd dla %s", template_name)
        return jsonify({"error": "Wewnętrzny błąd serwera."}), 500

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=False)
