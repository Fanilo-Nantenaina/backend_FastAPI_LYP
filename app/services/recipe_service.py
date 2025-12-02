from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Dict, Any
import json
import logging

from app.middleware.transaction_handler import transactional
from app.models.recipe import Recipe, RecipeIngredient
from app.models.inventory import InventoryItem
from app.models.product import Product
from app.models.user import User
from app.schemas.recipe import (
    RecipeCreate,
    FeasibleRecipeResponse,
    SuggestedRecipeResponse,
)
from app.core.config import settings

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class RecipeService:
    def __init__(self, db: Session):
        self.db = db
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

    @transactional
    def create_recipe(self, request: RecipeCreate) -> Recipe:
        """Créer une nouvelle recette avec ses ingrédients"""
        recipe = Recipe(
            title=request.title,
            description=request.description,
            steps=request.steps,
            preparation_time=request.preparation_time,
            difficulty=request.difficulty,
            extra_data=request.extra_data or {},
        )
        self.db.add(recipe)
        self.db.flush()

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
        """CU6: Trouve les recettes faisables avec l'inventaire actuel"""
        all_recipes = self.db.query(Recipe).all()
        inventory = (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )

        available_products = {
            item.product_id: {"quantity": item.quantity, "unit": item.unit}
            for item in inventory
        }

        feasible_recipes = []
        for recipe in all_recipes:
            if not self._check_dietary_restrictions(recipe, user):
                continue

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

        feasible_recipes.sort(key=lambda x: x["match_percentage"], reverse=True)
        return feasible_recipes

    def _check_dietary_restrictions(self, recipe: Recipe, user: User) -> bool:
        """
        Vérifie si la recette respecte les restrictions alimentaires de l'utilisateur

        Args:
            recipe: La recette à vérifier
            user: L'utilisateur avec ses restrictions

        Returns:
            True si la recette est compatible, False sinon
        """
        if not user.dietary_restrictions:
            return True

        # Charger les ingrédients avec leurs produits
        for ingredient in recipe.ingredients:
            product = (
                self.db.query(Product)
                .filter(Product.id == ingredient.product_id)
                .first()
            )
            if product and product.tags:
                # Vérifier si un tag du produit correspond à une restriction
                for restriction in user.dietary_restrictions:
                    restriction_lower = restriction.lower().strip()
                    for tag in product.tags:
                        if tag.lower().strip() == restriction_lower:
                            logger.info(
                                f"Recipe '{recipe.title}' excluded: "
                                f"contains {product.name} with tag '{tag}' "
                                f"matching restriction '{restriction}'"
                            )
                            return False

        return True

    def _check_ingredients_availability(
        self, recipe: Recipe, available_products: Dict[int, Dict]
    ) -> tuple:
        """
        Vérifie quels ingrédients sont disponibles et lesquels manquent

        Args:
            recipe: La recette à vérifier
            available_products: Dict {product_id: {"quantity": float, "unit": str}}

        Returns:
            Tuple (can_make: bool, missing_ingredients: List[Dict])
        """
        missing = []

        for ingredient in recipe.ingredients:
            product_id = ingredient.product_id
            required_qty = ingredient.quantity or 0

            available = available_products.get(product_id)

            if not available:
                # Produit complètement absent
                product = (
                    self.db.query(Product).filter(Product.id == product_id).first()
                )
                missing.append(
                    {
                        "product_id": product_id,
                        "product_name": (
                            product.name if product else f"Product #{product_id}"
                        ),
                        "quantity": required_qty,
                        "unit": ingredient.unit,
                        "available_quantity": 0,
                    }
                )
            elif available["quantity"] < required_qty:
                # Produit présent mais quantité insuffisante
                product = (
                    self.db.query(Product).filter(Product.id == product_id).first()
                )
                missing.append(
                    {
                        "product_id": product_id,
                        "product_name": (
                            product.name if product else f"Product #{product_id}"
                        ),
                        "quantity": required_qty,
                        "unit": ingredient.unit,
                        "available_quantity": available["quantity"],
                    }
                )

        can_make = len(missing) == 0

        return can_make, missing

    def _calculate_match_percentage(
        self, recipe: Recipe, available_products: Dict[int, Dict]
    ) -> float:
        """
        Calcule le pourcentage de correspondance entre l'inventaire et la recette

        Args:
            recipe: La recette
            available_products: Produits disponibles

        Returns:
            Pourcentage de 0 à 100
        """
        if not recipe.ingredients:
            return 0.0

        total_ingredients = len(recipe.ingredients)
        available_count = 0

        for ingredient in recipe.ingredients:
            if ingredient.product_id in available_products:
                available = available_products[ingredient.product_id]
                required = ingredient.quantity or 0

                # Compter comme disponible si on a au moins la quantité requise
                if available["quantity"] >= required:
                    available_count += 1
                # Compter partiellement si on a une partie de la quantité
                elif available["quantity"] > 0:
                    available_count += available["quantity"] / required

        match_percentage = (available_count / total_ingredients) * 100

        return round(match_percentage, 1)

    async def suggest_recipe_with_ai(
        self, fridge_id: int, user: User
    ) -> SuggestedRecipeResponse:
        """
        ✅ CORRIGÉ: Suggère une recette créative basée sur l'inventaire actuel
        """
        import logging

        logger = logging.getLogger(__name__)

        # ✅ CORRECTION: Requête séparée pour éviter les problèmes de JOIN
        inventory_items = (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )

        logger.info(f"Found {len(inventory_items)} items in fridge {fridge_id}")

        # ✅ Construire la liste des ingrédients disponibles
        available_ingredients = []
        for item in inventory_items:
            # ✅ CORRECTION: Récupérer le produit séparément
            product = (
                self.db.query(Product).filter(Product.id == item.product_id).first()
            )

            if product:
                ingredient_info = {
                    "name": product.name,
                    "quantity": item.quantity,
                    "unit": item.unit or product.default_unit or "pièce",
                    "category": product.category or "Divers",
                }
                available_ingredients.append(ingredient_info)
                logger.info(f"  - {product.name}: {item.quantity} {item.unit}")
            else:
                logger.warning(f"  - Product ID {item.product_id} not found!")

        # ✅ DEBUG: Log complet
        logger.info(f"Total available ingredients: {len(available_ingredients)}")
        for ing in available_ingredients:
            logger.info(f"  -> {ing}")

        # ✅ CORRECTION: Message plus explicite si inventaire vide
        if not available_ingredients:
            logger.warning(f"No valid ingredients found for fridge {fridge_id}")
            return SuggestedRecipeResponse(
                title="Inventaire vide",
                description="Votre frigo ne contient aucun ingrédient reconnu. "
                "Ajoutez des produits via le scan ou manuellement pour obtenir des suggestions de recettes personnalisées.",
                ingredients=[],
                steps="1. Ajoutez des produits à votre inventaire\n"
                "2. Revenez ici pour découvrir des recettes adaptées à vos ingrédients",
                preparation_time=0,
                difficulty="easy",
                available_ingredients=[],
                missing_ingredients=[],
                match_percentage=0.0,
            )

        # Préférences utilisateur
        dietary_restrictions = user.dietary_restrictions or []
        preferred_cuisine = user.preferred_cuisine

        output_schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "ingredients": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit": {"type": "string"},
                            "is_available": {"type": "boolean"},
                        },
                        "required": ["name", "quantity", "unit", "is_available"],
                    },
                },
                "steps": {"type": "string"},
                "preparation_time": {"type": "integer"},
                "difficulty": {"type": "string"},
            },
            "required": [
                "title",
                "description",
                "ingredients",
                "steps",
                "preparation_time",
                "difficulty",
            ],
        }

        ingredients_text = "\n".join(
            [
                f"- {ing['name']}: {ing['quantity']} {ing['unit']} ({ing['category']})"
                for ing in available_ingredients
            ]
        )

        restrictions_text = (
            ", ".join(dietary_restrictions) if dietary_restrictions else "Aucune"
        )
        cuisine_text = preferred_cuisine if preferred_cuisine else "Variée"

        prompt = f"""Tu es un chef cuisinier créatif. Suggère UNE recette originale et délicieuse basée sur les ingrédients disponibles.

    INGRÉDIENTS DISPONIBLES DANS LE FRIGO:
    {ingredients_text}

    PRÉFÉRENCES DE L'UTILISATEUR:
    - Cuisine préférée: {cuisine_text}
    - Restrictions alimentaires: {restrictions_text}

    RÈGLES IMPORTANTES:
    1. UTILISE EN PRIORITÉ les ingrédients listés ci-dessus
    2. Tu peux suggérer quelques ingrédients de base manquants (sel, poivre, huile, épices courantes)
    3. La recette doit être réalisable à la maison
    4. Donne des instructions claires et détaillées étape par étape
    5. Pour chaque ingrédient:
    - is_available: true → si l'ingrédient est dans la liste ci-dessus
    - is_available: false → si c'est un ingrédient de base à acheter
    6. Le temps de préparation doit être en minutes
    7. La difficulté doit être "easy", "medium" ou "hard"
    8. Sois créatif et propose quelque chose d'intéressant!

    Réponds UNIQUEMENT en JSON structuré."""

        try:
            config = types.GenerateContentConfig(
                system_instruction="Tu es un chef cuisinier expert qui suggère des recettes créatives. Réponds uniquement en JSON.",
                response_mime_type="application/json",
                response_schema=output_schema,
            )

            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt],
                config=config,
            )

            data = json.loads(response.text)
            logger.info(f"AI response: {data.get('title', 'No title')}")

            # ✅ Traitement amélioré des ingrédients
            available_names_lower = [
                ing["name"].lower().strip() for ing in available_ingredients
            ]
            suggested_ingredients = []
            missing_ingredients = []

            for ing in data.get("ingredients", []):
                ing_name = ing.get("name", "").strip()
                ing_data = {
                    "name": ing_name,
                    "quantity": ing.get("quantity", 1),
                    "unit": ing.get("unit", ""),
                }

                # ✅ Vérification améliorée de disponibilité
                is_available = ing.get("is_available", False)

                # Double-check: vérifier si le nom correspond à un ingrédient disponible
                name_lower = ing_name.lower().strip()
                actually_available = any(
                    avail_name in name_lower or name_lower in avail_name
                    for avail_name in available_names_lower
                )

                if is_available or actually_available:
                    suggested_ingredients.append(ing_data)
                else:
                    missing_ingredients.append(ing_data)

            total_ingredients = len(data.get("ingredients", []))
            available_count = len(suggested_ingredients)
            match_percentage = (
                (available_count / total_ingredients * 100)
                if total_ingredients > 0
                else 0
            )

            logger.info(
                f"Match: {available_count}/{total_ingredients} = {match_percentage:.1f}%"
            )

            return SuggestedRecipeResponse(
                title=data.get("title", "Recette suggérée"),
                description=data.get("description", ""),
                ingredients=data.get("ingredients", []),
                steps=data.get("steps", ""),
                preparation_time=data.get("preparation_time", 30),
                difficulty=data.get("difficulty", "medium"),
                available_ingredients=[ing["name"] for ing in suggested_ingredients],
                missing_ingredients=missing_ingredients,
                match_percentage=round(match_percentage, 1),
            )

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            raise Exception(f"Erreur de parsing de la réponse IA: {str(e)}")
        except Exception as e:
            logger.error(f"Erreur lors de la génération de recette IA: {e}")
            raise Exception(f"Erreur lors de la génération de la recette: {str(e)}")
