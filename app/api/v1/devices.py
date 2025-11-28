from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from app.core.database import get_db
from app.core.dependencies import get_user_fridge, get_current_user
from app.models.fridge import Fridge
from app.models.user import User
from app.services.device_service import DeviceService
from app.schemas.device import (
    PairingCodeResponse,
    PairingRequest,
    PairingResponse,
    DeviceResponse,
)

router = APIRouter(prefix="/fridges/{fridge_id}/devices", tags=["Device Pairing"])


@router.post("/generate-code", response_model=PairingCodeResponse)
def generate_pairing_code(
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
    device_type: str = "kiosk",
):
    """
    Génère un code de jumelage

    Utilisation :
    1. L'utilisateur lance cette requête depuis le Smartphone configuré comme frigo
    2. Un code à 6 chiffres s'affiche sur l'écran du Smartphone
    3. L'utilisateur peut maintenant jumeler son téléphone avec ce code
    """
    device_service = DeviceService(db)
    pairing_code = device_service.generate_pairing_code(fridge.id, device_type)

    return {
        "pairing_code": pairing_code,
        "fridge_id": fridge.id,
        "expires_in_minutes": 5,
        "instructions": (
            f"Entrez le code {pairing_code} sur votre téléphone pour vous connecter "
            "à ce réfrigérateur."
        ),
    }


@router.post("/pair", response_model=PairingResponse)
def pair_mobile_device(request: PairingRequest, db: Session = Depends(get_db)):
    """
    Jumelle un téléphone mobile avec le code de jumelage

    Utilisation :
    1. L'utilisateur ouvre l'app mobile
    2. Il entre le code à 6 chiffres affiché sur le Smartphone configuré comme frigo
    3. Le téléphone se connecte au frigo
    """
    device_service = DeviceService(db)

    result = device_service.pair_device(
        pairing_code=request.pairing_code,
        device_type=request.device_type,
        device_name=request.device_name,
    )

    if not result:
        raise HTTPException(
            status_code=404, detail="Code de jumelage invalide ou expiré"
        )

    return result


@router.get("", response_model=List[DeviceResponse])
def list_paired_devices(
    fridge: Fridge = Depends(get_user_fridge), db: Session = Depends(get_db)
):
    """Liste tous les appareils connectés à ce frigo"""
    device_service = DeviceService(db)
    devices = device_service.list_paired_devices(fridge.id)

    return devices


@router.delete("/{device_id}", status_code=204)
def unpair_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Déconnecter un appareil du frigo"""
    device_service = DeviceService(db)

    success = device_service.unpair_device(device_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=404, detail="Appareil non trouvé ou accès refusé"
        )

    return None


@router.post("/heartbeat")
def device_heartbeat(
    fridge: Fridge = Depends(get_user_fridge),
    device_id: str = None,
    db: Session = Depends(get_db),
):
    """
    Ping périodique pour maintenir la connexion active

    Les appareils envoient ce ping toutes les 30 secondes
    pour montrer qu'ils sont toujours connectés.
    """
    if device_id:
        device_service = DeviceService(db)
        device_service.update_device_activity(device_id)

    return {
        "status": "active",
        "fridge_id": fridge.id,
        "timestamp": datetime.utcnow().isoformat(),
    }
