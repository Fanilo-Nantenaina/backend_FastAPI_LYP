from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class ShoppingListItemCreate(BaseModel):
    product_id: int
    quantity: float
    unit: str


class ShoppingListCreate(BaseModel):
    fridge_id: int
    items: List[ShoppingListItemCreate]


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
