from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime


class FridgeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    config: Optional[Dict[str, Any]] = None

    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Le nom du frigo ne peut pas être vide")
        return v.strip()


class FridgeUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class FridgeResponse(BaseModel):
    id: int
    user_id: Optional[int]
    name: str
    location: Optional[str]
    kiosk_id: str
    is_paired: bool
    config: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


# ========================================
# SCHÉMAS KIOSK
# ========================================


class KioskInitResponse(BaseModel):
    """Réponse après initialisation du kiosk"""

    kiosk_id: str
    pairing_code: str
    expires_in_minutes: int


class KioskStatusResponse(BaseModel):
    """Statut d'un kiosk"""

    kiosk_id: str
    is_paired: bool
    fridge_id: Optional[int]
    fridge_name: Optional[str]
    last_heartbeat: Optional[str]
    paired_at: Optional[str]


# ========================================
# SCHÉMAS CLIENT
# ========================================


class PairingRequest(BaseModel):
    """Requête de pairing depuis le client mobile"""

    pairing_code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        description="Code 6 chiffres affiché sur le kiosk",
    )
    fridge_name: Optional[str] = Field(None, description="Nom personnalisé du frigo")
    fridge_location: Optional[str] = Field(
        None, description="Localisation (cuisine, garage, etc.)"
    )


class PairingResponse(BaseModel):
    """Réponse après pairing réussi"""

    fridge_id: int
    fridge_name: str
    fridge_location: Optional[str]
    kiosk_id: str
    access_token: str


class UpdateFridgeInfoRequest(BaseModel):
    """Modification du nom/localisation après pairing"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
