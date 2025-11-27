from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AlertResponse(BaseModel):
    id: int
    fridge_id: int
    inventory_item_id: Optional[int]
    type: str
    message: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class AlertUpdateRequest(BaseModel):
    status: Optional[str] = None
