from core.config import BaseConfig, make_config_map


class Config(BaseConfig):
    SESSION_COOKIE_NAME = 'admin_session'


CONFIGURATION_MAP = make_config_map(Config)
