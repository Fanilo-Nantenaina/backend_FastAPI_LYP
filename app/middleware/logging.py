import logging
from logging.config import dictConfig
from pydantic import BaseModel
from typing import Dict

class LogConfig(BaseModel):
    """Configuration de journalisation pour l'application"""
    LOGGER_NAME: str = "fridge_app_logger"
    LOG_FORMAT: str = "%(levelprefix)s | %(asctime)s | %(name)s | %(funcName)s | %(lineno)d | %(message)s"
    LOG_LEVEL: str = "INFO"

    version: int = 1
    disable_existing_loggers: bool = False
    formatters: Dict = {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": LOG_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    }
    handlers: Dict = {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "level": LOG_LEVEL,
        },
    }
    loggers: Dict = {
        LOGGER_NAME: {"handlers": ["default"], "level": LOG_LEVEL, "propagate": False},
        "app": {"handlers": ["default"], "level": LOG_LEVEL, "propagate": False},
        "uvicorn": {"handlers": ["default"], "level": "WARNING", "propagate": False},
        "uvicorn.error": {"level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["default"], "level": "WARNING", "propagate": False},
    }

def configure_logging():
    """Applique la configuration de journalisation"""
    config = LogConfig()
    dictConfig(config.dict())
    logging.basicConfig(level=config.LOG_LEVEL)