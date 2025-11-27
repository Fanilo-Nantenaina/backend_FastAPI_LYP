"""
Core configuration and utilities
"""

from app.core.config import settings
from app.core.database import Base, engine, SessionLocal, get_db
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user_id,
)
from app.core.dependencies import get_current_user, get_user_fridge

__all__ = [
    "settings",
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "get_password_hash",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_current_user_id",
    "get_current_user",
    "get_user_fridge",
]
