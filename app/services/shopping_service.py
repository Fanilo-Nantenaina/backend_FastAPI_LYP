from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import logging

from app.middleware.transaction_handler import transactional
from app.models.shopping_list import ShoppingList, ShoppingListItem
from app.models.recipe import RecipeIngredient
from app.models.inventory import InventoryItem
from app.models.product import Product
from app.models.event import Event
from app.models.user import User

logger = logging.getLogger(__name__)


class ShoppingService:
    def __init__(self, db: Session):
        self.db = db

    @transactional
    def generate_shopping_list(
        self,
        user_id: int,
        fridge_id: int,
        name: Optional[str] = None,
        recipe_ids: Optional[List[int]] = None,
        recipe_id: Optional[int] = None,
        include_suggestions: bool = True,
    ) -> ShoppingList:
        logger.info(f"Generating shopping list for fridge {fridge_id}")

        user = self.db.query(User).filter(User.id == user_id).first()
        dietary_restrictions = user.dietary_restrictions if user else []

        shopping_list = ShoppingList(
            user_id=user_id,
            fridge_id=fridge_id,
            generated_by="auto_recipe" if recipe_ids else "ai_suggestion",
            name=name,
            recipe_id=recipe_id,
        )
        self.db.add(shopping_list)
        self.db.flush()

        items_dict = {}

        if recipe_ids:
            recipe_items = self._generate_from_recipes(
                fridge_id, recipe_ids, dietary_restrictions
            )
            for item in recipe_items:
                self._merge_item(items_dict, item)

        if include_suggestions:
            suggestion_items = self._generate_smart_suggestions_with_diversity(
                fridge_id, user_id, dietary_restrictions
            )
            for item in suggestion_items:
                self._merge_item(items_dict, item)

        frequent_items = self._suggest_frequent_missing_items(
            fridge_id, dietary_restrictions
        )
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
            f"Generated shopping list {shopping_list.id} '{shopping_list.name}' "
            f"with {len(items_dict)} items, recipe_id={shopping_list.recipe_id}"
        )

        return shopping_list

    def _merge_item(self, items_dict: Dict, item_data: Dict):
        product_id = item_data["product_id"]

        if product_id in items_dict:
            items_dict[product_id]["quantity"] += item_data["quantity"]
        else:
            items_dict[product_id] = item_data

    def _generate_from_recipes(
        self, fridge_id: int, recipe_ids: List[int], dietary_restrictions: List[str]
    ) -> List[Dict[str, Any]]:
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
                required_products[ingredient.product_id]["quantity"] += (
                    ingredient.quantity
                )
            else:
                required_products[ingredient.product_id] = {
                    "quantity": ingredient.quantity,
                    "unit": ingredient.unit,
                }

        shopping_items = []

        for product_id, required in required_products.items():
            product = self.db.query(Product).filter(Product.id == product_id).first()

            if product and self._product_violates_restrictions(
                product, dietary_restrictions
            ):
                logger.info(
                    f"Skipping product {product.name} "
                    f"(violates dietary restrictions: {product.tags})"
                )
                continue

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

        logger.info(
            f"Generated {len(shopping_items)} items from recipes "
            f"(filtered by dietary restrictions)"
        )
        return shopping_items

    def _generate_smart_suggestions_with_diversity(
        self, fridge_id: int, user_id: int, dietary_restrictions: List[str]
    ) -> List[Dict[str, Any]]:
        logger.info(f"Generating diverse suggestions for fridge {fridge_id}")

        suggestions = []

        consumed_products = self._get_frequently_consumed_products(fridge_id)

        recently_consumed_ids = self._get_recently_consumed_product_ids(
            fridge_id, days=30
        )

        current_inventory = (
            self.db.query(InventoryItem.product_id)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )
        current_product_ids = {item.product_id for item in current_inventory}

        for product_data in consumed_products[:20]:
            product_id = product_data["product_id"]

            if product_id in current_product_ids:
                continue

            product = self.db.query(Product).filter(Product.id == product_id).first()

            if not product:
                continue

            if self._product_violates_restrictions(product, dietary_restrictions):
                logger.info(
                    f"Skipping {product.name} (dietary restriction: {product.tags})"
                )
                continue

            diversity_score = 1.0

            if product_id in recently_consumed_ids:
                diversity_score *= 0.3
                logger.info(
                    f"{product.name} : recently consumed, "
                    f"diversity score = {diversity_score}"
                )
            else:
                diversity_score *= 1.5
                logger.info(
                    f"{product.name} : NOT recently consumed, diversity bonus applied"
                )

            final_score = product_data.get("frequency", 0) * diversity_score

            avg_quantity = product_data.get("avg_quantity", 1.0)

            suggestions.append(
                {
                    "product_id": product.id,
                    "quantity": round(avg_quantity, 2),
                    "unit": product.default_unit,
                    "reason": "diverse_suggestion",
                    "priority_score": final_score,
                }
            )

        suggestions.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

        suggestions = suggestions[:10]

        logger.info(
            f"Generated {len(suggestions)} diverse suggestions (prioritizing variety)"
        )

        return suggestions

    def _get_recently_consumed_product_ids(self, fridge_id: int, days: int = 30) -> set:
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        recent_events = (
            self.db.query(Event)
            .filter(
                Event.fridge_id == fridge_id,
                Event.type.in_(["ITEM_CONSUMED", "ITEM_REMOVED"]),
                Event.created_at >= cutoff_date,
            )
            .all()
        )

        consumed_product_ids = set()

        for event in recent_events:
            if event.inventory_item_id:
                item = (
                    self.db.query(InventoryItem)
                    .filter(InventoryItem.id == event.inventory_item_id)
                    .first()
                )
                if item:
                    consumed_product_ids.add(item.product_id)

        logger.info(
            f"Found {len(consumed_product_ids)} products consumed in last {days} days"
        )

        return consumed_product_ids

    def _get_frequently_consumed_products(
        self, fridge_id: int, days: int = 90
    ) -> List[Dict[str, Any]]:
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

    def _suggest_frequent_missing_items(
        self, fridge_id: int, dietary_restrictions: List[str]
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import Integer, cast, Text

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
                    if self._product_violates_restrictions(
                        product, dietary_restrictions
                    ):
                        continue

                    suggestions.append(
                        {
                            "product_id": product.id,
                            "quantity": 1.0,
                            "unit": product.default_unit,
                            "reason": "frequently_purchased",
                        }
                    )

        return suggestions

    def _product_violates_restrictions(
        self, product: Product, dietary_restrictions: List[str]
    ) -> bool:
        if not dietary_restrictions or not product.tags:
            return False

        normalized_restrictions = [
            r.lower().strip().replace("-", "").replace("_", "")
            for r in dietary_restrictions
        ]

        normalized_tags = [
            t.lower().strip().replace("-", "").replace("_", "") for t in product.tags
        ]

        for restriction in normalized_restrictions:
            if restriction in normalized_tags:
                return True

        return False

    @transactional
    def add_item_to_list(
        self, shopping_list_id: int, product_id: int, quantity: float, unit: str
    ) -> ShoppingListItem:
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
        original = self.db.query(Product).filter(Product.id == product_id).first()

        if not original:
            return []

        query = self.db.query(Product).filter(
            Product.id != product_id, Product.category == original.category
        )

        alternatives = query.limit(limit).all()
        return alternatives

    def get_shopping_statistics(self, user_id: int, days: int = 30) -> Dict[str, Any]:
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
