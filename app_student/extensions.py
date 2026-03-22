from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# New instances for the student package; they will be initialised from app factory
db = SQLAlchemy()
login_manager = LoginManager()
