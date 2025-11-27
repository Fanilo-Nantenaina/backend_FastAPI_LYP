from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, date


class InventoryItemCreate(BaseModel):
    product_id: int
    quantity: float
    unit: Optional[str] = None
    expiry_date: Optional[date] = None


class InventoryItemUpdate(BaseModel):
    quantity: Optional[float] = None
    expiry_date: Optional[date] = None
    open_date: Optional[date] = None


class ConsumeItemRequest(BaseModel):
    quantity_consumed: float


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
    metadata: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True
