from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.fridge_service import FridgeService
from app.schemas.fridge import (
    KioskInitResponse,
    PairingRequest,
    PairingResponse,
    KioskStatusResponse,
    FridgeResponse,
    FridgeUpdate,
    UpdateFridgeInfoRequest,
)

router = APIRouter(prefix="/fridges", tags=["Fridges"])


class KioskInitRequest(BaseModel):
    device_id: Optional[str] = None
    device_name: Optional[str] = None


@router.post("/kiosk/init", response_model=KioskInitResponse)
def init_kiosk(
    request: KioskInitRequest,
    db: Session = Depends(get_db),
):
    """
    Initialise un nouveau frigo (kiosk physique).
    Si device_id fourni et existe déjà → restaure le kiosk existant
    """
    service = FridgeService(db)
    result = service.init_kiosk(
        device_id=request.device_id, device_name=request.device_name
    )

    return result


@router.get("/kiosk/device/{device_id}", response_model=Dict[str, Any])
def get_kiosk_by_device_id(
    device_id: str,
    db: Session = Depends(get_db),
):
    """
    NOUVELLE ROUTE : Récupère un kiosk par son device_id matériel

    Permet au kiosk de se "restaurer" après effacement du cache
    """
    service = FridgeService(db)

    fridge = db.query(Fridge).filter(Fridge.device_id == device_id).first()

    if not fridge:
        raise HTTPException(status_code=404, detail="Device not found")

    return {
        "kiosk_id": fridge.kiosk_id,
        "is_paired": fridge.is_paired,
        "fridge_id": fridge.id if fridge.is_paired else None,
        "fridge_name": fridge.name if fridge.is_paired else None,
        "pairing_code": fridge.pairing_code if not fridge.is_paired else None,
    }


@router.post("/kiosk/{kiosk_id}/heartbeat")
def kiosk_heartbeat(
    kiosk_id: str,
    db: Session = Depends(get_db),
):
    """
    Heartbeat du kiosk (appelé toutes les 30s).
    Maintient la connexion active.
    """
    service = FridgeService(db)
    service.update_heartbeat(kiosk_id)

    return {
        "status": "active",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/kiosk/{kiosk_id}/status", response_model=KioskStatusResponse)
def get_kiosk_status(
    kiosk_id: str,
    db: Session = Depends(get_db),
):
    """
    Vérifie si le kiosk a été pairé.
    Le kiosk poll cette route toutes les 5s après génération du code.
    """
    service = FridgeService(db)
    status = service.get_fridge_status(kiosk_id)

    if not status:
        raise HTTPException(status_code=404, detail="Kiosk not found")

    return status


@router.post("/pair", response_model=PairingResponse)
def pair_fridge(
    request: PairingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lie un frigo existant à l'utilisateur connecté.

    Flow :
    1. User ouvre l'app mobile
    2. User scanne le QR code OU entre le code 6 chiffres
    3. Cette API lie le frigo à l'utilisateur

    Args:
        pairing_code : Code 6 chiffres affiché sur le kiosk
        fridge_name : Nom personnalisé (défaut "Mon Frigo")
        fridge_location : Localisation (optionnel)

    Returns:
        - fridge_id : ID du frigo
        - kiosk_id : UUID du kiosk
        - access_token : Token pour accéder au frigo
    """
    service = FridgeService(db)

    result = service.pair_fridge(
        pairing_code=request.pairing_code,
        user_id=current_user.id,
        fridge_name=request.fridge_name or "Mon Frigo",
        fridge_location=request.fridge_location,
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Code invalide, expiré ou frigo déjà pairé",
        )

    return result


@router.get("", response_model=List[FridgeResponse])
def list_fridges(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Liste tous les frigos de l'utilisateur
    """
    service = FridgeService(db)
    fridges = service.get_user_fridges(current_user.id)

    return fridges


@router.get("/{fridge_id}", response_model=FridgeResponse)
def get_fridge(
    fridge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Récupère un frigo spécifique
    """
    service = FridgeService(db)
    fridge = service.get_fridge_by_id(fridge_id, current_user.id)

    if not fridge:
        raise HTTPException(status_code=404, detail="Frigo non trouvé")

    return fridge


@router.put("/{fridge_id}", response_model=FridgeResponse)
def update_fridge(
    fridge_id: int,
    request: FridgeUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Modifie le nom/localisation du frigo après pairing.
    """
    service = FridgeService(db)

    fridge = service.update_fridge(
        fridge_id=fridge_id,
        user_id=current_user.id,
        name=request.name,
        location=request.location,
        config=request.config,
    )

    if not fridge:
        raise HTTPException(status_code=404, detail="Frigo non trouvé")

    return fridge


@router.delete("/{fridge_id}", status_code=204)
def unpair_fridge(
    fridge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Délie un frigo (reset à unpaired).
    Supprime également tout l'inventaire !
    """
    service = FridgeService(db)
    success = service.unpair_fridge(fridge_id, current_user.id)

    if not success:
        raise HTTPException(status_code=404, detail="Frigo non trouvé")

    return None


@router.get("/{fridge_id}/statistics")
def get_fridge_statistics(
    fridge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Statistiques détaillées du frigo
    """
    service = FridgeService(db)

    fridge = service.get_fridge_by_id(fridge_id, current_user.id)
    if not fridge:
        raise HTTPException(status_code=404, detail="Frigo non trouvé")

    stats = service.get_fridge_statistics(fridge_id)
    return stats


@router.get("/{fridge_id}/summary")
def get_fridge_summary(
    fridge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Résumé rapide du frigo
    """
    service = FridgeService(db)

    fridge = service.get_fridge_by_id(fridge_id, current_user.id)
    if not fridge:
        raise HTTPException(status_code=404, detail="Frigo non trouvé")

    summary = service.get_fridge_summary(fridge_id)
    return summary
