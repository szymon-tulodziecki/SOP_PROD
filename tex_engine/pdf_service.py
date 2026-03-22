"""
tex_engine/pdf_service.py

Serwis spinający silnik TeX z modelami SQLAlchemy.
Punkt wejścia dla tras Flask – zamiast trzymać logikę generowania PDF w routes/,
wszystko jest tutaj, łącznie z mechanizmem cache SHA-256.

Użycie w routes (przykład):
    from tex_engine.pdf_service import pdf_service
    pdf_bytes = pdf_service.get_dziennik(praktyka)
    return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf",
                     as_attachment=True, download_name="dziennik.pdf")
"""

import hashlib
import io
import logging
from datetime import date

logger = logging.getLogger(__name__)


class PdfService:
    """
    Główna fasada serwisu PDF.
    Instancja singleton – importuj przez: `from tex_engine.pdf_service import pdf_service`.
    """

    def __init__(self):
        # Cache w pamięci: {klucz_sha256: bytes_pdf}
        # W produkcji zastąp Redis / tabelą DocumentCache w bazie.
        self._cache: dict[str, bytes] = {}

    # ──────────────────────────────────────────────────────────────────────────
    # Metody publiczne (jedna na każdy generowany załącznik)
    # ──────────────────────────────────────────────────────────────────────────

    def get_dziennik(self, praktyka) -> bytes:
        """
        Załącznik 6 – Dziennik praktyki.
        Wymaga: praktyka.wpisy_dziennika (list[WpisDziennika]) z relacją .efekt.
        """
        cache_key = self._cache_key("zal6", praktyka)
        if cache_key in self._cache:
            logger.debug("Cache HIT dla dziennika praktyki %s", praktyka.id)
            return self._cache[cache_key]

        from .compiler import compile_pdf
        context = self._build_context_dziennik(praktyka)
        pdf_bytes = compile_pdf("zal6_dziennik.tex.j2", context)

        self._cache[cache_key] = pdf_bytes
        return pdf_bytes

    def get_efekty(self, praktyka) -> bytes:
        """
        Załącznik 4 – Potwierdzenie efektów uczenia się.
        Wymaga: praktyka.oceny (list[OcenaPraktyki]) z relacją .efekt.
        """
        cache_key = self._cache_key("zal4", praktyka)
        if cache_key in self._cache:
            logger.debug("Cache HIT dla efektów praktyki %s", praktyka.id)
            return self._cache[cache_key]

        from .compiler import compile_pdf
        context = self._build_context_efekty(praktyka)
        pdf_bytes = compile_pdf("zal4_efekty.tex.j2", context)

        self._cache[cache_key] = pdf_bytes
        return pdf_bytes

    def get_sprawozdanie(self, praktyka, tresc: dict) -> bytes:
        """
        Załącznik 7 – Sprawozdanie studenta.

        Args:
            praktyka: obiekt Praktyka z modelu SQLAlchemy.
            tresc:    słownik z kluczami:
                        - charakterystyka_miejsca: str
                        - opis_prac: str
                        - efekty_opisy: list[str]  (13 elementów)
        """
        cache_key = self._cache_key("zal7", praktyka, extra=str(tresc))
        if cache_key in self._cache:
            return self._cache[cache_key]

        from .compiler import compile_pdf
        context = self._build_context_sprawozdanie(praktyka, tresc)
        pdf_bytes = compile_pdf("zal7_sprawozdanie.tex.j2", context)

        self._cache[cache_key] = pdf_bytes
        return pdf_bytes

    def invalidate(self, praktyka) -> None:
        """
        Unieważnia cache dla wszystkich dokumentów danej praktyki.
        Wywołaj po każdej zmianie danych (nowy wpis dziennika, zmiana oceny itp.).
        """
        for prefix in ("zal4", "zal6", "zal7"):
            key = self._cache_key(prefix, praktyka)
            self._cache.pop(key, None)
        logger.info("Cache unieważniony dla praktyki %s", praktyka.id)

    # ──────────────────────────────────────────────────────────────────────────
    # Metody pomocnicze – budowanie kontekstu
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_context_dziennik(praktyka) -> dict:
        """Buduje słownik kontekstu dla szablonu zal6_dziennik."""
        start = praktyka.start_date
        end = praktyka.end_date
        # Rok akademicki – heurystyka: jeśli praktyka zaczyna się po lipcu,
        # jest to rok N/N+1, inaczej N-1/N.
        if isinstance(start, date):
            rok = start.year if start.month <= 7 else start.year
            rok_ak = f"{rok}/{rok + 1}"
        else:
            rok_ak = "—"

        return {
            "student":          praktyka.student,
            "firma":            praktyka.zaklad,
            "sciezka":          _sciezka_label(praktyka.path_type),
            "rok_akademicki":   rok_ak,
            "data_rozpoczecia": praktyka.start_date,
            "data_zakonczenia": praktyka.end_date,
            "lacznie_godzin":   praktyka.total_hours_logged or 0,
            "wpisy":            sorted(
                praktyka.wpisy_dziennika,
                key=lambda w: w.entry_date
            ),
        }

    @staticmethod
    def _build_context_efekty(praktyka) -> dict:
        """Buduje słownik kontekstu dla szablonu zal4_efekty."""
        # Upewniamy się że mamy wszystkie 13 efektów, sortujemy po id
        oceny_sorted = sorted(praktyka.oceny, key=lambda o: o.learning_outcome_id)
        return {
            "student":        praktyka.student,
            "lacznie_godzin": praktyka.total_hours_logged or 0,
            "oceny":          oceny_sorted,
            "uwagi_uopz":     praktyka.grade_descriptive or "",
        }

    @staticmethod
    def _build_context_sprawozdanie(praktyka, tresc: dict) -> dict:
        """Buduje słownik kontekstu dla szablonu zal7_sprawozdanie."""
        start = praktyka.start_date
        if isinstance(start, date):
            rok_ak = f"{start.year}/{start.year + 1}"
        else:
            rok_ak = "—"

        efekty_opisy = tresc.get("efekty_opisy", [])
        # Fallback – jeśli nie podano opisów, generujemy puste stringi (13 efektów)
        if not efekty_opisy:
            efekty_opisy = ["" for _ in range(13)]

        return {
            "student":                praktyka.student,
            "firma":                  praktyka.zaklad,
            "rok_akademicki":         rok_ak,
            "charakterystyka_miejsca": tresc.get("charakterystyka_miejsca", ""),
            "opis_prac":              tresc.get("opis_prac", ""),
            "efekty_opisy":           efekty_opisy,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Cache helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _cache_key(prefix: str, praktyka, extra: str = "") -> str:
        """
        Generuje klucz cache SHA-256 na podstawie:
        - prefiks (zal4/zal6/zal7)
        - UUID praktyki
        - Suma kontrolna danych (updated_at lub hash wpisów)
        """
        wpisy_hash = hashlib.sha256(
            "".join(
                f"{w.entry_date}{w.duration_hours}{w.description}"
                for w in getattr(praktyka, "wpisy_dziennika", [])
            ).encode()
        ).hexdigest()[:16]

        raw = f"{prefix}:{praktyka.id}:{wpisy_hash}:{extra}"
        return hashlib.sha256(raw.encode()).hexdigest()


def _sciezka_label(path_type) -> str:
    """Zwraca polską etykietę ścieżki praktyki."""
    mapping = {
        "STANDARD":    "standardowa",
        "EMPLOYMENT":  "zatrudnienie",
        "OWN_BUSINESS": "własna działalność",
        "ERASMUS_PLUS": "Erasmus+",
    }
    val = path_type.value if hasattr(path_type, "value") else str(path_type)
    return mapping.get(val, val)


# Singleton – importuj z tego modułu
pdf_service = PdfService()
