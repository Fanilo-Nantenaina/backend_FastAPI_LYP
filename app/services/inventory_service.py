from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta
import logging

from app.middleware.transaction_handler import transactional
from app.models.inventory import InventoryItem
from app.models.product import Product
from app.models.event import Event

logger = logging.getLogger(__name__)


class InventoryService:
    """
    Service de gestion de l'inventaire
    Gère les règles RG6-RG9
    """

    def __init__(self, db: Session):
        self.db = db

    @transactional
    def add_item(
        self,
        fridge_id: int,
        product_id: int,
        quantity: float,
        unit: Optional[str] = None,
        expiry_date: Optional[date] = None,
        source: str = "manual",
    ) -> InventoryItem:
        """
        RG4: Ajoute un item à l'inventaire

        Args:
            source: 'manual', 'vision', 'barcode'
        """
        product = self.db.query(Product).filter(Product.id == product_id).first()

        if not product:
            raise ValueError(f"Product {product_id} not found")

        if not unit:
            unit = product.default_unit

        if not expiry_date and product.shelf_life_days:
            expiry_date = date.today() + timedelta(days=product.shelf_life_days)

        item = InventoryItem(
            fridge_id=fridge_id,
            product_id=product_id,
            quantity=quantity,
            initial_quantity=quantity,
            unit=unit,
            expiry_date=expiry_date,
            source=source,
            last_seen_at=datetime.utcnow(),
        )

        self.db.add(item)
        self.db.flush()

        event = Event(
            fridge_id=fridge_id,
            inventory_item_id=item.id,
            type="ITEM_ADDED",
            payload={
                "product_id": product_id,
                "product_name": product.name,
                "quantity": quantity,
                "unit": unit,
                "source": source,
            },
        )
        self.db.add(event)

        self.db.commit()
        self.db.refresh(item)

        logger.info(f"Item added to inventory: {item.id} - {product.name}")
        return item

    @transactional
    def update_quantity(
        self, item_id: int, new_quantity: float, reason: str = "manual_update"
    ) -> Optional[InventoryItem]:
        """
        Met à jour la quantité d'un item
        RG9: La quantité ne peut être négative
        """
        item = self.db.query(InventoryItem).filter(InventoryItem.id == item_id).first()

        if not item:
            return None

        if new_quantity < 0:
            raise ValueError("Quantity cannot be negative (RG9)")

        old_quantity = item.quantity
        item.quantity = new_quantity

        event = Event(
            fridge_id=item.fridge_id,
            inventory_item_id=item.id,
            type="QUANTITY_UPDATED",
            payload={
                "old_quantity": old_quantity,
                "new_quantity": new_quantity,
                "reason": reason,
            },
        )
        self.db.add(event)

        self.db.commit()
        self.db.refresh(item)

        return item

    def consume_item(
        self, item_id: int, quantity_consumed: float
    ) -> Optional[InventoryItem]:
        """
        CU3: Déclare une consommation
        RG8: Définit open_date si consommation partielle
        RG9: Vérifie que la quantité reste positive
        """
        item = self.db.query(InventoryItem).filter(InventoryItem.id == item_id).first()

        if not item:
            return None

        new_quantity = item.quantity - quantity_consumed
        if new_quantity < 0:
            raise ValueError(
                f"Cannot consume {quantity_consumed} {item.unit}. "
                f"Only {item.quantity} {item.unit} available (RG9)"
            )

        if new_quantity > 0 and not item.open_date:
            item.open_date = date.today()
            logger.info(f"Open date set for item {item_id} (RG8)")

        item.quantity = new_quantity

        event = Event(
            fridge_id=item.fridge_id,
            inventory_item_id=item.id,
            type="ITEM_CONSUMED",
            payload={
                "quantity_consumed": quantity_consumed,
                "unit": item.unit,
                "remaining": new_quantity,
                "open_date_set": item.open_date.isoformat() if item.open_date else None,
            },
        )
        self.db.add(event)

        self.db.commit()
        self.db.refresh(item)

        logger.info(f"Item consumed: {item_id} - {quantity_consumed} {item.unit}")
        return item

    def update_last_seen(
        self, item_id: int, seen_at: Optional[datetime] = None
    ) -> Optional[InventoryItem]:
        """RG7: Met à jour last_seen_at (pour le système de vision)"""
        item = self.db.query(InventoryItem).filter(InventoryItem.id == item_id).first()

        if not item:
            return None

        item.last_seen_at = seen_at or datetime.utcnow()
        self.db.commit()
        self.db.refresh(item)

        return item

    def get_active_items(self, fridge_id: int) -> List[InventoryItem]:
        """RG6: Récupère les items actifs (quantité > 0)"""
        return (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )

    def get_expiring_items(self, fridge_id: int, days: int = 3) -> List[InventoryItem]:
        """Récupère les items qui expirent dans X jours"""
        expiry_threshold = date.today() + timedelta(days=days)

        return (
            self.db.query(InventoryItem)
            .filter(
                InventoryItem.fridge_id == fridge_id,
                InventoryItem.quantity > 0,
                InventoryItem.expiry_date <= expiry_threshold,
                InventoryItem.expiry_date >= date.today(),
            )
            .all()
        )

    def get_expired_items(self, fridge_id: int) -> List[InventoryItem]:
        """Récupère les items expirés"""
        return (
            self.db.query(InventoryItem)
            .filter(
                InventoryItem.fridge_id == fridge_id,
                InventoryItem.quantity > 0,
                InventoryItem.expiry_date < date.today(),
            )
            .all()
        )

    def remove_item(self, item_id: int, reason: str = "user_delete") -> bool:
        """Supprime complètement un item de l'inventaire"""
        item = self.db.query(InventoryItem).filter(InventoryItem.id == item_id).first()

        if not item:
            return False

        event = Event(
            fridge_id=item.fridge_id,
            inventory_item_id=item.id,
            type="ITEM_REMOVED",
            payload={
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit": item.unit,
                "reason": reason,
            },
        )
        self.db.add(event)

        self.db.delete(item)
        self.db.commit()

        logger.info(f"Item removed: {item_id} - {reason}")
        return True
