from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
# Globalny bezpiecznik anty-flood; trasy wrażliwe mają własne, ostrzejsze limity.
limiter = Limiter(key_func=get_remote_address, default_limits=['200 per minute'])
