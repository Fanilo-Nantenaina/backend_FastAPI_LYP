from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime


class EventResponse(BaseModel):
    id: int
    fridge_id: int
    inventory_item_id: Optional[int]
    type: str
    payload: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True
