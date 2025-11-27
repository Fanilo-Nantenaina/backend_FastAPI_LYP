from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class ProductCreate(BaseModel):
    barcode: Optional[str] = None
    name: str
    category: Optional[str] = None
    shelf_life_days: Optional[int] = None
    default_unit: str = "piece"
    image_url: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    shelf_life_days: Optional[int] = None
    default_unit: Optional[str] = None
    image_url: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class ProductResponse(BaseModel):
    id: int
    barcode: Optional[str]
    name: str
    category: Optional[str]
    shelf_life_days: Optional[int]
    default_unit: str
    image_url: Optional[str]
    tags: Optional[List[str]]
    metadata: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True
