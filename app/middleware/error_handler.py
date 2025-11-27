from fastapi import Request, status, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
import logging

# Le logger sera configuré par logging.py au démarrage de l'application
logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception):
    """Gestionnaire global d'erreurs"""

    # 1. Gestion des erreurs d'intégrité de la base de données (ex: contrainte UNIQUE violée)
    if isinstance(exc, IntegrityError):
        # Log l'erreur complète pour le débogage, mais retourne une erreur 409 conviviale à l'utilisateur.
        logger.error(f"Database Integrity Error: {exc.orig}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Database integrity error: A resource with these attributes already exists or is linked improperly."
            },
        )

    # 2. Gestion des erreurs standard de FastAPI (celles qui sont levées via raise HTTPException)
    if isinstance(exc, HTTPException):
        # Log uniquement si c'est une erreur serveur (5xx)
        if exc.status_code >= 500:
            logger.error(
                f"HTTP Exception {exc.status_code}: {exc.detail}", exc_info=True
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    # 3. Gestion des erreurs liées à la base de données (connexion perdue, syntaxe invalide, etc.)
    if isinstance(exc, (OperationalError, SQLAlchemyError)):
        logger.critical(f"Critical Database Error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "A critical database operation failed."},
        )

    # 4. Gestion de toutes les autres exceptions non capturées (erreurs serveur 500)
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred on the server."},
    )
