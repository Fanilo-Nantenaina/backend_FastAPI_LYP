from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.fridge import Fridge
from app.schemas.fridge import FridgeCreate, FridgeResponse, FridgeUpdate
from app.utils.exceptions import FridgeNotFoundError

router = APIRouter(prefix="/fridges", tags=["Fridges"])


@router.post("", response_model=FridgeResponse, status_code=201)
def create_fridge(
    request: FridgeCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Créer un nouveau réfrigérateur (RG1)"""
    fridge = Fridge(
        user_id=current_user.id,
        name=request.name,
        location=request.location,
        config=request.config or {},
    )

    db.add(fridge)
    db.commit()
    db.refresh(fridge)
    return fridge


@router.get("", response_model=List[FridgeResponse])
def list_fridges(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Liste tous les frigos de l'utilisateur (RG1)"""
    return db.query(Fridge).filter(Fridge.user_id == current_user.id).all()


@router.get("/{fridge_id}", response_model=FridgeResponse)
def get_fridge(
    fridge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Récupérer un frigo spécifique (RG2)"""
    fridge = (
        db.query(Fridge)
        .filter(Fridge.id == fridge_id, Fridge.user_id == current_user.id)
        .first()
    )

    if not fridge:
        raise FridgeNotFoundError(fridge_id=fridge_id)
    return fridge


@router.put("/{fridge_id}", response_model=FridgeResponse)
def update_fridge(
    fridge_id: int,
    request: FridgeUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Modifier un frigo"""
    fridge = (
        db.query(Fridge)
        .filter(Fridge.id == fridge_id, Fridge.user_id == current_user.id)
        .first()
    )

    if not fridge:
        raise FridgeNotFoundError(fridge_id=fridge_id)

    if request.name is not None:
        fridge.name = request.name
    if request.location is not None:
        fridge.location = request.location
    if request.config is not None:
        fridge.config = request.config

    db.commit()
    db.refresh(fridge)
    return fridge


@router.delete("/{fridge_id}", status_code=204)
def delete_fridge(
    fridge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Supprimer un frigo (RG2)"""
    fridge = (
        db.query(Fridge)
        .filter(Fridge.id == fridge_id, Fridge.user_id == current_user.id)
        .first()
    )

    if not fridge:
        raise FridgeNotFoundError(fridge_id=fridge_id)

    db.delete(fridge)
    db.commit()
    return
