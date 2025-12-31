from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.models.fridge import Fridge
from typing import Optional

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
        user_id_str = payload.get("sub")

        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        user_id = int(user_id_str)
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        return user
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
        )


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not credentials:
        return None

    try:
        payload = decode_token(credentials.credentials)
        user_id_str = payload.get("sub")

        if not user_id_str:
            return None

        user_id = int(user_id_str)
        user = db.query(User).filter(User.id == user_id).first()

        return user
    except Exception:
        return None


async def get_user_fridge(
    fridge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Fridge:
    fridge = (
        db.query(Fridge)
        .filter(Fridge.id == fridge_id, Fridge.user_id == current_user.id)
        .first()
    )

    if not fridge:
        raise HTTPException(status_code=404, detail="Fridge not found or access denied")
    return fridge


async def get_kiosk_fridge(
    fridge_id: int,
    x_kiosk_id: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Fridge:
    if not x_kiosk_id:
        raise HTTPException(status_code=401, detail="Missing X-Kiosk-ID header")

    fridge = (
        db.query(Fridge)
        .filter(
            Fridge.id == fridge_id,
            Fridge.kiosk_id == x_kiosk_id,
            Fridge.is_paired,
        )
        .first()
    )

    if not fridge:
        raise HTTPException(
            status_code=403,
            detail="Kiosk ID does not match this fridge or fridge not paired",
        )

    return fridge


def get_fridge_access_hybrid(
    fridge_id: int,
    x_kiosk_id: Optional[str] = Header(None, alias="X-Kiosk-ID"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Fridge:
    if x_kiosk_id:
        fridge = (
            db.query(Fridge)
            .filter(
                Fridge.id == fridge_id,
                Fridge.kiosk_id == x_kiosk_id,
                Fridge.is_paired,
            )
            .first()
        )

        if not fridge:
            raise HTTPException(
                status_code=403,
                detail="Access denied to this fridge or fridge not paired",
            )

        return fridge

    elif current_user:
        fridge = (
            db.query(Fridge)
            .filter(Fridge.id == fridge_id, Fridge.user_id == current_user.id)
            .first()
        )

        if not fridge:
            raise HTTPException(
                status_code=404, detail="Fridge not found or access denied"
            )

        return fridge

    else:
        raise HTTPException(
            status_code=401,
            detail="Authentication required (JWT token or X-Kiosk-ID header)",
        )
