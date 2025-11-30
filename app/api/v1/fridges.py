# ==================================================
# api/v1/fridges.py - VERSION REFACTORISÉE COMPLÈTE
# ==================================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

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


# ========================================
# ROUTES KIOSK (appelées par le frigo Samsung)
# ========================================


@router.post("/kiosk/init", response_model=KioskInitResponse)
def init_kiosk(
    device_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    🔵 KIOSK ROUTE

    Initialise un nouveau frigo (kiosk physique).
    Appelé au démarrage du kiosk Samsung.

    Returns:
        - kiosk_id : UUID du kiosk (à stocker localement)
        - pairing_code : Code 6 chiffres à afficher
        - expires_in_minutes : Durée de validité du code
    """
    service = FridgeService(db)
    result = service.init_kiosk(device_name=device_name)

    return result


@router.post("/kiosk/{kiosk_id}/heartbeat")
def kiosk_heartbeat(
    kiosk_id: str,
    db: Session = Depends(get_db),
):
    """
    🔵 KIOSK ROUTE

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
    🔵 KIOSK ROUTE

    Vérifie si le kiosk a été pairé.
    Le kiosk poll cette route toutes les 5s après génération du code.
    """
    service = FridgeService(db)
    status = service.get_fridge_status(kiosk_id)

    if not status:
        raise HTTPException(status_code=404, detail="Kiosk not found")

    return status


# ========================================
# ROUTES CLIENT (appelées par l'app mobile)
# ========================================


@router.post("/pair", response_model=PairingResponse)
def pair_fridge(
    request: PairingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    📱 CLIENT ROUTE

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
    📱 CLIENT ROUTE

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
    📱 CLIENT ROUTE

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
    📱 CLIENT ROUTE

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
    📱 CLIENT ROUTE

    Délie un frigo (reset à unpaired).
    ⚠️ Supprime également tout l'inventaire !
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
    📱 CLIENT ROUTE

    Statistiques détaillées du frigo
    """
    service = FridgeService(db)

    # Vérifier la propriété
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
    📱 CLIENT ROUTE

    Résumé rapide du frigo
    """
    service = FridgeService(db)

    # Vérifier la propriété
    fridge = service.get_fridge_by_id(fridge_id, current_user.id)
    if not fridge:
        raise HTTPException(status_code=404, detail="Frigo non trouvé")

    summary = service.get_fridge_summary(fridge_id)
    return summary
