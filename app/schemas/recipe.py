from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any


class RecipeIngredientCreate(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: float = Field(..., gt=0)
    unit: str = Field(..., min_length=1, max_length=20)


class RecipeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    steps: Optional[str] = Field(None, max_length=5000)
    preparation_time: Optional[int] = Field(None, ge=0, le=1440)
    difficulty: Optional[str] = Field(None, pattern="^(easy|medium|hard)$")
    extra_data: Optional[Dict[str, Any]] = None
    ingredients: List[RecipeIngredientCreate] = Field(..., min_length=1)

    fridge_id: Optional[int] = None

    @validator("title")
    def validate_title(cls, v):
        if not v or not v.strip():
            raise ValueError("Le titre ne peut pas être vide")
        return v.strip()

    @validator("ingredients")
    def validate_ingredients(cls, v):
        product_ids = [ing.product_id for ing in v]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("La recette contient des ingrédients en double")
        return v


class AddToFavoritesRequest(BaseModel):
    fridge_id: int = Field(..., gt=0, description="ID du frigo associé")


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
    fridge_id: Optional[int] = None  # AJOUT
    ingredients: List[RecipeIngredientResponse] = []

    class Config:
        from_attributes = True


class FeasibleRecipeResponse(BaseModel):
    """Réponse pour une recette avec infos de faisabilité"""

    recipe: RecipeResponse
    can_make: bool
    missing_ingredients: List[Dict[str, Any]]
    match_percentage: float
    shopping_list_id: Optional[int] = None
    shopping_list_status: Optional[str] = None
    ingredients_complete: bool = False
    combined_percentage: float = 0.0
    purchased_missing_count: int = 0
    total_missing_count: int = 0

    class Config:
        from_attributes = True


class SuggestedIngredient(BaseModel):
    """Ingrédient suggéré par l'IA"""

    name: str
    quantity: float
    unit: str
    is_available: Optional[bool] = None


class MissingIngredient(BaseModel):
    """Ingrédient manquant pour une recette"""

    name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None


class SuggestedIngredient(BaseModel):
    """Ingrédient suggéré par l'IA avec mapping vers l'inventaire"""

    name: str
    quantity: float = 1
    unit: str = ""
    is_available: bool = False
    matched_inventory_id: Optional[int] = None  # ✅ NOUVEAU
    matched_inventory_name: Optional[str] = None  # ✅ NOUVEAU


class MissingIngredient(BaseModel):
    """Ingrédient manquant"""

    name: str
    quantity: float = 1
    unit: str = ""


class SuggestedRecipeResponse(BaseModel):
    """Réponse de suggestion de recette par l'IA"""

    title: str
    description: str
    ingredients: List[SuggestedIngredient]
    steps: str
    preparation_time: int
    difficulty: str
    available_ingredients: List[str] = []
    missing_ingredients: List[MissingIngredient]=[]
    match_percentage: float
    fridge_id: Optional[int] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "title": "Omelette aux légumes",
                "description": "Une délicieuse omelette garnie de légumes frais",
                "ingredients": [
                    {
                        "name": "Œufs",
                        "quantity": 3,
                        "unit": "pièces",
                        "is_available": True,
                    },
                ],
                "steps": "1. Battre les œufs...",
                "preparation_time": 15,
                "difficulty": "easy",
                "available_ingredients": ["Œufs", "Tomates"],
                "missing_ingredients": [
                    {"name": "Oignon", "quantity": 1, "unit": "pièce"}
                ],
                "match_percentage": 66.7,
                "fridge_id": 1,
            }
        }
