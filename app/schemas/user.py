from pydantic import BaseModel, EmailStr, Field, validator
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
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    preferred_cuisine: Optional[str] = Field(None, max_length=50)
    dietary_restrictions: Optional[List[str]] = None
    timezone: Optional[str] = Field(None, max_length=50)
    prefs: Optional[Dict[str, Any]] = None

    @validator("name")
    def validate_name(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError("Le nom ne peut pas être vide")
        return v.strip() if v else v

    @validator("timezone")
    def validate_timezone(cls, v):
        if v:
            import pytz

            try:
                pytz.timezone(v)
            except pytz.exceptions.UnknownTimeZoneError:
                raise ValueError(f"Timezone invalide: {v}")
        return v

    @validator("dietary_restrictions", each_item=True)
    def validate_dietary_restrictions(cls, v):
        if not v or not v.strip():
            raise ValueError("Les restrictions alimentaires ne peuvent pas être vides")
        return v.lower().strip()
