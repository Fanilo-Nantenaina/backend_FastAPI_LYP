from sqlalchemy.orm import Session
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
    SuggestedRecipeResponse,
)
from app.core.config import settings
from google import genai
from google.genai import types
from app.models.shopping_list import ShoppingList
from app.services.vision_service import VisionService

logger = logging.getLogger(__name__)


class RecipeService:
    def __init__(self, db: Session):
        self.db = db
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

    @transactional
    def create_recipe(self, request: RecipeCreate) -> Recipe:
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


    def find_feasible_recipes(
        self,
        fridge_id: int,
        user: User,
        sort_by: str = "match",
        sort_order: str = "desc",
    ) -> List[Dict[str, Any]]:
        import unicodedata

        def normalize(s):
            s = s.lower().strip()
            s = unicodedata.normalize("NFD", s)
            s = "".join(c for c in s if unicodedata.category(c) != "Mn")
            return s

        all_recipes = self.db.query(Recipe).filter(Recipe.fridge_id == fridge_id).all()

        inventory = (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )

        available_by_product_id = {}
        available_by_normalized_name = {}

        for item in inventory:
            product = self.db.query(Product).filter(Product.id == item.product_id).first()
            if product:
                available_by_product_id[item.product_id] = {
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "product": product,
                }
                norm_name = normalize(product.name)
                available_by_normalized_name[norm_name] = {
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "product_id": item.product_id,
                    "product": product,
                }

        print(f"=== FIND_FEASIBLE for fridge {fridge_id} ===")
        print(f"Inventory IDs: {set(available_by_product_id.keys())}")
        print(f"Inventory names: {list(available_by_normalized_name.keys())}")

        feasible_recipes = []

        for recipe in all_recipes:
            if not self._check_dietary_restrictions(recipe, user):
                continue

            recipe_ingredients = recipe.ingredients
            total_ingredients = len(recipe_ingredients)

            if total_ingredients == 0:
                continue

            available_count = 0
            missing_ingredients = []

            print(f"\nRecipe: {recipe.title}")

            for ingredient in recipe_ingredients:
                product_id = ingredient.product_id
                required_qty = ingredient.quantity or 0

                ingredient_product = (
                    self.db.query(Product).filter(Product.id == product_id).first()
                )
                ingredient_name = (
                    ingredient_product.name
                    if ingredient_product
                    else f"Product #{product_id}"
                )
                ing_normalized = normalize(ingredient_name)

                found = False

                if product_id in available_by_product_id:
                    available = available_by_product_id[product_id]
                    if available["quantity"] >= required_qty:
                        available_count += 1
                        found = True
                        print(f"  [OK by ID] {ingredient_name} (id={product_id})")

                if not found and ing_normalized in available_by_normalized_name:
                    available = available_by_normalized_name[ing_normalized]
                    if available["quantity"] >= required_qty:
                        available_count += 1
                        found = True
                        print(
                            f"  [OK by name] {ingredient_name} -> {available['product'].name}"
                        )

                if not found:
                    for inv_norm_name, inv_data in available_by_normalized_name.items():
                        if (
                            len(ing_normalized) >= 3 and ing_normalized in inv_norm_name
                        ) or (len(inv_norm_name) >= 3 and inv_norm_name in ing_normalized):
                            if inv_data["quantity"] >= required_qty:
                                available_count += 1
                                found = True
                                print(
                                    f"  [OK by substring] {ingredient_name} -> {inv_data['product'].name}"
                                )
                                break

                if not found:
                    missing_ingredients.append(
                        {
                            "product_id": product_id,
                            "product_name": ingredient_name,
                            "quantity": required_qty,
                            "unit": ingredient.unit,
                            "available_quantity": 0,
                        }
                    )
                    print(f"  [MISSING] {ingredient_name}")

            match_percentage = (available_count / total_ingredients) * 100
            can_make = len(missing_ingredients) == 0

            print(f"  => {available_count}/{total_ingredients} = {match_percentage:.1f}%")

            shopping_list_status = None
            shopping_list_id = None
            ingredients_complete = can_make
            purchased_missing_count = 0
            total_missing_count = len(missing_ingredients)
            combined_percentage = match_percentage

            related_shopping_list = (
                self.db.query(ShoppingList)
                .filter(
                    ShoppingList.recipe_id == recipe.id,
                    ShoppingList.fridge_id == fridge_id,
                    ShoppingList.user_id == user.id,
                    ShoppingList.status != "cancelled",
                )
                .order_by(ShoppingList.created_at.desc())
                .first()
            )

            if related_shopping_list:
                shopping_list_id = related_shopping_list.id
                shopping_items = related_shopping_list.items
                total_items = len(shopping_items)

                if total_items > 0:
                    purchased_items_count = sum(
                        1 for item in shopping_items if item.status == "purchased"
                    )

                    if purchased_items_count == total_items:
                        shopping_list_status = "completed"
                    elif purchased_items_count > 0:
                        shopping_list_status = "in_progress"
                    else:
                        shopping_list_status = "pending"

                    purchased_missing_count = purchased_items_count
                    total_missing_count = total_items

                    shopping_completion_ratio = purchased_items_count / total_items
                    missing_percentage = 100 - match_percentage
                    combined_percentage = match_percentage + (
                        shopping_completion_ratio * missing_percentage
                    )

                    if purchased_items_count == total_items:
                        combined_percentage = 100.0
                        ingredients_complete = True

                    print(
                        f"  Shopping list: {purchased_items_count}/{total_items} purchased"
                    )
                    print(
                        f"  Combined: {match_percentage:.1f}% + ({purchased_items_count}/{total_items} * {missing_percentage:.1f}%) = {combined_percentage:.1f}%"
                    )

            feasible_recipes.append(
                {
                    "recipe": recipe,
                    "can_make": can_make,
                    "missing_ingredients": missing_ingredients,
                    "match_percentage": round(match_percentage, 1),
                    "shopping_list_id": shopping_list_id,
                    "shopping_list_status": shopping_list_status,
                    "ingredients_complete": ingredients_complete,
                    "combined_percentage": round(combined_percentage, 1),
                    "purchased_missing_count": purchased_missing_count,
                    "total_missing_count": total_missing_count,
                }
            )

        reverse = sort_order == "desc"

        if sort_by == "match":
            feasible_recipes.sort(key=lambda x: x["combined_percentage"], reverse=reverse)
        elif sort_by == "name":
            feasible_recipes.sort(key=lambda x: x["recipe"].title.lower(), reverse=reverse)
        elif sort_by == "date":
            feasible_recipes.sort(key=lambda x: x["recipe"].created_at, reverse=reverse)
        elif sort_by == "time":
            feasible_recipes.sort(
                key=lambda x: x["recipe"].preparation_time or 9999, reverse=reverse
            )

        print("=" * 50)
        return feasible_recipes

    def _check_dietary_restrictions(self, recipe: Recipe, user: User) -> bool:
        if not user.dietary_restrictions:
            return True

        for ingredient in recipe.ingredients:
            product = (
                self.db.query(Product)
                .filter(Product.id == ingredient.product_id)
                .first()
            )
            if product and product.tags:
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
        missing = []

        for ingredient in recipe.ingredients:
            product_id = ingredient.product_id
            required_qty = ingredient.quantity or 0

            available = available_products.get(product_id)

            if not available:
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
        if not recipe.ingredients:
            return 0.0

        total_ingredients = len(recipe.ingredients)
        available_count = 0

        for ingredient in recipe.ingredients:
            if ingredient.product_id in available_products:
                available = available_products[ingredient.product_id]
                required = ingredient.quantity or 0

                if available["quantity"] >= required:
                    available_count += 1

                elif available["quantity"] > 0:
                    available_count += available["quantity"] / required

        match_percentage = (available_count / total_ingredients) * 100

        return round(match_percentage, 1)

    async def suggest_recipe_with_ai(
        self, fridge_id: int, user: User
    ) -> SuggestedRecipeResponse:
        import traceback

        try:
            inventory_items = (
                self.db.query(InventoryItem)
                .filter(
                    InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0
                )
                .all()
            )

            available_ingredients = []
            inventory_map = {}

            for item in inventory_items:
                product = (
                    self.db.query(Product).filter(Product.id == item.product_id).first()
                )
                if product:
                    ingredient_info = {
                        "id": item.product_id,
                        "name": product.name,
                        "quantity": item.quantity,
                        "unit": item.unit or product.default_unit or "piece",
                        "category": product.category or "Divers",
                    }
                    available_ingredients.append(ingredient_info)
                    inventory_map[item.product_id] = product

            print(f"=== INVENTORY FOR FRIDGE {fridge_id} ===")
            for ing in available_ingredients:
                print(f"  [{ing['id']}] {ing['name']}")
            print("=" * 50)

            if not available_ingredients:
                return SuggestedRecipeResponse(
                    title="Inventaire vide",
                    description="Votre frigo ne contient aucun ingredient reconnu.",
                    ingredients=[],
                    steps="1. Ajoutez des produits a votre inventaire",
                    preparation_time=0,
                    difficulty="easy",
                    available_ingredients=[],
                    missing_ingredients=[],
                    match_percentage=0.0,
                )

            dietary_restrictions = user.dietary_restrictions or []
            restrictions_text = (
                ", ".join(dietary_restrictions) if dietary_restrictions else "Aucune"
            )
            cuisine_text = (
                user.preferred_cuisine if user.preferred_cuisine else "Variee"
            )

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
                            },
                            "required": ["name", "quantity", "unit"],
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

            prompt = f"""Tu es un chef cuisinier creatif. Suggere UNE recette basee sur les ingredients disponibles.

    INGREDIENTS DISPONIBLES DANS LE FRIGO:
    {ingredients_text}

    PREFERENCES:
    - Cuisine preferee: {cuisine_text}
    - Restrictions alimentaires: {restrictions_text}

    {self._generate_dietary_restrictions_rules(dietary_restrictions)}

    REGLES:
    - Utilise EN PRIORITE les ingredients listes ci-dessus
    - Tu peux suggerer quelques ingredients de base manquants (sel, poivre, huile)
    - Temps de preparation en minutes
    - Difficulte: "easy", "medium" ou "hard"
    - Reponds en FRANCAIS

    Reponds UNIQUEMENT en JSON."""

            print("Calling Gemini API...")

            config = types.GenerateContentConfig(
                system_instruction=(
                    "Tu es un chef expert. Utilise principalement les ingredients fournis. "
                    "Reponds en francais et uniquement en JSON."
                ),
                response_mime_type="application/json",
                response_schema=output_schema,
            )

            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt],
                config=config,
            )

            print("Gemini API response received")

            data = json.loads(response.text)

            print(f"Recipe title: {data.get('title')}")
            print(
                f"Ingredients from AI: {[ing.get('name') for ing in data.get('ingredients', [])]}"
            )

            processed_ingredients = []
            available_names = []
            missing_ingredients = []

            for ing in data.get("ingredients", []):
                ing_name = ing.get("name", "").strip()

                if self._ingredient_violates_restrictions(
                    ing_name, dietary_restrictions
                ):
                    continue

                matched_product_id = self._match_ingredient_to_inventory(
                    ing_name, available_ingredients
                )

                print(f"AI ingredient: '{ing_name}' -> matched_id={matched_product_id}")

                ing_data = {
                    "name": ing_name,
                    "quantity": ing.get("quantity", 1),
                    "unit": ing.get("unit", ""),
                    "is_available": matched_product_id is not None,
                    "matched_inventory_id": matched_product_id,
                    "matched_inventory_name": inventory_map[matched_product_id].name
                    if matched_product_id
                    else None,
                }

                if matched_product_id:
                    available_names.append(ing_name)
                else:
                    missing_ingredients.append(
                        {
                            "name": ing_name,
                            "quantity": ing.get("quantity", 1),
                            "unit": ing.get("unit", ""),
                        }
                    )

                processed_ingredients.append(ing_data)

            total = len(processed_ingredients)
            available_count = sum(
                1 for ing in processed_ingredients if ing["is_available"]
            )
            match_percentage = (available_count / total * 100) if total > 0 else 0

            print("=== AI SUGGESTION RESULT ===")
            print(f"  Total ingredients: {total}")
            print(f"  Available: {available_count}")
            print(f"  Match percentage: {match_percentage:.1f}%")
            for ing in processed_ingredients:
                status = "OK" if ing["is_available"] else "MISSING"
                print(
                    f"    [{status}] {ing['name']} -> product_id={ing['matched_inventory_id']}"
                )
            print("=" * 50)

            return SuggestedRecipeResponse(
                title=data.get("title", "Recette suggeree"),
                description=data.get("description", ""),
                ingredients=processed_ingredients,
                steps=data.get("steps", ""),
                preparation_time=data.get("preparation_time", 30),
                difficulty=data.get("difficulty", "medium"),
                available_ingredients=available_names,
                missing_ingredients=missing_ingredients,
                match_percentage=round(match_percentage, 1),
            )

        except Exception as e:
            print(f"ERROR in suggest_recipe_with_ai: {e}")
            traceback.print_exc()
            raise

    def _match_ingredient_to_inventory(self, ingredient_name: str, inventory: list):
        from difflib import SequenceMatcher
        import unicodedata

        def normalize(s):
            s = s.lower().strip()
            s = unicodedata.normalize("NFD", s)
            s = "".join(c for c in s if unicodedata.category(c) != "Mn")
            return s

        ingredient_normalized = normalize(ingredient_name)
        ingredient_words = set(ingredient_normalized.split())

        best_match_id = None
        best_score = 0.0
        best_name = None

        for inv_item in inventory:
            inv_name = inv_item["name"]
            inv_normalized = normalize(inv_name)
            inv_words = set(inv_normalized.split())

            if ingredient_normalized == inv_normalized:
                return inv_item["id"]

            if len(ingredient_normalized) >= 3 and len(inv_normalized) >= 3:
                if ingredient_normalized in inv_normalized:
                    return inv_item["id"]
                if inv_normalized in ingredient_normalized:
                    return inv_item["id"]

            if ingredient_words and inv_words:
                common_words = ingredient_words & inv_words
                if common_words:
                    significant_common = [w for w in common_words if len(w) >= 3]
                    if significant_common:
                        return inv_item["id"]

            score = SequenceMatcher(None, ingredient_normalized, inv_normalized).ratio()
            if score > best_score:
                best_score = score
                best_match_id = inv_item["id"]
                best_name = inv_name

        if best_score >= 0.75:
            print(
                f"    Fuzzy match: '{ingredient_name}' ~ '{best_name}' (score={best_score:.2f})"
            )
            return best_match_id

        return None

    def _generate_dietary_restrictions_rules(
        self, dietary_restrictions: List[str]
    ) -> str:
        if not dietary_restrictions:
            return "Aucune restriction alimentaire."

            rules = []

            restrictions_lower = [r.lower().strip() for r in dietary_restrictions]

            if "vegan" in restrictions_lower or "végétalien" in restrictions_lower:
                rules.append(
                    "- INTERDICTION ABSOLUE: viande, poisson, œufs, lait, beurre, fromage, miel, crème, yaourt"
                )
                rules.append(
                    "- AUTORISÉ: légumes, fruits, céréales, légumineuses, noix, lait végétal"
                )

            if "vegetarian" in restrictions_lower or "végétarien" in restrictions_lower:
                rules.append("- INTERDICTION: viande, poisson, fruits de mer")
                rules.append("- AUTORISÉ: œufs, produits laitiers, légumes, fruits")

            if (
                "gluten-free" in restrictions_lower
                or "sans gluten" in restrictions_lower
            ):
                rules.append(
                    "- INTERDICTION: blé, farine de blé, pain classique, pâtes de blé, semoule"
                )
                rules.append(
                    "- AUTORISÉ: riz, quinoa, maïs, pommes de terre, farine sans gluten"
                )

            if (
                "dairy-free" in restrictions_lower
                or "sans lactose" in restrictions_lower
            ):
                rules.append("- INTERDICTION: lait, fromage, beurre, crème, yaourt")
                rules.append(
                    "- AUTORISÉ: lait végétal (amande, soja, avoine), margarine végétale"
                )

            if "nut-free" in restrictions_lower or "sans noix" in restrictions_lower:
                rules.append(
                    "- INTERDICTION: noix, amandes, noisettes, cacahuètes, pistaches"
                )

            if "halal" in restrictions_lower:
                rules.append("- INTERDICTION: porc, alcool")

            if "kosher" in restrictions_lower or "casher" in restrictions_lower:
                rules.append("- INTERDICTION: porc, fruits de mer, mélange viande+lait")

            rules.append(
                f"\nL'UTILISATEUR A LES RESTRICTIONS SUIVANTES: {', '.join(dietary_restrictions)}"
            )
            rules.append("NE SUGGÈRE AUCUN INGRÉDIENT QUI VIOLE CES RESTRICTIONS.")

            return "\n".join(rules)

    def _ingredient_violates_restrictions(
        self, ingredient_name: str, dietary_restrictions: List[str]
    ) -> bool:
        if not dietary_restrictions:
            return False

        ingredient_lower = ingredient_name.lower().strip()
        restrictions_lower = [r.lower().strip() for r in dietary_restrictions]

        forbidden_foods = {
            "vegan": [
                "viande",
                "poulet",
                "bœuf",
                "porc",
                "agneau",
                "poisson",
                "saumon",
                "thon",
                "œuf",
                "lait",
                "fromage",
                "beurre",
                "crème",
                "yaourt",
                "miel",
            ],
            "végétalien": [
                "viande",
                "poulet",
                "bœuf",
                "porc",
                "agneau",
                "poisson",
                "œuf",
                "lait",
                "fromage",
                "beurre",
                "crème",
                "yaourt",
                "miel",
            ],
            "vegetarian": [
                "viande",
                "poulet",
                "bœuf",
                "porc",
                "agneau",
                "poisson",
                "saumon",
                "thon",
            ],
            "végétarien": ["viande", "poulet", "bœuf", "porc", "agneau", "poisson"],
            "gluten-free": ["blé", "farine de blé", "pain", "pâtes", "semoule"],
            "sans gluten": ["blé", "farine", "pain", "pâtes", "semoule"],
            "dairy-free": ["lait", "fromage", "beurre", "crème", "yaourt"],
            "sans lactose": ["lait", "fromage", "beurre", "crème", "yaourt"],
            "nut-free": ["noix", "amande", "noisette", "cacahuète", "pistache"],
            "sans noix": ["noix", "amande", "noisette", "cacahuète"],
            "halal": ["porc", "alcool", "vin"],
            "kosher": ["porc", "crabe", "crevette", "homard"],
            "casher": ["porc", "crabe", "crevette", "homard"],
        }

        for restriction in restrictions_lower:
            forbidden_list = forbidden_foods.get(restriction, [])

            for forbidden in forbidden_list:
                if forbidden in ingredient_lower:
                    logger.warning(
                        f"Ingredient '{ingredient_name}' contains forbidden food '{forbidden}' "
                        f"for restriction '{restriction}'"
                    )
                    return True

        return False
