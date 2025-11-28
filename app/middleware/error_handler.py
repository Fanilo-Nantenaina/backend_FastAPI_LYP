from fastapi import Request, status, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
import logging

logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception):
    """Gestionnaire global d'erreurs"""

    if isinstance(exc, IntegrityError):
        logger.error(f"Database Integrity Error: {exc.orig}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Database integrity error: A resource with these attributes already exists or is linked improperly."
            },
        )

    if isinstance(exc, HTTPException):
        if exc.status_code >= 500:
            logger.error(
                f"HTTP Exception {exc.status_code}: {exc.detail}", exc_info=True
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    if isinstance(exc, (OperationalError, SQLAlchemyError)):
        logger.critical(f"Critical Database Error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "A critical database operation failed."},
        )

    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred on the server."},
    )
