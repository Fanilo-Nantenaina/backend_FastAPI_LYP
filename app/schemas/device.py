from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PairingCodeResponse(BaseModel):
    pairing_code: str
    fridge_id: int
    expires_in_minutes: int
    instructions: str


class PairingRequest(BaseModel):
    pairing_code: str
    device_type: str  # 'mobile', 'tablet', 'web', 'kiosk'
    device_name: Optional[str] = None  # Complète la ligne


class PairingResponse(BaseModel):
    """Schéma de la réponse après jumelage réussi"""

    fridge_id: int
    device_id: str
    device_name: Optional[str]
    access_token: str


class DeviceResponse(BaseModel):
    """Schéma représentant un appareil jumelé (pour la liste GET /devices)"""

    id: int
    fridge_id: int
    device_id: str
    device_type: str
    device_name: Optional[str]
    is_paired: bool
    last_active_at: Optional[datetime]
    created_at: datetime

    class Config:
        # Permet à Pydantic d'utiliser les attributs ORM (device.id, device.fridge_id, etc.)
        from_attributes = True
