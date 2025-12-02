from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_user_fridge
from app.models.user import User
from app.models.fridge import Fridge
from app.models.recipe import Recipe, RecipeFavorite, RecipeIngredient
from app.models.product import Product

from app.schemas.recipe import (
    RecipeResponse,
    RecipeCreate,
    FeasibleRecipeResponse,
    SuggestedRecipeResponse,
)
from app.services.recipe_service import RecipeService

router = APIRouter(prefix="/recipes", tags=["Recipes"])
logger = logging.getLogger(__name__)


@router.get("", response_model=List[RecipeResponse])
def list_recipes(
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
        query = query.filter(Recipe.extra_data["cuisine"].astext == cuisine)
    return query.limit(limit).all()


@router.post("", response_model=RecipeResponse, status_code=201)
def create_recipe(
    request: RecipeCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Créer une nouvelle recette"""
    recipe_service = RecipeService(db)
    recipe = recipe_service.create_recipe(request)
    return recipe


@router.get("/{recipe_id}", response_model=RecipeResponse)
def get_recipe(recipe_id: int, db: Session = Depends(get_db)):
    """Récupérer une recette spécifique"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.post("/{recipe_id}/favorite", status_code=201)
def add_to_favorites(
    recipe_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """CU6: Marquer une recette comme favorite (RG16)"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

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

    favorite = RecipeFavorite(user_id=current_user.id, recipe_id=recipe_id)
    db.add(favorite)
    db.commit()
    return {"message": "Recipe added to favorites"}


@router.delete("/{recipe_id}/favorite", status_code=204)
def remove_from_favorites(
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
def list_my_favorites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """CU6: Consulter les recettes favorites"""
    favorites = (
        db.query(Recipe)
        .join(RecipeFavorite)
        .filter(RecipeFavorite.user_id == current_user.id)
        .all()
    )
    return favorites


@router.get(
    "/fridges/{fridge_id}/feasible", response_model=List[FeasibleRecipeResponse]
)
def list_feasible_recipes(
    fridge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """CU6: Consulter les recettes faisables avec l'inventaire actuel"""
    from app.models.fridge import Fridge

    fridge = (
        db.query(Fridge)
        .filter(Fridge.id == fridge_id, Fridge.user_id == current_user.id)
        .first()
    )
    if not fridge:
        raise HTTPException(status_code=404, detail="Fridge not found or access denied")

    recipe_service = RecipeService(db)
    feasible_recipes = recipe_service.find_feasible_recipes(
        fridge_id=fridge_id, user=current_user
    )

    # ✅ DEBUG : Logger ce qui est retourné
    for item in feasible_recipes[:3]:  # Les 3 premiers
        logger.info(
            f"API Response: {item['recipe'].title} - "
            f"complete={item['ingredients_complete']}, "
            f"combined={item['combined_percentage']}%, "
            f"status={item['shopping_list_status']}"
        )

    return feasible_recipes


@router.post("/fridges/{fridge_id}/suggest", response_model=SuggestedRecipeResponse)
async def suggest_recipe_with_ai(
    fridge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    🆕 NOUVELLE ROUTE: Suggestion IA de recette basée sur l'inventaire

    Utilise Gemini pour suggérer une recette créative basée sur:
    - Les produits disponibles dans le frigo
    - Les préférences alimentaires de l'utilisateur
    - Les restrictions alimentaires

    Returns:
        SuggestedRecipeResponse avec la recette générée par l'IA
    """
    from app.models.fridge import Fridge

    fridge = (
        db.query(Fridge)
        .filter(Fridge.id == fridge_id, Fridge.user_id == current_user.id)
        .first()
    )
    if not fridge:
        raise HTTPException(status_code=404, detail="Fridge not found or access denied")

    recipe_service = RecipeService(db)

    try:
        suggested_recipe = await recipe_service.suggest_recipe_with_ai(
            fridge_id=fridge_id,
            user=current_user,
        )
        return suggested_recipe
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la génération de la recette: {str(e)}",
        )


@router.post("/save-suggested", response_model=RecipeResponse, status_code=201)
async def save_suggested_recipe(
    suggestion: SuggestedRecipeResponse,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    🆕 Sauvegarde une recette suggérée par l'IA dans la base de données

    Permet de transformer une suggestion temporaire en recette permanente
    accessible à tous les utilisateurs.
    """
    try:
        # Créer la recette de base
        recipe = Recipe(
            title=suggestion.title,
            description=suggestion.description,
            steps=suggestion.steps,
            preparation_time=suggestion.preparation_time,
            difficulty=suggestion.difficulty,
            extra_data={
                "created_from": "ai_suggestion",
                "created_by_user_id": current_user.id,
                "match_percentage": suggestion.match_percentage,
            },
        )
        db.add(recipe)
        db.flush()

        # Créer les ingrédients
        for ingredient_data in suggestion.ingredients:
            # Trouver ou créer le produit
            product = (
                db.query(Product)
                .filter(Product.name.ilike(ingredient_data["name"]))
                .first()
            )

            if not product:
                product = Product(
                    name=ingredient_data["name"].strip().capitalize(),
                    category="Divers",
                    default_unit=ingredient_data.get("unit", "pièce"),
                    shelf_life_days=7,
                )
                db.add(product)
                db.flush()

            # Créer l'ingrédient de recette
            recipe_ingredient = RecipeIngredient(
                recipe_id=recipe.id,
                product_id=product.id,
                quantity=ingredient_data.get("quantity", 1),
                unit=ingredient_data.get("unit", product.default_unit),
            )
            db.add(recipe_ingredient)

        db.commit()
        db.refresh(recipe)

        logger.info(f"✅ Saved AI-suggested recipe: {recipe.id} - {recipe.title}")

        return recipe

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save suggested recipe: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erreur lors de la sauvegarde: {str(e)}"
        )


@router.get("/debug/shopping-lists-recipes")
def debug_shopping_lists_recipes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    🔍 DEBUG : Voir les liens entre recettes et listes de courses
    """
    from app.models.shopping_list import ShoppingList
    from app.models.recipe import Recipe

    # Toutes les listes de courses de l'utilisateur
    shopping_lists = (
        db.query(ShoppingList).filter(ShoppingList.user_id == current_user.id).all()
    )

    # Toutes les recettes
    recipes = db.query(Recipe).all()

    lists_info = []
    for sl in shopping_lists:
        items_count = len(sl.items)
        purchased_count = sum(1 for item in sl.items if item.status == "purchased")

        lists_info.append(
            {
                "id": sl.id,
                "fridge_id": sl.fridge_id,
                "recipe_id": sl.recipe_id,  # ✅ C'est ça qu'on vérifie
                "recipe_name": sl.recipe.title if sl.recipe else None,
                "generated_by": sl.generated_by,
                "status": sl.status,
                "items_count": items_count,
                "purchased_count": purchased_count,
                "is_completed": purchased_count == items_count and items_count > 0,
                "created_at": sl.created_at.isoformat() if sl.created_at else None,
            }
        )

    recipes_info = [
        {
            "id": r.id,
            "title": r.title,
            "has_shopping_list": any(sl["recipe_id"] == r.id for sl in lists_info),
        }
        for r in recipes[:20]  # Limiter à 20
    ]

    return {
        "user_id": current_user.id,
        "shopping_lists": lists_info,
        "recipes_sample": recipes_info,
        "total_recipes": len(recipes),
        "lists_with_recipe_id": sum(
            1 for sl in lists_info if sl["recipe_id"] is not None
        ),
        "lists_without_recipe_id": sum(
            1 for sl in lists_info if sl["recipe_id"] is None
        ),
    }
