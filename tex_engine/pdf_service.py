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


# Dummy implementacja - w przyszłości całość przeniesiona do tex_service
class DummyPDFService(PDFServiceInterface):
    def build_context_dziennik(self, zapis):
        return {"message": "Use tex_service microservice instead"}

    def build_context_efekty(self, zapis):
        return {"message": "Use tex_service microservice instead"}

    def build_context_sprawozdanie(self, zapis, tresc):
        return {"message": "Use tex_service microservice instead"}


# Instancja dla backward compatibility
pdf_service = DummyPDFService()