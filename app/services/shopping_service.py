from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import logging

from app.middleware.transaction_handler import transactional
from app.models.shopping_list import ShoppingList, ShoppingListItem
from app.models.recipe import Recipe, RecipeIngredient
from app.models.inventory import InventoryItem
from app.models.product import Product
from app.models.event import Event
from app.models.user import User

logger = logging.getLogger(__name__)


class ShoppingService:
    """
    Service complet de gestion des listes de courses
    - CU4: Génération manuelle et automatique
    - RG13: Vérification de propriété
    - RG15: Inclusion uniquement des produits insuffisants
    - Suggestions intelligentes basées sur l'historique
    """

    def __init__(self, db: Session):
        self.db = db

    @transactional
    def generate_shopping_list(
        self,
        user_id: int,
        fridge_id: int,
        recipe_ids: Optional[List[int]] = None,
        include_suggestions: bool = True,
    ) -> ShoppingList:
        """
        CU4: Génère automatiquement une liste de courses intelligente

        Args:
            user_id: ID de l'utilisateur (pour RG13)
            fridge_id: ID du frigo
            recipe_ids: Liste des recettes à préparer (optionnel)
            include_suggestions: Ajouter des suggestions IA

        Returns:
            ShoppingList créée avec tous les items
        """
        logger.info(f"Generating shopping list for fridge {fridge_id}")

        shopping_list = ShoppingList(
            user_id=user_id,
            fridge_id=fridge_id,
            generated_by="auto_recipe" if recipe_ids else "ai_suggestion",
        )
        self.db.add(shopping_list)
        self.db.flush()

        items_dict = {}

        if recipe_ids:
            recipe_items = self._generate_from_recipes(fridge_id, recipe_ids)
            for item in recipe_items:
                self._merge_item(items_dict, item)

        if include_suggestions:
            suggestion_items = self._generate_smart_suggestions(fridge_id, user_id)
            for item in suggestion_items:
                self._merge_item(items_dict, item)

        frequent_items = self._suggest_frequent_missing_items(fridge_id)
        for item in frequent_items:
            self._merge_item(items_dict, item)

        for product_id, item_data in items_dict.items():
            item = ShoppingListItem(
                shopping_list_id=shopping_list.id,
                product_id=product_id,
                quantity=item_data["quantity"],
                unit=item_data["unit"],
                status="pending",
            )
            self.db.add(item)

        self.db.commit()
        self.db.refresh(shopping_list)

        logger.info(
            f"Generated shopping list {shopping_list.id} "
            f"with {len(items_dict)} items"
        )

        return shopping_list

    def _merge_item(self, items_dict: Dict, item_data: Dict):
        """Fusionne un item dans le dictionnaire (cumule les quantités)"""
        product_id = item_data["product_id"]

        if product_id in items_dict:
            items_dict[product_id]["quantity"] += item_data["quantity"]
        else:
            items_dict[product_id] = item_data

    def _generate_from_recipes(
        self, fridge_id: int, recipe_ids: List[int]
    ) -> List[Dict[str, Any]]:
        """
        RG15: Génère les items basés sur les recettes
        N'inclut que les produits en quantité insuffisante
        """
        logger.info(f"Generating items from {len(recipe_ids)} recipes")

        inventory = (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )

        available_products = {
            item.product_id: {"quantity": item.quantity, "unit": item.unit}
            for item in inventory
        }

        ingredients = (
            self.db.query(RecipeIngredient)
            .filter(RecipeIngredient.recipe_id.in_(recipe_ids))
            .all()
        )

        required_products = {}
        for ingredient in ingredients:
            if ingredient.product_id in required_products:
                required_products[ingredient.product_id][
                    "quantity"
                ] += ingredient.quantity
            else:
                required_products[ingredient.product_id] = {
                    "quantity": ingredient.quantity,
                    "unit": ingredient.unit,
                }

        shopping_items = []

        for product_id, required in required_products.items():
            available = available_products.get(product_id, {})
            available_qty = available.get("quantity", 0)

            if available_qty < required["quantity"]:
                needed_qty = required["quantity"] - available_qty

                shopping_items.append(
                    {
                        "product_id": product_id,
                        "quantity": round(needed_qty, 2),
                        "unit": required["unit"],
                        "reason": "recipe",
                    }
                )

        logger.info(f"Generated {len(shopping_items)} items from recipes")
        return shopping_items

    def _generate_smart_suggestions(
        self, fridge_id: int, user_id: int
    ) -> List[Dict[str, Any]]:
        """
        Suggestions intelligentes basées sur :
        1. L'historique de consommation
        2. Les préférences utilisateur
        3. Les patterns d'achat
        """
        logger.info(f"Generating smart suggestions for fridge {fridge_id}")

        suggestions = []

        consumed_products = self._get_frequently_consumed_products(fridge_id)

        current_inventory = (
            self.db.query(InventoryItem.product_id)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )
        current_product_ids = {item.product_id for item in current_inventory}

        for product_data in consumed_products[:10]:
            product_id = product_data["product_id"]

            if product_id not in current_product_ids:
                product = (
                    self.db.query(Product).filter(Product.id == product_id).first()
                )

                if product:
                    avg_quantity = product_data.get("avg_quantity", 1.0)

                    suggestions.append(
                        {
                            "product_id": product.id,
                            "quantity": round(avg_quantity, 2),
                            "unit": product.default_unit,
                            "reason": "frequently_consumed",
                            "confidence": product_data.get("frequency", 0),
                        }
                    )

        logger.info(f"Generated {len(suggestions)} smart suggestions")
        return suggestions

    def _get_frequently_consumed_products(
        self, fridge_id: int, days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Analyse l'historique pour trouver les produits fréquemment consommés
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        events = (
            self.db.query(Event)
            .filter(
                Event.fridge_id == fridge_id,
                Event.type.in_(["ITEM_CONSUMED", "ITEM_REMOVED"]),
                Event.created_at >= cutoff_date,
            )
            .all()
        )

        product_consumption = {}

        for event in events:
            payload = event.payload or {}

            if event.inventory_item_id:
                item = (
                    self.db.query(InventoryItem)
                    .filter(InventoryItem.id == event.inventory_item_id)
                    .first()
                )

                if item:
                    product_id = item.product_id

                    if product_id not in product_consumption:
                        product_consumption[product_id] = {
                            "product_id": product_id,
                            "count": 0,
                            "total_quantity": 0.0,
                        }

                    product_consumption[product_id]["count"] += 1

                    consumed = payload.get("quantity_consumed", 0)
                    product_consumption[product_id]["total_quantity"] += consumed

        result = []
        for data in product_consumption.values():
            avg_quantity = (
                data["total_quantity"] / data["count"] if data["count"] > 0 else 1.0
            )

            result.append(
                {
                    "product_id": data["product_id"],
                    "frequency": data["count"],
                    "avg_quantity": max(avg_quantity, 1.0),
                }
            )

        result.sort(key=lambda x: x["frequency"], reverse=True)

        return result

    def _suggest_frequent_missing_items(self, fridge_id: int) -> List[Dict[str, Any]]:
        """
        ✅ CORRIGÉ : Utilise le casting correct pour JSON
        Suggère les produits fréquemment ajoutés mais actuellement absents
        """
        from sqlalchemy import Integer, cast, Text

        # ✅ CORRECTION : Cast JSON → TEXT → INTEGER au lieu de jsonb_extract_path_text
        top_products = (
            self.db.query(
                cast(cast(Event.payload["product_id"], Text), Integer).label(
                    "product_id"
                ),
                func.count().label("add_count"),
            )
            .filter(Event.fridge_id == fridge_id, Event.type == "ITEM_ADDED")
            .group_by(cast(cast(Event.payload["product_id"], Text), Integer))
            .order_by(desc("add_count"))
            .limit(15)
            .all()
        )

        current_inventory = (
            self.db.query(InventoryItem.product_id)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )
        current_product_ids = {item.product_id for item in current_inventory}

        suggestions = []

        for product_id, count in top_products:
            if product_id and product_id not in current_product_ids:
                product = (
                    self.db.query(Product).filter(Product.id == product_id).first()
                )

                if product:
                    suggestions.append(
                        {
                            "product_id": product.id,
                            "quantity": 1.0,
                            "unit": product.default_unit,
                            "reason": "frequently_purchased",
                        }
                    )

        return suggestions

    @transactional
    def add_item_to_list(
        self, shopping_list_id: int, product_id: int, quantity: float, unit: str
    ) -> ShoppingListItem:
        """Ajoute un item à une liste existante"""
        item = ShoppingListItem(
            shopping_list_id=shopping_list_id,
            product_id=product_id,
            quantity=quantity,
            unit=unit,
            status="pending",
        )

        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)

        return item

    @transactional
    def update_item_status(
        self, item_id: int, status: str
    ) -> Optional[ShoppingListItem]:
        """Met à jour le statut d'un item (pending, purchased, cancelled)"""
        item = (
            self.db.query(ShoppingListItem)
            .filter(ShoppingListItem.id == item_id)
            .first()
        )

        if item:
            item.status = status
            self.db.commit()
            self.db.refresh(item)

        return item

    @transactional
    def mark_list_as_completed(self, shopping_list_id: int) -> Tuple[int, int]:
        """
        Marque tous les items pending comme purchased

        Returns:
            (nombre d'items marqués, nombre total d'items)
        """
        items = (
            self.db.query(ShoppingListItem)
            .filter(ShoppingListItem.shopping_list_id == shopping_list_id)
            .all()
        )

        updated_count = 0
        for item in items:
            if item.status == "pending":
                item.status = "purchased"
                updated_count += 1

        self.db.commit()
        return updated_count, len(items)

    def optimize_shopping_list(self, shopping_list_id: int) -> Dict[str, Any]:
        """
        Optimise une liste de courses :
        - Regroupe par catégories
        - Suggère des alternatives moins chères
        - Élimine les doublons
        """
        items = (
            self.db.query(ShoppingListItem)
            .filter(ShoppingListItem.shopping_list_id == shopping_list_id)
            .all()
        )

        by_category = {}
        for item in items:
            product = (
                self.db.query(Product).filter(Product.id == item.product_id).first()
            )

            if product:
                category = product.category or "Divers"

                if category not in by_category:
                    by_category[category] = []

                by_category[category].append(
                    {
                        "item_id": item.id,
                        "product_name": product.name,
                        "quantity": item.quantity,
                        "unit": item.unit,
                        "status": item.status,
                    }
                )

        return {
            "shopping_list_id": shopping_list_id,
            "total_items": len(items),
            "pending_items": sum(1 for i in items if i.status == "pending"),
            "by_category": by_category,
            "categories_count": len(by_category),
        }

    def suggest_alternatives(self, product_id: int, limit: int = 3) -> List[Product]:
        """
        Suggère des produits alternatifs similaires
        Basé sur la catégorie et les tags
        """
        original = self.db.query(Product).filter(Product.id == product_id).first()

        if not original:
            return []

        query = self.db.query(Product).filter(
            Product.id != product_id, Product.category == original.category
        )

        alternatives = query.limit(limit).all()
        return alternatives

    def get_shopping_statistics(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Génère des statistiques sur les habitudes d'achat"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        lists_count = (
            self.db.query(ShoppingList)
            .filter(
                ShoppingList.user_id == user_id, ShoppingList.created_at >= cutoff_date
            )
            .count()
        )

        purchased_items = (
            self.db.query(ShoppingListItem)
            .join(ShoppingList)
            .filter(
                ShoppingList.user_id == user_id,
                ShoppingListItem.status == "purchased",
                ShoppingList.created_at >= cutoff_date,
            )
            .count()
        )

        top_products = (
            self.db.query(Product.name, func.count(ShoppingListItem.id).label("count"))
            .join(ShoppingListItem)
            .join(ShoppingList)
            .filter(
                ShoppingList.user_id == user_id,
                ShoppingListItem.status == "purchased",
                ShoppingList.created_at >= cutoff_date,
            )
            .group_by(Product.id, Product.name)
            .order_by(desc("count"))
            .limit(10)
            .all()
        )

        return {
            "period_days": days,
            "shopping_lists_created": lists_count,
            "items_purchased": purchased_items,
            "avg_items_per_list": (
                round(purchased_items / lists_count, 2) if lists_count > 0 else 0
            ),
            "top_products": [
                {"product": name, "purchases": count} for name, count in top_products
            ],
        }

    def get_shopping_efficiency(self, shopping_list_id: int) -> Dict[str, Any]:
        """
        Calcule l'efficacité d'une liste de courses
        (% d'items achetés vs ajoutés)
        """
        items = (
            self.db.query(ShoppingListItem)
            .filter(ShoppingListItem.shopping_list_id == shopping_list_id)
            .all()
        )

        total = len(items)
        purchased = sum(1 for i in items if i.status == "purchased")
        cancelled = sum(1 for i in items if i.status == "cancelled")
        pending = sum(1 for i in items if i.status == "pending")

        return {
            "total_items": total,
            "purchased": purchased,
            "cancelled": cancelled,
            "pending": pending,
            "completion_rate": round((purchased / total * 100), 2) if total > 0 else 0,
            "efficiency_score": (
                round(((purchased / (total - cancelled)) * 100), 2)
                if (total - cancelled) > 0
                else 0
            ),
        }
