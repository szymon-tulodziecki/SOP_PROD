"""
tex_service/pdf_service.py

Klasa PDFService — buduje konteksty danych dla szablonów LaTeX.
Przeniesiona z tex_engine/pdf_service.py (tex_engine usunięty).
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PDFServiceInterface:
    """Interface dla usługi generowania PDF."""

    def build_context_dziennik(self, zapis) -> Dict[str, Any]:
        raise NotImplementedError

    def build_context_efekty(self, zapis) -> Dict[str, Any]:
        raise NotImplementedError

    def build_context_sprawozdanie(self, zapis, tresc: Dict) -> Dict[str, Any]:
        raise NotImplementedError


class PDFService(PDFServiceInterface):

    def build_context_dziennik(self, zapis) -> Dict[str, Any]:
        wpisy = getattr(zapis, 'wpisy_dziennika', [])
        return {
            'student': {
                'first_name':   zapis.student.first_name,
                'last_name':    zapis.student.last_name,
                'album_number': zapis.student.album_number,
            },
            'zapis': {
                'total_hours_logged': zapis.total_hours_logged,
                'praktyka': {
                    'rok_uczelniany': zapis.praktyka.rok_uczelniany,
                    'semestr':        zapis.praktyka.semestr,
                },
            },
            'wpisy': [
                {
                    'entry_date':       w.entry_date.isoformat(),
                    'duration_hours':   w.duration_hours,
                    'description':      w.description,
                    'efekt': {'kod': f"{w.learning_outcome_id:02d}"},
                }
                for w in sorted(wpisy, key=lambda x: x.entry_date)
            ],
        }

    def build_context_efekty(self, zapis) -> Dict[str, Any]:
        return {
            'student': {
                'nazwisko':       zapis.student.last_name,
                'imie':           zapis.student.first_name,
                'numer_albumu':   zapis.student.album_number,
            },
            'specjalnosc':      zapis.specjalnosc or '',
            'harmonogram':      getattr(zapis, 'harmonogram', []),
            'efekty_uczenia':   [],   # uzupełniane w route
            'oceny_efektow':    [],   # uzupełniane w route
        }

    def build_context_sprawozdanie(self, zapis, tresc: Dict) -> Dict[str, Any]:
        return {
            'student': {
                'imie':         zapis.student.first_name,
                'nazwisko':     zapis.student.last_name,
                'album_number': zapis.student.album_number,
            },
            'firma': {
                'nazwa': zapis.firma_nazwa,
            },
            'tresc': tresc,
            'zapis': zapis,
        }


# Singleton używany przez Flask routes i Celery tasks
pdf_service = PDFService()
