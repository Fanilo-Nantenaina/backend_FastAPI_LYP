from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
import logging

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.fridge import Fridge
from app.models.recipe import Recipe, RecipeFavorite, RecipeIngredient
from app.models.product import Product

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
    V2 : Utilise matched_inventory_id fourni par l'IA pour garantir la cohérence
    """
    try:
        # Récupérer l'inventaire pour validation
        from app.models.inventory import InventoryItem

        inventory_items = (
            db.query(InventoryItem)
            .filter(
                InventoryItem.fridge_id == suggestion.fridge_id,
                InventoryItem.quantity > 0,
            )
            .all()
        )

        # Set des product_id valides dans l'inventaire
        valid_inventory_ids = {item.product_id for item in inventory_items}

        logger.info(f"Saving recipe for fridge {suggestion.fridge_id}")
        logger.info(f"Valid inventory IDs: {valid_inventory_ids}")

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

        ingredients_matched = 0
        ingredients_created = 0

        for ingredient_data in suggestion.ingredients:
            ingredient_name = ingredient_data.get("name", "").strip()
            matched_id = ingredient_data.get("matched_inventory_id")
            is_available = ingredient_data.get("is_available", False)

            product = None
            source = None

            #  PRIORITÉ 1 : Utiliser matched_inventory_id si fourni et valide
            if matched_id is not None and matched_id in valid_inventory_ids:
                product = db.query(Product).filter(Product.id == matched_id).first()
                if product:
                    source = f"matched_inventory_id={matched_id}"
                    ingredients_matched += 1
                    logger.info(
                        f"   '{ingredient_name}' → Product ID {matched_id} ({product.name}) [FROM AI MAPPING]"
                    )

            #  PRIORITÉ 2 : Chercher par nom exact dans tous les produits
            if not product:
                from app.services.vision_service import VisionService

                normalized = VisionService.normalize_product_name(ingredient_name)

                # D'abord dans l'inventaire
                for item in inventory_items:
                    inv_product = (
                        db.query(Product).filter(Product.id == item.product_id).first()
                    )
                    if inv_product:
                        inv_normalized = VisionService.normalize_product_name(
                            inv_product.name
                        )
                        if normalized == inv_normalized:
                            product = inv_product
                            source = "exact_match_inventory"
                            ingredients_matched += 1
                            logger.info(
                                f"   '{ingredient_name}' → Product ID {product.id} ({product.name}) [EXACT MATCH]"
                            )
                            break

            #  PRIORITÉ 3 : Chercher par similarité élevée dans l'inventaire
            if not product and is_available:
                from difflib import SequenceMatcher

                best_match = None
                best_score = 0.0

                for item in inventory_items:
                    inv_product = (
                        db.query(Product).filter(Product.id == item.product_id).first()
                    )
                    if inv_product:
                        score = SequenceMatcher(
                            None, ingredient_name.lower(), inv_product.name.lower()
                        ).ratio()

                        # Bonus si inclusion
                        if (
                            ingredient_name.lower() in inv_product.name.lower()
                            or inv_product.name.lower() in ingredient_name.lower()
                        ):
                            score = max(score, 0.75)

                        if score > best_score:
                            best_score = score
                            best_match = inv_product

                if (
                    best_match and best_score >= 0.4
                ):  # Seuil bas car l'IA dit que c'est dispo
                    product = best_match
                    source = f"fuzzy_inventory({best_score:.0%})"
                    ingredients_matched += 1
                    logger.info(
                        f"   '{ingredient_name}' → Product ID {product.id} ({product.name}) [FUZZY {best_score:.0%}]"
                    )

            #  PRIORITÉ 4 : Chercher dans tous les produits existants
            if not product:
                all_products = db.query(Product).all()
                from difflib import SequenceMatcher

                best_match = None
                best_score = 0.0

                for prod in all_products:
                    if prod.name.lower() == ingredient_name.lower():
                        product = prod
                        source = "exact_match_global"
                        logger.info(
                            f"   '{ingredient_name}' → Product ID {product.id} [EXACT GLOBAL]"
                        )
                        break

                    score = SequenceMatcher(
                        None, ingredient_name.lower(), prod.name.lower()
                    ).ratio()
                    if score > best_score and score >= 0.7:
                        best_score = score
                        best_match = prod

                if not product and best_match:
                    product = best_match
                    source = f"fuzzy_global({best_score:.0%})"
                    logger.info(
                        f"   '{ingredient_name}' → Product ID {product.id} ({product.name}) [FUZZY GLOBAL]"
                    )

            #  PRIORITÉ 5 : Créer nouveau produit uniquement en dernier recours
            if not product:
                product = Product(
                    name=ingredient_name.capitalize(),
                    category="Divers",
                    default_unit=ingredient_data.get("unit", "pièce"),
                    shelf_life_days=7,
                )
                db.add(product)
                db.flush()
                source = "created_new"
                ingredients_created += 1
                logger.info(f" '{ingredient_name}' → NEW Product ID {product.id}")

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

        #  Vérification finale de cohérence
        saved_ids = {ing.product_id for ing in recipe.ingredients}
        matched_with_inventory = saved_ids & valid_inventory_ids
        final_match_pct = (
            (len(matched_with_inventory) / len(saved_ids) * 100) if saved_ids else 0
        )

        logger.info(
            f" Source: {source}\n"
            f" Recipe saved: {recipe.id} - {recipe.title}\n"
            f"   Total ingredients: {len(saved_ids)}\n"
            f"   Matched from inventory: {ingredients_matched}\n"
            f"   Created new: {ingredients_created}\n"
            f"   Final match %: {final_match_pct:.1f}% (was {suggestion.match_percentage}%)"
        )

        #  Alerte si grosse différence
        if abs(final_match_pct - suggestion.match_percentage) > 10:
            logger.warning(
                f" MISMATCH ALERT: AI said {suggestion.match_percentage}% but actual is {final_match_pct:.1f}%"
            )

        return recipe

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save suggested recipe: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erreur lors de la sauvegarde: {str(e)}"
        )
