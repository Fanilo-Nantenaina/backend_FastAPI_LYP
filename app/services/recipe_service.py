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
        all_recipes = self.db.query(Recipe).filter(Recipe.fridge_id == fridge_id).all()

        inventory = (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )

        available_by_product_id = {}
        available_by_normalized_name = {}

        for item in inventory:
            product = (
                self.db.query(Product).filter(Product.id == item.product_id).first()
            )
            if product:
                available_by_product_id[item.product_id] = {
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "product": product,
                }
                normalized = VisionService.normalize_product_name(product.name)
                available_by_normalized_name[normalized] = {
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "product_id": item.product_id,
                    "product": product,
                }

        logger.info(
            f" Inventaire du frigo {fridge_id}: {len(available_by_product_id)} produits"
        )

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
            matched_product_ids = set()

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
                normalized_name = VisionService.normalize_product_name(ingredient_name)

                available = available_by_product_id.get(product_id)

                if not available:
                    available = available_by_normalized_name.get(normalized_name)
                    if available:
                        logger.debug(
                            f"   Match par nom: '{ingredient_name}' → inventory product_id={available['product_id']}"
                        )

                if available and available["quantity"] >= required_qty:
                    available_count += 1
                    matched_product_ids.add(product_id)
                    logger.debug(f"   {ingredient_name} disponible")
                else:
                    missing_ingredients.append(
                        {
                            "product_id": product_id,
                            "product_name": ingredient_name,
                            "quantity": required_qty,
                            "unit": ingredient.unit,
                            "available_quantity": available["quantity"]
                            if available
                            else 0,
                        }
                    )
                    logger.debug(f"   {ingredient_name} manquant")

            match_percentage = (available_count / total_ingredients) * 100
            can_make = len(missing_ingredients) == 0

            logger.info(
                f"📊 Recipe '{recipe.title}': "
                f"{available_count}/{total_ingredients} ingrédients → "
                f"match={match_percentage:.1f}%, missing={len(missing_ingredients)}"
            )

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
                    purchased_by_product_id = set()
                    purchased_by_name = set()

                    for item in shopping_items:
                        if item.status == "purchased":
                            purchased_by_product_id.add(item.product_id)

                            item_product = (
                                self.db.query(Product)
                                .filter(Product.id == item.product_id)
                                .first()
                            )
                            if item_product:
                                purchased_by_name.add(
                                    VisionService.normalize_product_name(
                                        item_product.name
                                    )
                                )

                    purchased_items_count = len(purchased_by_product_id)

                    logger.info(
                        f"  🛒 Shopping list #{shopping_list_id}: {purchased_items_count}/{total_items} achetés"
                    )
                    logger.debug(f"     IDs achetés: {purchased_by_product_id}")
                    logger.debug(f"     Noms achetés: {purchased_by_name}")

                    if purchased_items_count == total_items:
                        shopping_list_status = "completed"
                    elif purchased_items_count > 0:
                        shopping_list_status = "in_progress"
                    else:
                        shopping_list_status = "pending"

                    for missing in missing_ingredients:
                        missing_product_id = missing.get("product_id")
                        missing_name = VisionService.normalize_product_name(
                            missing.get("product_name", "")
                        )

                        if missing_product_id in purchased_by_product_id:
                            purchased_missing_count += 1
                            logger.debug(
                                f"      Manquant '{missing['product_name']}' acheté (par ID)"
                            )
                        elif missing_name in purchased_by_name:
                            purchased_missing_count += 1
                            logger.debug(
                                f"      Manquant '{missing['product_name']}' acheté (par nom)"
                            )

                    logger.info(
                        f"  📈 Ingrédients manquants achetés: {purchased_missing_count}/{total_missing_count}"
                    )

                    if total_missing_count > 0:
                        missing_covered_ratio = (
                            purchased_missing_count / total_missing_count
                        )

                        missing_percentage = 100 - match_percentage
                        added_from_shopping = missing_covered_ratio * missing_percentage
                        combined_percentage = match_percentage + added_from_shopping

                        if purchased_missing_count >= total_missing_count:
                            combined_percentage = 100.0
                            ingredients_complete = True

                        logger.info(
                            f"  📊 Calcul: base={match_percentage:.1f}% + "
                            f"({purchased_missing_count}/{total_missing_count} × {missing_percentage:.1f}%) = "
                            f"{combined_percentage:.1f}%"
                        )
                    elif shopping_list_status == "completed":
                        combined_percentage = 100.0
                        ingredients_complete = True

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
            feasible_recipes.sort(
                key=lambda x: x["combined_percentage"], reverse=reverse
            )
        elif sort_by == "name":
            feasible_recipes.sort(
                key=lambda x: x["recipe"].title.lower(), reverse=reverse
            )
        elif sort_by == "date":
            feasible_recipes.sort(key=lambda x: x["recipe"].created_at, reverse=reverse)
        elif sort_by == "time":
            feasible_recipes.sort(
                key=lambda x: x["recipe"].preparation_time or 9999, reverse=reverse
            )

        logger.info(
            f" Trouvé {len(feasible_recipes)} recettes (triées par {sort_by} {sort_order})"
        )

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

    def _find_best_inventory_match(
        self, ingredient_name: str, inventory: list
    ) -> int | None:
        from difflib import SequenceMatcher

        ingredient_lower = ingredient_name.lower().strip()
        best_match_id = None
        best_score = 0.0

        for inv_item in inventory:
            inv_name = inv_item["name"].lower().strip()

            if ingredient_lower == inv_name:
                return inv_item["id"]

            if ingredient_lower in inv_name or inv_name in ingredient_lower:
                score = 0.8
                if score > best_score:
                    best_score = score
                    best_match_id = inv_item["id"]
                    continue

            score = SequenceMatcher(None, ingredient_lower, inv_name).ratio()
            if score > best_score and score >= 0.5:
                best_score = score
                best_match_id = inv_item["id"]

        return best_match_id if best_score >= 0.5 else None

    async def suggest_recipe_with_ai(
        self, fridge_id: int, user: User
    ) -> SuggestedRecipeResponse:
        import logging

        logger = logging.getLogger(__name__)

        inventory_items = (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )

        logger.info(f"Found {len(inventory_items)} items in fridge {fridge_id}")

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
                    "unit": item.unit or product.default_unit or "pièce",
                    "category": product.category or "Divers",
                }
                available_ingredients.append(ingredient_info)
                inventory_map[item.product_id] = product
                logger.info(
                    f"  - [{item.product_id}] {product.name}: {item.quantity} {item.unit}"
                )

        if not available_ingredients:
            return SuggestedRecipeResponse(
                title="Inventaire vide",
                description="Votre frigo ne contient aucun ingrédient reconnu.",
                ingredients=[],
                steps="1. Ajoutez des produits à votre inventaire",
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
        cuisine_text = user.preferred_cuisine if user.preferred_cuisine else "Variée"

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
                            "matched_inventory_id": {
                                "type": ["integer", "null"],
                                "description": "L'ID du produit dans l'inventaire si disponible, null sinon",
                            },
                            "matched_inventory_name": {
                                "type": ["string", "null"],
                                "description": "Le nom exact du produit matché dans l'inventaire",
                            },
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
                f"- [ID:{ing['id']}] {ing['name']}: {ing['quantity']} {ing['unit']} ({ing['category']})"
                for ing in available_ingredients
            ]
        )

        prompt = f"""Tu es un chef cuisinier créatif. Suggère UNE recette basée sur les ingrédients disponibles.

    INGRÉDIENTS DISPONIBLES DANS LE FRIGO (avec leurs IDs):
    {ingredients_text}

    PRÉFÉRENCES:
    - Cuisine préférée: {cuisine_text}
    - Restrictions alimentaires: {restrictions_text}

    {self._generate_dietary_restrictions_rules(dietary_restrictions)}

    RÈGLES CRITIQUES POUR LE MAPPING DES INGRÉDIENTS:
    1. Pour chaque ingrédient de ta recette, tu DOIS vérifier s'il correspond à un produit de la liste ci-dessus
    2. Si un ingrédient correspond (même partiellement) à un produit de l'inventaire:
    - is_available: true
    - matched_inventory_id: l'ID entre crochets [ID:X] du produit correspondant
    - matched_inventory_name: le nom EXACT du produit dans l'inventaire
    3. Exemples de correspondances VALIDES:
    - "Lait entier" dans la recette → [ID:5] "Lait" dans l'inventaire → matched_inventory_id: 5
    - "Œufs" dans la recette → [ID:12] "Oeufs" dans l'inventaire → matched_inventory_id: 12
    - "Fromage râpé" dans la recette → [ID:8] "Emmental" dans l'inventaire → matched_inventory_id: 8
    4. Si l'ingrédient n'a PAS de correspondance dans l'inventaire:
    - is_available: false
    - matched_inventory_id: null
    - matched_inventory_name: null

    AUTRES RÈGLES:
    - Tu peux suggérer quelques ingrédients de base manquants (sel, poivre, huile)
    - Temps de préparation en minutes
    - Difficulté: "easy", "medium" ou "hard"
    - Réponds en FRANÇAIS

    Réponds UNIQUEMENT en JSON."""

        try:
            config = types.GenerateContentConfig(
                system_instruction=(
                    "Tu es un chef expert. Pour chaque ingrédient, tu DOIS indiquer "
                    "matched_inventory_id avec l'ID exact du produit de l'inventaire s'il correspond. "
                    "Réponds en français et uniquement en JSON."
                ),
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

            processed_ingredients = []
            available_names = []
            missing_ingredients = []

            inventory_ids = set(inventory_map.keys())

            for ing in data.get("ingredients", []):
                ing_name = ing.get("name", "").strip()
                matched_id = ing.get("matched_inventory_id")
                matched_name = ing.get("matched_inventory_name")
                is_available = ing.get("is_available", False)

                if self._ingredient_violates_restrictions(
                    ing_name, dietary_restrictions
                ):
                    logger.warning(f"Filtering restricted ingredient: {ing_name}")
                    continue

                ing_data = {
                    "name": ing_name,
                    "quantity": ing.get("quantity", 1),
                    "unit": ing.get("unit", ""),
                    "is_available": False,
                    "matched_inventory_id": None,
                    "matched_inventory_name": None,
                }

                if matched_id is not None and matched_id in inventory_ids:
                    ing_data["is_available"] = True
                    ing_data["matched_inventory_id"] = matched_id
                    ing_data["matched_inventory_name"] = (
                        matched_name or inventory_map[matched_id].name
                    )
                    available_names.append(ing_name)
                    logger.info(
                        f"   '{ing_name}' → inventory ID {matched_id} ({ing_data['matched_inventory_name']})"
                    )
                elif is_available:
                    best_match_id = self._find_best_inventory_match(
                        ing_name, available_ingredients
                    )
                    if best_match_id:
                        ing_data["is_available"] = True
                        ing_data["matched_inventory_id"] = best_match_id
                        ing_data["matched_inventory_name"] = inventory_map[
                            best_match_id
                        ].name
                        available_names.append(ing_name)
                        logger.info(
                            f"   '{ing_name}' → fallback match ID {best_match_id}"
                        )
                    else:
                        missing_ingredients.append(
                            {
                                "name": ing_name,
                                "quantity": ing.get("quantity", 1),
                                "unit": ing.get("unit", ""),
                            }
                        )
                        logger.info(
                            f"   '{ing_name}' marqué dispo par IA mais non trouvé"
                        )
                else:
                    missing_ingredients.append(
                        {
                            "name": ing_name,
                            "quantity": ing.get("quantity", 1),
                            "unit": ing.get("unit", ""),
                        }
                    )
                    logger.info(f"   '{ing_name}' manquant")

                processed_ingredients.append(ing_data)

            total = len(processed_ingredients)
            available_count = sum(
                1 for ing in processed_ingredients if ing["is_available"]
            )
            match_percentage = (available_count / total * 100) if total > 0 else 0

            logger.info(
                f"Final match: {available_count}/{total} = {match_percentage:.1f}%"
            )

            return SuggestedRecipeResponse(
                title=data.get("title", "Recette suggérée"),
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
            logger.error(f"Erreur génération recette IA: {e}")
            raise

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

        if "gluten-free" in restrictions_lower or "sans gluten" in restrictions_lower:
            rules.append(
                "- INTERDICTION: blé, farine de blé, pain classique, pâtes de blé, semoule"
            )
            rules.append(
                "- AUTORISÉ: riz, quinoa, maïs, pommes de terre, farine sans gluten"
            )

        if "dairy-free" in restrictions_lower or "sans lactose" in restrictions_lower:
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
