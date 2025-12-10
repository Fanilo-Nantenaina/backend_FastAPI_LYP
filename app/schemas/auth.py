from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str
    password: str = Field(..., min_length=8, max_length=72)
    timezone: Optional[str] = "UTC"
    dietary_restrictions: Optional[List[str]] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
