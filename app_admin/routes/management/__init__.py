from flask import Blueprint

zarzadzanie_bp = Blueprint('zarzadzanie', __name__)

from . import companies, committee, director, forms, internships, student_documents, users
