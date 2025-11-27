from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: Optional[str]
    timezone: str
    prefs: Optional[Dict[str, Any]]
    preferred_cuisine: Optional[str]
    dietary_restrictions: Optional[List[str]]

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    preferred_cuisine: Optional[str] = None
    dietary_restrictions: Optional[List[str]] = None
    timezone: Optional[str] = None
    prefs: Optional[Dict[str, Any]] = None
