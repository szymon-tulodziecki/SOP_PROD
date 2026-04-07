from flask import Blueprint

zarzadzanie_bp = Blueprint('zarzadzanie', __name__)

from . import uzytkownicy, praktyki, firmy, komisja, dziekan
