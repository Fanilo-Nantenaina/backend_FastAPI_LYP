from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class FridgeCreate(BaseModel):
    name: str
    location: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


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
