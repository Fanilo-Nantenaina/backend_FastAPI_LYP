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
    async def async_wrapper(self, *args, **kwargs):
        db: Session = self.db
        try:
            result = await func(self, *args, **kwargs)
            db.commit()
            logger.info(f"Transaction committed in {func.__name__}")
            return result
        except Exception as e:
            db.rollback()
            logger.error(f"Transaction failed in {func.__name__}: {e}", exc_info=True)
            raise

    @wraps(func)
    def sync_wrapper(self, *args, **kwargs):
        db: Session = self.db
        try:
            result = func(self, *args, **kwargs)
            db.commit()
            logger.info(f"Transaction committed in {func.__name__}")
            return result
        except Exception as e:
            db.rollback()
            logger.error(f"Transaction failed in {func.__name__}: {e}", exc_info=True)
            raise

    import asyncio

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
