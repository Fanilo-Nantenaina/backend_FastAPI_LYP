from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Dict, Any
from app.models.recipe import Recipe, RecipeIngredient
from app.models.inventory import InventoryItem
from app.models.product import Product
from app.models.user import User
from app.schemas.recipe import RecipeCreate, FeasibleRecipeResponse


class RecipeService:
    def __init__(self, db: Session):
        self.db = db

    def create_recipe(self, request: RecipeCreate) -> Recipe:
        """Créer une nouvelle recette avec ses ingrédients"""
        recipe = Recipe(
            title=request.title,
            description=request.description,
            steps=request.steps,
            preparation_time=request.preparation_time,
            difficulty=request.difficulty,
            metadata=request.metadata or {},
        )

        self.db.add(recipe)
        self.db.flush()

        # Ajouter les ingrédients
        for ingredient in request.ingredients:
            recipe_ingredient = RecipeIngredient(
                recipe_id=recipe.id,
                product_id=ingredient.product_id,
                quantity=ingredient.quantity,
                unit=ingredient.unit,
            )
            self.db.add(recipe_ingredient)

        self.db.commit()
        self.db.refresh(recipe)
        return recipe

    def find_feasible_recipes(self, fridge_id: int, user: User) -> List[Dict[str, Any]]:
        """
        CU6: Trouve les recettes faisables avec l'inventaire actuel
        RG14: Exclut les recettes violant les restrictions alimentaires
        """
        # 1. Récupérer toutes les recettes
        all_recipes = self.db.query(Recipe).all()

        # 2. Récupérer l'inventaire actuel du frigo
        inventory = (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )

        # Créer un dictionnaire : product_id -> quantité disponible
        available_products = {
            item.product_id: {"quantity": item.quantity, "unit": item.unit}
            for item in inventory
        }

        # 3. Filtrer les recettes
        feasible_recipes = []

        for recipe in all_recipes:
            # RG14: Vérifier les restrictions alimentaires
            if not self._check_dietary_restrictions(recipe, user):
                continue

            # Vérifier si tous les ingrédients sont disponibles
            can_make, missing_ingredients = self._check_ingredients_availability(
                recipe, available_products
            )

            feasible_recipes.append(
                {
                    "recipe": recipe,
                    "can_make": can_make,
                    "missing_ingredients": missing_ingredients,
                    "match_percentage": self._calculate_match_percentage(
                        recipe, available_products
                    ),
                }
            )

        # Trier par pourcentage de correspondance (recettes les plus faisables en premier)
        feasible_recipes.sort(key=lambda x: x["match_percentage"], reverse=True)

        return feasible_recipes

    def _check_dietary_restrictions(self, recipe: Recipe, user: User) -> bool:
        """RG14: Vérifier que la recette ne viole pas les restrictions"""
        if not user.dietary_restrictions:
            return True

        # Récupérer les ingrédients de la recette
        ingredients = (
            self.db.query(RecipeIngredient)
            .filter(RecipeIngredient.recipe_id == recipe.id)
            .all()
        )

        for ingredient in ingredients:
            product = (
                self.db.query(Product)
                .filter(Product.id == ingredient.product_id)
                .first()
            )

            if product and product.tags:
                # Vérifier si un tag de l'ingrédient viole une restriction
                for restriction in user.dietary_restrictions:
                    if restriction.lower() in [tag.lower() for tag in product.tags]:
                        return False

        return True

    def _check_ingredients_availability(
        self, recipe: Recipe, available_products: Dict[int, Dict]
    ) -> tuple[bool, List[Dict]]:
        """Vérifie si tous les ingrédients sont disponibles en quantité suffisante"""
        ingredients = (
            self.db.query(RecipeIngredient)
            .filter(RecipeIngredient.recipe_id == recipe.id)
            .all()
        )

        missing = []

        for ingredient in ingredients:
            available = available_products.get(ingredient.product_id)

            if not available:
                # Produit complètement absent
                product = (
                    self.db.query(Product)
                    .filter(Product.id == ingredient.product_id)
                    .first()
                )

                missing.append(
                    {
                        "product_id": ingredient.product_id,
                        "product_name": product.name if product else "Unknown",
                        "required": ingredient.quantity,
                        "available": 0,
                        "unit": ingredient.unit,
                    }
                )
            elif available["quantity"] < ingredient.quantity:
                # Quantité insuffisante
                product = (
                    self.db.query(Product)
                    .filter(Product.id == ingredient.product_id)
                    .first()
                )

                missing.append(
                    {
                        "product_id": ingredient.product_id,
                        "product_name": product.name if product else "Unknown",
                        "required": ingredient.quantity,
                        "available": available["quantity"],
                        "unit": ingredient.unit,
                    }
                )

        can_make = len(missing) == 0
        return can_make, missing

    def _calculate_match_percentage(
        self, recipe: Recipe, available_products: Dict[int, Dict]
    ) -> float:
        """Calcule le pourcentage d'ingrédients disponibles"""
        ingredients = (
            self.db.query(RecipeIngredient)
            .filter(RecipeIngredient.recipe_id == recipe.id)
            .all()
        )

        if not ingredients:
            return 0.0

        available_count = sum(
            1 for ing in ingredients if ing.product_id in available_products
        )

        return (available_count / len(ingredients)) * 100
