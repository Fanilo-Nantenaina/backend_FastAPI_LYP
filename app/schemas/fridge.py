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

    @validator("config")
    def validate_config(cls, v):
        """Valider les valeurs de configuration"""
        if v:
            # Valider expiry_warning_days
            if "expiry_warning_days" in v:
                days = v["expiry_warning_days"]
                if not isinstance(days, int) or days < 0 or days > 30:
                    raise ValueError("expiry_warning_days doit être entre 0 et 30")

            # Valider lost_item_threshold_hours
            if "lost_item_threshold_hours" in v:
                hours = v["lost_item_threshold_hours"]
                if not isinstance(hours, (int, float)) or hours < 0 or hours > 720:
                    raise ValueError(
                        "lost_item_threshold_hours doit être entre 0 et 720 (30 jours)"
                    )

            # Valider low_stock_threshold
            if "low_stock_threshold" in v:
                threshold = v["low_stock_threshold"]
                if not isinstance(threshold, (int, float)) or threshold < 0:
                    raise ValueError("low_stock_threshold doit être positif")

        return v


class FridgeUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class FridgeResponse(BaseModel):
    id: int
    user_id: int
    name: str
    location: Optional[str]
    config: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True
