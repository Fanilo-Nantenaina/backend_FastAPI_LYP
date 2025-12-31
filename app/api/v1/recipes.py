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
    AddToFavoritesRequest,
)
from app.services.recipe_service import RecipeService

router = APIRouter(prefix="/recipes", tags=["Recipes"])
logger = logging.getLogger(__name__)


@router.get("", response_model=List[RecipeResponse])
def list_recipes(
    db: Session = Depends(get_db),
    fridge_id: int = Query(None, description="Filtrer par frigo"),
    difficulty: str = None,
    cuisine: str = None,
    limit: int = 50,
    sort_by: str = Query("date", pattern="^(date|name|time)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
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
    recipe_service = RecipeService(db)
    recipe = recipe_service.create_recipe(request)
    return recipe


@router.get("/{recipe_id}", response_model=RecipeResponse)
def get_recipe(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.post("/{recipe_id}/favorite", status_code=201)
def add_to_favorites(
    recipe_id: int,
    request: AddToFavoritesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    existing = (
        db.query(RecipeFavorite)
        .filter(
            RecipeFavorite.user_id == current_user.id,
            RecipeFavorite.recipe_id == recipe_id,
            RecipeFavorite.fridge_id == request.fridge_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Recipe already in favorites for this fridge"
        )

    favorite = RecipeFavorite(
        user_id=current_user.id,
        recipe_id=recipe_id,
        fridge_id=request.fridge_id,
    )
    db.add(favorite)
    db.commit()
    return {"message": "Recipe added to favorites"}


@router.delete("/{recipe_id}/favorite", status_code=204)
def remove_from_favorites(
    recipe_id: int,
    fridge_id: int = Query(..., description="ID du frigo"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    favorite = (
        db.query(RecipeFavorite)
        .filter(
            RecipeFavorite.user_id == current_user.id,
            RecipeFavorite.recipe_id == recipe_id,
            RecipeFavorite.fridge_id == fridge_id,
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
    fridge_id: int = Query(..., description="ID du frigo"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    favorites = (
        db.query(Recipe)
        .join(RecipeFavorite)
        .filter(
            RecipeFavorite.user_id == current_user.id,
            RecipeFavorite.fridge_id == fridge_id,
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
    sort_by: str = Query("match", pattern="^(match|name|date|time)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
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
    try:
        from app.models.inventory import InventoryItem
        from difflib import SequenceMatcher
        import unicodedata

        def normalize(s):
            s = s.lower().strip()
            s = unicodedata.normalize("NFD", s)
            s = "".join(c for c in s if unicodedata.category(c) != "Mn")
            return s

        inventory_items = (
            db.query(InventoryItem)
            .filter(
                InventoryItem.fridge_id == suggestion.fridge_id,
                InventoryItem.quantity > 0,
            )
            .all()
        )

        valid_inventory_ids = {item.product_id for item in inventory_items}

        inventory_products = {}
        for item in inventory_items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if product:
                inventory_products[item.product_id] = product

        print(f"=== SAVING RECIPE FOR FRIDGE {suggestion.fridge_id} ===")
        print(f"Inventory product IDs: {valid_inventory_ids}")
        print(f"AI match_percentage: {suggestion.match_percentage}%")

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
            if isinstance(ingredient_data, dict):
                ingredient_name = ingredient_data.get("name", "").strip()
                matched_id = ingredient_data.get("matched_inventory_id")
                is_available = ingredient_data.get("is_available", False)
                ing_quantity = ingredient_data.get("quantity", 1)
                ing_unit = ingredient_data.get("unit", "piece")
            else:
                ingredient_name = (
                    ingredient_data.name.strip() if ingredient_data.name else ""
                )
                matched_id = ingredient_data.matched_inventory_id
                is_available = ingredient_data.is_available
                ing_quantity = ingredient_data.quantity or 1
                ing_unit = ingredient_data.unit or "piece"

            product = None
            ing_normalized = normalize(ingredient_name)

            print(
                f"Processing: '{ingredient_name}' matched_id={matched_id} is_available={is_available}"
            )

            if matched_id is not None and matched_id in valid_inventory_ids:
                inv_product = inventory_products.get(matched_id)
                if inv_product:
                    inv_normalized = normalize(inv_product.name)

                    is_valid = (
                        ing_normalized == inv_normalized
                        or (
                            len(ing_normalized) >= 3
                            and ing_normalized in inv_normalized
                        )
                        or (
                            len(inv_normalized) >= 3
                            and inv_normalized in ing_normalized
                        )
                        or SequenceMatcher(None, ing_normalized, inv_normalized).ratio()
                        >= 0.7
                    )

                    if is_valid:
                        product = inv_product
                        print(
                            f"  -> matched_inventory_id OK: {matched_id} ({product.name})"
                        )
                    else:
                        print(
                            f"  -> REJECTED matched_id={matched_id}: '{ingredient_name}' != '{inv_product.name}'"
                        )

            if not product:
                for inv_product_id, inv_product in inventory_products.items():
                    inv_normalized = normalize(inv_product.name)

                    if ing_normalized == inv_normalized:
                        product = inv_product
                        print(
                            f"  -> Exact match: {inv_product.id} ({inv_product.name})"
                        )
                        break

                    if (
                        len(ing_normalized) >= 3 and ing_normalized in inv_normalized
                    ) or (
                        len(inv_normalized) >= 3 and inv_normalized in ing_normalized
                    ):
                        product = inv_product
                        print(
                            f"  -> Substring match: {inv_product.id} ({inv_product.name})"
                        )
                        break

            if not product:
                existing = (
                    db.query(Product)
                    .filter(Product.name.ilike(ingredient_name))
                    .first()
                )

                if existing:
                    product = existing
                    print(f"  -> Existing product: {existing.id} ({existing.name})")
                else:
                    product = Product(
                        name=ingredient_name.capitalize(),
                        category="Divers",
                        default_unit=ing_unit,
                        shelf_life_days=7,
                    )
                    db.add(product)
                    db.flush()
                    print(f"  -> Created new: {product.id} ({product.name})")

            recipe_ingredient = RecipeIngredient(
                recipe_id=recipe.id,
                product_id=product.id,
                quantity=ing_quantity,
                unit=ing_unit or product.default_unit,
            )
            db.add(recipe_ingredient)

        db.commit()
        db.refresh(recipe)

        saved_product_ids = {ing.product_id for ing in recipe.ingredients}
        final_matched = saved_product_ids & valid_inventory_ids
        final_percentage = (
            (len(final_matched) / len(saved_product_ids) * 100)
            if saved_product_ids
            else 0
        )

        print(f"=== RECIPE SAVED: {recipe.id} ===")
        print(f"  Ingredients: {len(saved_product_ids)}")
        print(
            f"  Matched with inventory: {len(final_matched)}/{len(saved_product_ids)}"
        )
        print(
            f"  Final percentage: {final_percentage:.1f}% (AI said: {suggestion.match_percentage}%)"
        )
        print(f"  Saved product IDs: {saved_product_ids}")
        print(f"  Inventory IDs: {valid_inventory_ids}")
        print(f"  Intersection: {final_matched}")
        print("=" * 50)

        return recipe

    except Exception as e:
        db.rollback()
        print(f"ERROR saving recipe: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Erreur lors de la sauvegarde: {str(e)}"
        )
