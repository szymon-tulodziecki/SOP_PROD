import os


class Config:
    SESSION_COOKIE_NAME = 'student_session'
    SECRET_KEY = os.environ.get('SECRET_KEY', 'super-tajny-klucz-tylko-na-dev-xd')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql+pg8000://ans_admin:secure_password_123@localhost:5432/ans_praktyki'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    DEBUG = True
    ENV = 'development'


class ProductionConfig(Config):
    DEBUG = False
    ENV = 'production'
    SESSION_COOKIE_SECURE = True


config_dict = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
