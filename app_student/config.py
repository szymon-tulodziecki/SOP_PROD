from datetime import timedelta

from core.config import BaseConfig, make_config_map


class Config(BaseConfig):
    SESSION_COOKIE_NAME = 'student_session'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)


CONFIGURATION_MAP = make_config_map(Config)
