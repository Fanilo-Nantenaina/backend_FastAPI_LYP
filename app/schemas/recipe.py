from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class RecipeIngredientCreate(BaseModel):
    product_id: int
    quantity: float
    unit: str


class RecipeCreate(BaseModel):
    title: str
    description: Optional[str] = None
    steps: Optional[str] = None
    preparation_time: Optional[int] = None
    difficulty: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    ingredients: List[RecipeIngredientCreate]


class RecipeIngredientResponse(BaseModel):
    id: int
    recipe_id: int
    product_id: int
    quantity: Optional[float]
    unit: Optional[str]

    class Config:
        from_attributes = True


class RecipeResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    steps: Optional[str]
    preparation_time: Optional[int]
    difficulty: Optional[str]
    metadata: Optional[Dict[str, Any]]
    ingredients: List[RecipeIngredientResponse] = []

    class Config:
        from_attributes = True


class FeasibleRecipeResponse(BaseModel):
    recipe: RecipeResponse
    can_make: bool
    missing_ingredients: List[Dict[str, Any]]
    match_percentage: float
