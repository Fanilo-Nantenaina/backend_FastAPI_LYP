from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
import logging

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_user_fridge
from app.models.user import User
from app.models.fridge import Fridge
from app.models.recipe import Recipe, RecipeFavorite, RecipeIngredient
from app.models.product import Product
from sqlalchemy import or_

from app.schemas.recipe import (
    RecipeResponse,
    RecipeCreate,
    FeasibleRecipeResponse,
    SuggestedRecipeResponse,
    AddToFavoritesRequest,  # NOUVEAU
)
from app.services.recipe_service import RecipeService

router = APIRouter(prefix="/recipes", tags=["Recipes"])
logger = logging.getLogger(__name__)


@router.get("", response_model=List[RecipeResponse])
def list_recipes(
    db: Session = Depends(get_db),
    fridge_id: int = Query(None, description="Filtrer par frigo"),  # AJOUT
    difficulty: str = None,
    cuisine: str = None,
    limit: int = 50,
    sort_by: str = Query("date", regex="^(date|name|time)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
):
    """Liste toutes les recettes disponibles

    MODIFIÉ : Peut filtrer par fridge_id pour ne montrer que :
    - Les recettes globales (fridge_id = NULL)
    - Les recettes créées pour ce frigo spécifique
    """
    query = db.query(Recipe)

    if fridge_id is not None:
        query = query.filter(Recipe.fridge_id == fridge_id)

    if difficulty:
        query = query.filter(Recipe.difficulty == difficulty)
    if cuisine:
        query = query.filter(Recipe.extra_data["cuisine"].astext == cuisine)

    if sort_by == "name":
        query = query.order_by(
            Recipe.title.desc() if order == "desc" else Recipe.title.asc()
        )
    elif sort_by == "time":
        query = query.order_by(
            Recipe.preparation_time.desc()
            if order == "desc"
            else Recipe.preparation_time.asc()
        )
    else:
        query = query.order_by(
            Recipe.created_at.desc() if order == "desc" else Recipe.created_at.asc()
        )

    return query.limit(limit).all()


@router.post("", response_model=RecipeResponse, status_code=201)
def create_recipe(
    request: RecipeCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Créer une nouvelle recette

    MODIFIÉ : Supporte maintenant fridge_id optionnel
    """
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
    request: AddToFavoritesRequest,  # MODIFIÉ : Maintenant prend fridge_id
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """CU6: Marquer une recette comme favorite (RG16)

    MODIFIÉ : Nécessite maintenant un fridge_id
    Les favoris sont par frigo, pas globaux
    """
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # MODIFIÉ : Vérifier si déjà favori POUR CE FRIGO
    existing = (
        db.query(RecipeFavorite)
        .filter(
            RecipeFavorite.user_id == current_user.id,
            RecipeFavorite.recipe_id == recipe_id,
            RecipeFavorite.fridge_id == request.fridge_id,  # AJOUT
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Recipe already in favorites for this fridge"
        )

    # MODIFIÉ : Créer avec fridge_id
    favorite = RecipeFavorite(
        user_id=current_user.id,
        recipe_id=recipe_id,
        fridge_id=request.fridge_id,  # AJOUT
    )
    db.add(favorite)
    db.commit()
    return {"message": "Recipe added to favorites"}


@router.delete("/{recipe_id}/favorite", status_code=204)
def remove_from_favorites(
    recipe_id: int,
    fridge_id: int = Query(..., description="ID du frigo"),  # AJOUT
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retirer une recette des favoris

    MODIFIÉ : Nécessite maintenant un fridge_id en query param
    """
    favorite = (
        db.query(RecipeFavorite)
        .filter(
            RecipeFavorite.user_id == current_user.id,
            RecipeFavorite.recipe_id == recipe_id,
            RecipeFavorite.fridge_id == fridge_id,  # AJOUT
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
    fridge_id: int = Query(..., description="ID du frigo"),  # MODIFIÉ : Obligatoire
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """CU6: Consulter les recettes favorites

    MODIFIÉ : Filtre par fridge_id (obligatoire)
    """
    favorites = (
        db.query(Recipe)
        .join(RecipeFavorite)
        .filter(
            RecipeFavorite.user_id == current_user.id,
            RecipeFavorite.fridge_id == fridge_id,  # AJOUT
        )
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
    sort_by: str = Query("match", regex="^(match|name|date|time)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
):
    """CU6: Consulter les recettes faisables avec l'inventaire actuel

    MODIFIÉ : Ne retourne que les recettes :
    - Globales (fridge_id = NULL)
    - Créées pour ce frigo spécifique
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
    feasible_recipes = recipe_service.find_feasible_recipes(
        fridge_id=fridge_id,
        user=current_user,
        sort_by=sort_by,
        sort_order=order,
    )

    return feasible_recipes


@router.post("/fridges/{fridge_id}/suggest", response_model=SuggestedRecipeResponse)
async def suggest_recipe_with_ai(
    fridge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """NOUVELLE ROUTE: Suggestion IA de recette basée sur l'inventaire

    La recette suggérée sera liée à ce frigo
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
        # AJOUT : Inclure fridge_id dans la réponse
        suggested_recipe_dict = suggested_recipe.dict()
        suggested_recipe_dict["fridge_id"] = fridge_id
        return suggested_recipe_dict
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
    Sauvegarde une recette suggérée par l'IA dans la base de données
    ✅ CORRIGÉ : Utilise les available_ingredients de l'IA pour un matching précis
    """
    try:
        from app.services.vision_service import VisionService

        # Récupérer l'inventaire du frigo pour avoir les product_id disponibles
        from app.models.inventory import InventoryItem

        inventory_items = (
            db.query(InventoryItem)
            .filter(
                InventoryItem.fridge_id == suggestion.fridge_id,
                InventoryItem.quantity > 0,
            )
            .all()
        )

        # Créer un mapping product_id -> product pour l'inventaire
        inventory_products = {}
        for item in inventory_items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if product:
                inventory_products[product.id] = product

        logger.info(
            f"Inventaire du frigo {suggestion.fridge_id}: {len(inventory_products)} produits"
        )

        # Créer un set des noms disponibles (normalisés) depuis l'IA
        available_from_ai = set()
        if suggestion.available_ingredients:
            available_from_ai = {
                VisionService.normalize_product_name(name.strip())
                for name in suggestion.available_ingredients
            }
            logger.info(f"IA considère disponibles: {available_from_ai}")

        recipe = Recipe(
            title=suggestion.title,
            description=suggestion.description,
            steps=suggestion.steps,
            preparation_time=suggestion.preparation_time,
            difficulty=suggestion.difficulty,
            fridge_id=suggestion.fridge_id,
            extra_data={
                "created_from": "ai_suggestion",
                "created_by_user_id": current_user.id,
                "match_percentage": suggestion.match_percentage,
            },
        )
        db.add(recipe)
        db.flush()

        for ingredient_data in suggestion.ingredients:
            ingredient_name = ingredient_data["name"].strip()
            normalized_ingredient = VisionService.normalize_product_name(
                ingredient_name
            )

            # ✅ PRIORITÉ 1: Si l'IA dit que c'est disponible, chercher dans l'inventaire
            product = None
            best_match = None
            best_score = 0.0

            if normalized_ingredient in available_from_ai:
                logger.info(
                    f"🔍 '{ingredient_name}' marqué DISPONIBLE par l'IA, recherche dans inventaire..."
                )

                # Chercher parmi les produits de l'inventaire uniquement
                for prod_id, prod in inventory_products.items():
                    normalized_db = VisionService.normalize_product_name(prod.name)

                    # Match exact normalisé
                    if normalized_ingredient == normalized_db:
                        best_match = prod
                        best_score = 100.0
                        logger.info(f"  ✅ EXACT MATCH: '{prod.name}' (ID: {prod.id})")
                        break

                    # Similarité haute
                    similarity = VisionService.calculate_similarity(
                        normalized_ingredient, normalized_db
                    )

                    if (
                        similarity > best_score and similarity >= 60
                    ):  # Seuil abaissé pour inventaire
                        best_match = prod
                        best_score = similarity

                if best_match:
                    product = best_match
                    logger.info(
                        f"  ✅ Matched DISPONIBLE '{ingredient_name}' → '{product.name}' "
                        f"(ID: {product.id}, score: {best_score:.1f}%)"
                    )
                else:
                    logger.warning(
                        f"  ⚠️ L'IA dit '{ingredient_name}' disponible mais RIEN trouvé dans inventaire!"
                    )

            # ✅ PRIORITÉ 2: Si pas trouvé dans inventaire, chercher dans TOUS les produits
            if not product:
                all_products = db.query(Product).all()

                for prod in all_products:
                    normalized_db = VisionService.normalize_product_name(prod.name)

                    if normalized_ingredient == normalized_db:
                        product = prod
                        best_score = 100.0
                        logger.info(
                            f"  ✅ EXACT MATCH global: '{prod.name}' (ID: {prod.id})"
                        )
                        break

                    similarity = VisionService.calculate_similarity(
                        normalized_ingredient, normalized_db
                    )

                    if similarity > best_score and similarity >= 70:
                        product = prod
                        best_score = similarity

            # ✅ PRIORITÉ 3: Créer nouveau produit si aucun match
            if not product:
                product = Product(
                    name=ingredient_name.capitalize(),
                    category="Divers",
                    default_unit=ingredient_data.get("unit", "pièce"),
                    shelf_life_days=7,
                )
                db.add(product)
                db.flush()
                logger.info(
                    f"  🆕 Created new product: '{product.name}' (ID: {product.id})"
                )

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

        logger.info(
            f"✅ Saved AI-suggested recipe: {recipe.id} - {recipe.title} "
            f"(fridge_id: {recipe.fridge_id})"
        )

        return recipe

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save suggested recipe: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erreur lors de la sauvegarde: {str(e)}"
        )
