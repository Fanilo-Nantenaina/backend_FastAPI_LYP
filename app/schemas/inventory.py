from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Dict, Any, List
from datetime import datetime, date


class InventoryItemCreate(BaseModel):
    product_id: Optional[int] = Field(
        None, gt=0, description="ID du produit existant (optionnel)"
    )
    product_name: Optional[str] = Field(
        None, min_length=1, max_length=200, description="Nom du nouveau produit"
    )
    category: Optional[str] = Field(
        None, max_length=100, description="Catégorie du produit"
    )
    quantity: float = Field(..., gt=0, description="Quantité (doit être > 0)")
    unit: Optional[str] = Field(None, min_length=1, max_length=20)
    expiry_date: Optional[date] = None

    @field_validator("expiry_date")
    @classmethod
    def validate_expiry_date(cls, v):
        if v and v < date.today():
            raise ValueError("La date de péremption ne peut pas être dans le passé")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError("La quantité doit être positive (RG9)")
        if v > 10000:
            raise ValueError("La quantité semble trop élevée")
        return v

    @model_validator(mode="after")
    def validate_product_source(self):
        if not self.product_id and not self.product_name:
            raise ValueError("Vous devez fournir soit product_id, soit product_name")
        return self


class InventoryItemUpdate(BaseModel):
    quantity: Optional[float] = Field(None, ge=0)
    expiry_date: Optional[date] = None
    open_date: Optional[date] = None

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v):
        if v is not None and v < 0:
            raise ValueError("La quantité ne peut pas être négative (RG9)")
        return v

    @model_validator(mode="after")
    def validate_dates(self):
        if self.open_date and self.open_date > date.today():
            raise ValueError("La date d'ouverture ne peut pas être dans le futur")

        if self.expiry_date and self.open_date and self.expiry_date < self.open_date:
            raise ValueError(
                "La date de péremption ne peut pas être avant la date d'ouverture"
            )

        return self


class ConsumeItemRequest(BaseModel):
    quantity_consumed: float = Field(..., gt=0, description="Quantité consommée")

    @field_validator("quantity_consumed")
    @classmethod
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

    product_name: Optional[str] = None
    product_category: Optional[str] = None

    class Config:
        from_attributes = True


class ConsumeBatchItem(BaseModel):
    inventory_item_id: int
    quantity_consumed: float
    detected_product_name: str


class ConsumeBatchRequest(BaseModel):
    items: List[ConsumeBatchItem]


class ConsumeBatchResponse(BaseModel):
    success_count: int
    failed_count: int
    results: List[Dict[str, Any]]


class SearchRequest(BaseModel):
    query: str


class SearchHistoryResponse(BaseModel):
    id: str
    query: str
    response: str
    timestamp: str

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    query: str
    response: str
    timestamp: str
    inventory_count: int
