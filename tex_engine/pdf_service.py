"""
tex_engine/pdf_service.py
Klasa abstrakcyjna PDF Service - w przyszłości można przenieść całą logikę tutaj
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PDFServiceInterface:
    """
    Interface dla usługi generowania PDF - w przyszłości można
    przenieść całą logikę budowania kontekstu tutaj
    """

    def build_context_dziennik(self, zapis) -> Dict[str, Any]:
        """Buduje kontekst dla szablonu dziennika"""
        raise NotImplementedError("Implementuj w konkretnej klasie")

    def build_context_efekty(self, zapis) -> Dict[str, Any]:
        """Buduje kontekst dla szablonu efektów uczenia"""
        raise NotImplementedError("Implementuj w konkretnej klasie")

    def build_context_sprawozdanie(self, zapis, tresc: Dict) -> Dict[str, Any]:
        """Buduje kontekst dla szablonu sprawozdania"""
        raise NotImplementedError("Implementuj w konkretnej klasie")


# Implementacja PDF Service dla backward compatibility
class PDFService(PDFServiceInterface):

    def _build_context_dziennik(self, zapis):
        """Buduje kontekst dla dziennika praktyki"""
        wpisy = getattr(zapis, 'wpisy_dziennika', [])
        return {
            'student': {
                'first_name': zapis.student.first_name,
                'last_name': zapis.student.last_name,
                'album_number': zapis.student.album_number,
            },
            'zapis': {
                'total_hours_logged': zapis.total_hours_logged,
                'praktyka': {
                    'rok_uczelniany': zapis.praktyka.rok_uczelniany,
                    'semestr': zapis.praktyka.semestr,
                },
            },
            'wpisy': [
                {
                    'entry_date': w.entry_date.isoformat(),
                    'duration_hours': w.duration_hours,
                    'description': w.description,
                    'efekt': {'kod': f"{w.learning_outcome_id:02d}"},
                }
                for w in sorted(wpisy, key=lambda x: x.entry_date)
            ]
        }

    def _build_context_efekty(self, zapis):
        """Buduje kontekst dla efektów uczenia się"""
        return {
            'student': {
                'nazwisko': zapis.student.last_name,
                'imie': zapis.student.first_name,
                'numer_albumu': zapis.student.album_number,
            },
            'specjalnosc': zapis.specjalnosc or '',
            'harmonogram': getattr(zapis, 'harmonogram', []),
            'efekty_uczenia': [],  # będzie uzupełniane w route
            'oceny_efektow': []    # będzie uzupełniane w route
        }

    def _build_context_sprawozdanie(self, zapis, tresc):
        """Buduje kontekst dla sprawozdania"""
        return {
            'student': {
                'imie': zapis.student.first_name,
                'nazwisko': zapis.student.last_name,
                'album_number': zapis.student.album_number,
            },
            'firma': {
                'nazwa': zapis.firma_nazwa,
            },
            'tresc': tresc,
            'zapis': zapis
        }

    def get_dziennik(self, zapis):
        """Backward compatibility - używa tex_service"""
        raise NotImplementedError("Use tex_service HTTP API instead")

    def get_efekty(self, zapis):
        """Backward compatibility - używa tex_service"""
        raise NotImplementedError("Use tex_service HTTP API instead")

    def get_sprawozdanie(self, zapis, tresc):
        """Backward compatibility - używa tex_service"""
        raise NotImplementedError("Use tex_service HTTP API instead")

    # Interface implementations
    def build_context_dziennik(self, zapis):
        return self._build_context_dziennik(zapis)

    def build_context_efekty(self, zapis):
        return self._build_context_efekty(zapis)

    def build_context_sprawozdanie(self, zapis, tresc):
        return self._build_context_sprawozdanie(zapis, tresc)


# Instancja dla backward compatibility
pdf_service = PDFService()