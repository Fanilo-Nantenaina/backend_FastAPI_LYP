from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime


class ShoppingListItemCreate(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: float = Field(..., gt=0)
    unit: str = Field(..., min_length=1, max_length=20)


class ShoppingListCreate(BaseModel):
    fridge_id: int = Field(..., gt=0)
    items: List[ShoppingListItemCreate] = Field(..., min_length=1)

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


class GenerateFromIngredientsRequest(BaseModel):
    """
    🆕 Requête pour générer une liste de courses depuis des ingrédients bruts

    Utilisé principalement pour créer une liste depuis les ingrédients
    manquants suggérés par l'IA pour une recette.
    """

    fridge_id: int = Field(..., gt=0)
    ingredients: List[Dict[str, Any]] = Field(..., min_length=1)

    class Config:
        json_schema_extra = {
            "example": {
                "fridge_id": 1,
                "ingredients": [
                    {"name": "Oignon", "quantity": 2, "unit": "pièces"},
                    {"name": "Crème fraîche", "quantity": 200, "unit": "ml"},
                    {"name": "Parmesan", "quantity": 50, "unit": "g"},
                ],
            }
        }

    @validator("ingredients")
    def validate_ingredients(cls, v):
        """Vérifier que chaque ingrédient a au moins un nom"""
        for ing in v:
            if not ing.get("name") or not str(ing.get("name")).strip():
                raise ValueError("Chaque ingrédient doit avoir un nom")
        return v


class ShoppingListItemResponse(BaseModel):
    id: int
    shopping_list_id: int
    product_id: int
    quantity: Optional[float]
    unit: Optional[str]
    status: str
    product_name: Optional[str] = None 

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
