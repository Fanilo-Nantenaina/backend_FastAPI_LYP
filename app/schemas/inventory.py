from pydantic import BaseModel, Field, validator, model_validator
from typing import Optional, Dict, Any
from datetime import datetime, date


class InventoryItemCreate(BaseModel):
    product_id: int = Field(..., gt=0, description="ID du produit")
    quantity: float = Field(..., gt=0, description="Quantité (doit être > 0)")
    unit: Optional[str] = Field(None, min_length=1, max_length=20)
    expiry_date: Optional[date] = None

    @validator("expiry_date")
    def validate_expiry_date(cls, v):
        if v and v < date.today():
            raise ValueError("La date de péremption ne peut pas être dans le passé")
        return v

    @validator("quantity")
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError("La quantité doit être positive (RG9)")
        if v > 10000:
            raise ValueError("La quantité semble trop élevée")
        return v


class InventoryItemUpdate(BaseModel):
    quantity: Optional[float] = Field(None, ge=0)
    expiry_date: Optional[date] = None
    open_date: Optional[date] = None

    @validator("quantity")
    def validate_quantity(cls, v):
        if v is not None and v < 0:
            raise ValueError("La quantité ne peut pas être négative (RG9)")
        return v

    @model_validator(mode="after")
    def validate_dates(cls, values):
        """Vérifier la cohérence des dates après validation des champs"""
        expiry_date = values.get("expiry_date")
        open_date = values.get("open_date")

        if open_date and open_date > date.today():
            raise ValueError("La date d'ouverture ne peut pas être dans le futur")

        if expiry_date and open_date and expiry_date < open_date:
            raise ValueError(
                "La date de péremption ne peut pas être avant la date d'ouverture"
            )

        return values


class ConsumeItemRequest(BaseModel):
    quantity_consumed: float = Field(..., gt=0, description="Quantité consommée")

    @validator("quantity_consumed")
    def validate_quantity_consumed(cls, v):
        if v <= 0:
            raise ValueError("La quantité consommée doit être positive")
        if v > 10000:
            raise ValueError("La quantité consommée semble trop élevée")
        return v


class InventoryItemResponse(BaseModel):
    id: int
    fridge_id: int
    product_id: int
    quantity: float
    initial_quantity: Optional[float]
    unit: str
    added_at: datetime
    open_date: Optional[date]
    expiry_date: Optional[date]
    source: Optional[str]
    last_seen_at: datetime
    extra_data: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True
