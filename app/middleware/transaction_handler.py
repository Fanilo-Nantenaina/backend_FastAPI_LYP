from sqlalchemy.orm import Session
from functools import wraps
import logging

logger = logging.getLogger(__name__)


def transactional(func):
    """
    Décorateur pour gérer automatiquement les transactions
    Usage: @transactional sur les méthodes de service
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        db: Session = self.db
        try:
            result = func(self, *args, **kwargs)
            db.commit()
            return result
        except Exception as e:
            db.rollback()
            logger.error(f"Transaction failed in {func.__name__}: {e}", exc_info=True)
            raise

    return wrapper
