import logging
from logging.config import dictConfig
from pydantic import BaseModel
from typing import Dict

# 1. Définition du format Pydantic pour la configuration
# Ce n'est pas strictement nécessaire pour la configuration de logging, mais
# c'est une bonne pratique si vous utilisez Pydantic pour vos configurations d'app
class LogConfig(BaseModel):
    """Configuration de journalisation pour l'application"""
    LOGGER_NAME: str = "fridge_app_logger"
    LOG_FORMAT: str = "%(levelprefix)s | %(asctime)s | %(name)s | %(funcName)s | %(lineno)d | %(message)s"
    LOG_LEVEL: str = "INFO"

    # Configuration complète pour dictConfig
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
        # Les loggers des modules de votre application (ex: app.middleware.error_handler)
        "app": {"handlers": ["default"], "level": LOG_LEVEL, "propagate": False},
        # Pour uvicorn (le serveur web)
        "uvicorn": {"handlers": ["default"], "level": "WARNING", "propagate": False},
        "uvicorn.error": {"level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["default"], "level": "WARNING", "propagate": False},
    }

def configure_logging():
    """Applique la configuration de journalisation"""
    config = LogConfig()
    dictConfig(config.dict())
    # Définir le niveau de log par défaut pour les loggers non spécifiés
    logging.basicConfig(level=config.LOG_LEVEL)

# Exemple d'utilisation (pour s'assurer que le logger est configuré correctement)
# logger_test = logging.getLogger("app")
# logger_test.info("Logging configured successfully.")

# Note : Vous devriez appeler configure_logging() au démarrage de votre application
# (ex: dans main.py) pour que cette configuration prenne effet.