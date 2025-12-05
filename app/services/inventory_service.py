from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta
import logging

from app.middleware.transaction_handler import transactional
from app.models.inventory import InventoryItem
from app.models.product import Product
from app.models.event import Event
from app.models.alert import Alert  # ✅ AJOUT

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
        ✅ NOUVEAU: Met à jour automatiquement les alertes concernées
        """
        item = self.db.query(InventoryItem).filter(InventoryItem.id == item_id).first()

        if not item:
            return None

        if new_quantity < 0:
            raise ValueError("Quantity cannot be negative (RG9)")

        old_quantity = item.quantity
        item.quantity = new_quantity

        # ✅ NOUVEAU: Mettre à jour les alertes associées
        self._update_related_alerts(item, old_quantity, new_quantity)

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
        ✅ NOUVEAU: Met à jour automatiquement les alertes concernées
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

        old_quantity = item.quantity

        # RG8: Définir open_date si consommation partielle
        if new_quantity > 0 and not item.open_date:
            item.open_date = date.today()
            logger.info(f"Open date set for item {item_id} (RG8)")

        item.quantity = new_quantity

        # ✅ NOUVEAU: Mettre à jour les alertes associées
        self._update_related_alerts(item, old_quantity, new_quantity)

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

        logger.info(f"✅ Item consumed: {item_id} - {quantity_consumed} {item.unit}")
        return item

    def _update_related_alerts(
        self, item: InventoryItem, old_quantity: float, new_quantity: float
    ):
        """
        ✅ NOUVEAU: Met à jour automatiquement les alertes non résolues concernant cet item

        Logique:
        - Si quantité = 0 : résoudre toutes les alertes
        - Si quantité réduite : mettre à jour le message avec la nouvelle quantité
        - Si quantité augmentée : vérifier si l'alerte est encore pertinente
        """
        # Récupérer toutes les alertes non résolues pour cet item
        pending_alerts = (
            self.db.query(Alert)
            .filter(Alert.inventory_item_id == item.id, Alert.status == "pending")
            .all()
        )

        if not pending_alerts:
            logger.info(f"No pending alerts found for item {item.id}")
            return

        product = self.db.query(Product).filter(Product.id == item.product_id).first()
        product_name = product.name if product else f"Produit #{item.product_id}"

        for alert in pending_alerts:
            if new_quantity == 0:
                # ✅ CAS 1: Produit complètement consommé → résoudre l'alerte
                alert.status = "resolved"
                alert.resolved_at = datetime.utcnow()

                logger.info(
                    f"✅ Alert {alert.id} auto-resolved: product fully consumed"
                )

                # Créer un événement
                event = Event(
                    fridge_id=item.fridge_id,
                    inventory_item_id=item.id,
                    type="ALERT_AUTO_RESOLVED",
                    payload={
                        "alert_id": alert.id,
                        "alert_type": alert.type,
                        "reason": "product_consumed",
                        "old_quantity": old_quantity,
                        "new_quantity": 0,
                    },
                )
                self.db.add(event)

            elif alert.type in ["EXPIRY_SOON", "EXPIRED"]:
                # ✅ CAS 2: Alerte d'expiration → mettre à jour le message avec la nouvelle quantité
                alert.message = self._generate_updated_expiry_message(
                    product_name=product_name,
                    expiry_date=item.expiry_date,
                    quantity=new_quantity,
                    unit=item.unit,
                    alert_type=alert.type,
                )

                logger.info(
                    f"📝 Alert {alert.id} message updated: "
                    f"{old_quantity} → {new_quantity} {item.unit}"
                )

            elif alert.type == "LOW_STOCK":
                # ✅ CAS 3: Alerte de stock faible
                # Si la quantité augmente et dépasse le seuil, résoudre
                min_quantity = (
                    product.extra_data.get("min_quantity")
                    if product and product.extra_data
                    else None
                )

                if min_quantity and new_quantity > min_quantity:
                    alert.status = "resolved"
                    alert.resolved_at = datetime.utcnow()
                    logger.info(f"✅ Alert {alert.id} auto-resolved: stock replenished")
                else:
                    # Sinon, mettre à jour le message
                    alert.message = (
                        f"📉 Stock faible pour {product_name}. "
                        f"Quantité actuelle : {new_quantity} {item.unit}. "
                        f"Pensez à en racheter."
                    )

    def _generate_updated_expiry_message(
        self,
        product_name: str,
        expiry_date: Optional[date],
        quantity: float,
        unit: str,
        alert_type: str,
    ) -> str:
        """
        ✅ NOUVEAU: Génère un message d'alerte mis à jour avec la nouvelle quantité
        """
        if not expiry_date:
            return f"Le produit {product_name} nécessite une attention."

        days_until_expiry = (expiry_date - date.today()).days

        if days_until_expiry < 0:
            # Produit expiré
            days_expired = abs(days_until_expiry)
            return (
                f"🚫 {product_name} a expiré il y a {days_expired} jour(s). "
                f"Quantité restante : {quantity} {unit}. "
                f"À retirer immédiatement du réfrigérateur."
            )
        elif days_until_expiry == 0:
            # Expire aujourd'hui
            return (
                f"⚠️ {product_name} expire AUJOURD'HUI ! "
                f"Quantité : {quantity} {unit}. "
                f"À consommer rapidement."
            )
        else:
            # Expire bientôt
            return (
                f"⏰ {product_name} expire dans {days_until_expiry} jour(s) "
                f"({expiry_date.strftime('%d/%m/%Y')}). "
                f"Quantité : {quantity} {unit}."
            )

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

        # ✅ NOUVEAU: Résoudre automatiquement toutes les alertes associées
        pending_alerts = (
            self.db.query(Alert)
            .filter(Alert.inventory_item_id == item_id, Alert.status == "pending")
            .all()
        )

        for alert in pending_alerts:
            alert.status = "resolved"
            alert.resolved_at = datetime.utcnow()
            logger.info(f"✅ Alert {alert.id} auto-resolved: item deleted")

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
