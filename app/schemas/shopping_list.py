from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime


class ShoppingListItemCreate(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: float = Field(..., gt=0)
    unit: str = Field(..., min_length=1, max_length=20)


class ShoppingListCreate(BaseModel):
    fridge_id: int = Field(..., gt=0)
    items: List[ShoppingListItemCreate] = Field(..., min_items=1)

    @validator("items")
    def validate_items(cls, v):
        """Vérifier qu'il n'y a pas de doublons"""
        product_ids = [item.product_id for item in v]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("La liste contient des produits en double")
        return v


class GenerateShoppingListRequest(BaseModel):
    fridge_id: int
    recipe_ids: Optional[List[int]] = None


class ShoppingListItemResponse(BaseModel):
    id: int
    shopping_list_id: int
    product_id: int
    quantity: Optional[float]
    unit: Optional[str]
    status: str

    class Config:
        from_attributes = True


class ShoppingListResponse(BaseModel):
    id: int
    user_id: int
    fridge_id: int
    created_at: datetime
    generated_by: Optional[str]
    items: List[ShoppingListItemResponse] = []

    class Config:
        from_attributes = True
