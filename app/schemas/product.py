from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any


class ProductCreate(BaseModel):
    barcode: Optional[str] = Field(None, min_length=8, max_length=20)
    name: str = Field(..., min_length=1, max_length=200)
    category: Optional[str] = Field(None, max_length=100)
    shelf_life_days: Optional[int] = Field(None, ge=0, le=3650)
    default_unit: str = Field("piece", min_length=1, max_length=20)
    image_url: Optional[str] = Field(None, max_length=500)
    tags: Optional[List[str]] = None
    extra_data: Optional[Dict[str, Any]] = None

    @validator("barcode")
    def validate_barcode(cls, v):
        if v and not v.isdigit():
            raise ValueError("Le code-barres doit contenir uniquement des chiffres")
        return v

    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Le nom du produit ne peut pas être vide")
        return v.strip()

    @validator("tags", each_item=True)
    def validate_tags(cls, v):
        if not v or not v.strip():
            raise ValueError("Les tags ne peuvent pas être vides")
        if len(v) > 50:
            raise ValueError("Les tags ne peuvent pas dépasser 50 caractères")
        return v.lower().strip()


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    shelf_life_days: Optional[int] = None
    default_unit: Optional[str] = None
    image_url: Optional[str] = None
    tags: Optional[List[str]] = None
    extra_data: Optional[Dict[str, Any]] = None


class ProductResponse(BaseModel):
    id: int
    barcode: Optional[str]
    name: str
    category: Optional[str]
    shelf_life_days: Optional[int]
    default_unit: str
    image_url: Optional[str]
    tags: Optional[List[str]]
    extra_data: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True
