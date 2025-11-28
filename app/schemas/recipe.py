from pydantic import BaseModel, Field, validator, model_validator
from typing import List, Optional, Dict, Any


class RecipeIngredientCreate(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: float = Field(..., gt=0)
    unit: str = Field(..., min_length=1, max_length=20)


class RecipeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    steps: Optional[str] = Field(None, max_length=5000)
    preparation_time: Optional[int] = Field(None, ge=0, le=1440)  # Max 24h
    difficulty: Optional[str] = Field(None, pattern="^(easy|medium|hard)$")  # <--- ici
    extra_data: Optional[Dict[str, Any]] = None
    ingredients: List[RecipeIngredientCreate] = Field(..., min_items=1)

    @validator("title")
    def validate_title(cls, v):
        if not v or not v.strip():
            raise ValueError("Le titre ne peut pas être vide")
        return v.strip()

    @validator("ingredients")
    def validate_ingredients(cls, v):
        """Vérifier qu'il n'y a pas de doublons"""
        product_ids = [ing.product_id for ing in v]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("La recette contient des ingrédients en double")
        return v


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
    extra_data: Optional[Dict[str, Any]]
    ingredients: List[RecipeIngredientResponse] = []

    class Config:
        from_attributes = True


class FeasibleRecipeResponse(BaseModel):
    recipe: RecipeResponse
    can_make: bool
    missing_ingredients: List[Dict[str, Any]]
    match_percentage: float
