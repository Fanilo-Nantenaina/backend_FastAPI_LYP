from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdateRequest

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Récupérer le profil de l'utilisateur connecté"""
    return current_user


@router.put("/me", response_model=UserResponse)
def update_profile(
    request: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """CU1: Gérer le Profil et les Préférences"""
    if request.name is not None:
        current_user.name = request.name
    if request.preferred_cuisine is not None:
        current_user.preferred_cuisine = request.preferred_cuisine
    if request.dietary_restrictions is not None:
        current_user.dietary_restrictions = request.dietary_restrictions
    if request.timezone is not None:
        current_user.timezone = request.timezone
    if request.prefs is not None:
        current_user.prefs = request.prefs

    db.commit()
    db.refresh(current_user)
    return current_user
