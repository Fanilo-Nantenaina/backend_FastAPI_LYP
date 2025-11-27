from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_user_fridge
from app.models.user import User
from app.models.fridge import Fridge
from app.models.recipe import Recipe, RecipeFavorite
from app.schemas.recipe import RecipeResponse, RecipeCreate, FeasibleRecipeResponse
from app.services.recipe_service import RecipeService

router = APIRouter(prefix="/recipes", tags=["Recipes"])


@router.get("", response_model=List[RecipeResponse])
async def list_recipes(
    db: Session = Depends(get_db),
    difficulty: str = None,
    cuisine: str = None,
    limit: int = 50,
):
    """Liste toutes les recettes disponibles"""
    query = db.query(Recipe)

    if difficulty:
        query = query.filter(Recipe.difficulty == difficulty)

    if cuisine:
        query = query.filter(Recipe.metadata["cuisine"].astext == cuisine)

    return query.limit(limit).all()


@router.post("", response_model=RecipeResponse, status_code=201)
async def create_recipe(
    request: RecipeCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Créer une nouvelle recette"""
    recipe_service = RecipeService(db)
    recipe = recipe_service.create_recipe(request)
    return recipe


@router.get("/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(recipe_id: int, db: Session = Depends(get_db)):
    """Récupérer une recette spécifique"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.post("/{recipe_id}/favorite", status_code=201)
async def add_to_favorites(
    recipe_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """CU6: Marquer une recette comme favorite (RG16)"""
    # Vérifier que la recette existe
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # RG16: Vérifier que le favori n'existe pas déjà
    existing = (
        db.query(RecipeFavorite)
        .filter(
            RecipeFavorite.user_id == current_user.id,
            RecipeFavorite.recipe_id == recipe_id,
        )
        .first()
    )

    if existing:
        raise HTTPException(status_code=400, detail="Recipe already in favorites")

    # Ajouter aux favoris
    favorite = RecipeFavorite(user_id=current_user.id, recipe_id=recipe_id)
    db.add(favorite)
    db.commit()

    return {"message": "Recipe added to favorites"}


@router.delete("/{recipe_id}/favorite", status_code=204)
async def remove_from_favorites(
    recipe_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retirer une recette des favoris"""
    favorite = (
        db.query(RecipeFavorite)
        .filter(
            RecipeFavorite.user_id == current_user.id,
            RecipeFavorite.recipe_id == recipe_id,
        )
        .first()
    )

    if not favorite:
        raise HTTPException(status_code=404, detail="Favorite not found")

    db.delete(favorite)
    db.commit()
    return None


@router.get("/favorites/mine", response_model=List[RecipeResponse])
async def list_my_favorites(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """CU6: Consulter les recettes favorites"""
    favorites = (
        db.query(Recipe)
        .join(RecipeFavorite)
        .filter(RecipeFavorite.user_id == current_user.id)
        .all()
    )

    return favorites


# Route spéciale pour les recettes faisables avec l'inventaire actuel
@router.get(
    "/fridges/{fridge_id}/feasible", response_model=List[FeasibleRecipeResponse]
)
async def list_feasible_recipes(
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    CU6: Consulter les recettes faisables avec l'inventaire actuel
    RG14: Exclut les recettes avec des restrictions alimentaires
    """
    recipe_service = RecipeService(db)

    feasible_recipes = recipe_service.find_feasible_recipes(
        fridge_id=fridge.id, user=current_user
    )

    return feasible_recipes
