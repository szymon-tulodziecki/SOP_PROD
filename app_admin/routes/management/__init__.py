from flask import Blueprint

zarzadzanie_bp = Blueprint("zarzadzanie", __name__)

# Import po utworzeniu blueprintu — moduły tras importują go z powrotem.
from . import (  # noqa: E402
    companies,
    committee,
    director,
    forms,
    internships,
    student_documents,
    users,
)
