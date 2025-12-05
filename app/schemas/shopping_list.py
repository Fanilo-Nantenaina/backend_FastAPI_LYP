from pydantic import BaseModel, Field, validator, model_validator
from typing import List, Optional, Dict, Any
from datetime import datetime


class ShoppingListItemCreate(BaseModel):
    """
    Schéma pour créer un item de liste de courses
    Accepte SOIT product_id (produit existant), SOIT product_name (nouveau produit)
    """

    product_id: Optional[int] = Field(None, gt=0)
    product_name: Optional[str] = Field(None, min_length=1, max_length=200)
    quantity: float = Field(..., gt=0)
    unit: str = Field(..., min_length=1, max_length=20)

    @model_validator(mode="before")
    def validate_product_source(cls, values):
        """Vérifie qu'on a soit product_id, soit product_name"""
        product_id = values.get("product_id")
        product_name = values.get("product_name")

        if not product_id and not product_name:
            raise ValueError("Vous devez fournir soit product_id, soit product_name")

        return values


class ShoppingListCreate(BaseModel):
    fridge_id: int = Field(..., gt=0)
    items: List[ShoppingListItemCreate] = Field(..., min_length=1)
    name: Optional[str] = None

    @validator("items")
    def validate_items(cls, v):
        """Vérifier qu'il n'y a pas de doublons (product_id OU product_name)"""
        if not v:
            return v

        seen = set()
        for item in v:
            if item.product_id is not None:
                key = ("id", item.product_id)
            elif item.product_name is not None:
                key = ("name", item.product_name.strip().lower())
            else:
                continue

            if key in seen:
                raise ValueError("La liste contient des produits en double")
            seen.add(key)

        return v


class GenerateShoppingListRequest(BaseModel):
    fridge_id: int
    recipe_ids: Optional[List[int]] = None


class GenerateFromIngredientsRequest(BaseModel):
    """
    🆕 Requête pour générer une liste de courses depuis des ingrédients bruts
    ✅ AJOUT : recipe_id optionnel pour lier à une recette
    """

    fridge_id: int = Field(..., gt=0)
    ingredients: List[Dict[str, Any]] = Field(..., min_length=1)
    recipe_id: Optional[int] = None  # ✅ NOUVEAU

    class Config:
        json_schema_extra = {
            "example": {
                "fridge_id": 1,
                "recipe_id": 42,  # ✅ Optionnel
                "ingredients": [
                    {"name": "Oignon", "quantity": 2, "unit": "pièces"},
                    {"name": "Crème fraîche", "quantity": 200, "unit": "ml"},
                    {"name": "Parmesan", "quantity": 50, "unit": "g"},
                ],
            }
        }

    @validator("ingredients")
    def validate_ingredients(cls, v):
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
    name: str
    created_at: datetime
    generated_by: Optional[str]
    items: List[ShoppingListItemResponse] = []

    class Config:
        from_attributes = True
