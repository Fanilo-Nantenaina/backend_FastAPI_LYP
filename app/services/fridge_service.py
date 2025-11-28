from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from app.middleware.transaction_handler import transactional
from app.models.fridge import Fridge
from app.models.inventory import InventoryItem
from app.models.alert import Alert
from app.models.event import Event

logger = logging.getLogger(__name__)


class FridgeService:
    """Service de gestion des réfrigérateurs"""

    def __init__(self, db: Session):
        self.db = db

    @transactional
    def create_fridge(
        self,
        user_id: int,
        name: str,
        location: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Fridge:
        """RG1: Crée un nouveau frigo pour un utilisateur"""
        fridge = Fridge(
            user_id=user_id,
            name=name,
            location=location,
            config=config
            or {
                "expiry_warning_days": 3,
                "lost_item_threshold_hours": 72,
                "low_stock_threshold": 2.0,
            },
        )

        self.db.add(fridge)
        # self.db.commit()
        self.db.refresh(fridge)

        logger.info(f"Fridge created: {fridge.id} for user {user_id}")
        return fridge

    def get_fridge_by_id(
        self, fridge_id: int, user_id: Optional[int] = None
    ) -> Optional[Fridge]:
        """
        Récupère un frigo par son ID

        Args:
            fridge_id: ID du frigo
            user_id: Si fourni, vérifie que le frigo appartient à cet utilisateur (RG2)
        """
        query = self.db.query(Fridge).filter(Fridge.id == fridge_id)

        if user_id:
            query = query.filter(Fridge.user_id == user_id)

        return query.first()

    def get_user_fridges(self, user_id: int) -> List[Fridge]:
        """RG1: Récupère tous les frigos d'un utilisateur"""
        return self.db.query(Fridge).filter(Fridge.user_id == user_id).all()

    @transactional
    def update_fridge(
        self,
        fridge_id: int,
        user_id: int,
        name: Optional[str] = None,
        location: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Optional[Fridge]:
        """Met à jour un frigo (RG2: vérifie la propriété)"""
        fridge = self.get_fridge_by_id(fridge_id, user_id)

        if not fridge:
            return None

        if name is not None:
            fridge.name = name

        if location is not None:
            fridge.location = location

        if config is not None:
            current_config = fridge.config or {}
            current_config.update(config)
            fridge.config = current_config

        # self.db.commit()
        self.db.refresh(fridge)

        logger.info(f"Fridge updated: {fridge_id}")
        return fridge

    @transactional
    def delete_fridge(self, fridge_id: int, user_id: int) -> bool:
        """
        Supprime un frigo (RG2: vérifie la propriété)

        Note: Cascade supprime automatiquement inventory, events, alerts
        """
        fridge = self.get_fridge_by_id(fridge_id, user_id)

        if not fridge:
            return False

        self.db.delete(fridge)
        # self.db.commit()

        logger.info(f"Fridge deleted: {fridge_id}")
        return True

    def get_fridge_statistics(self, fridge_id: int) -> Dict[str, Any]:
        """Génère des statistiques complètes sur un frigo"""
        fridge = self.get_fridge_by_id(fridge_id)

        if not fridge:
            return {}

        active_items = (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .count()
        )

        pending_alerts = (
            self.db.query(Alert)
            .filter(Alert.fridge_id == fridge_id, Alert.status == "pending")
            .count()
        )

        from datetime import timedelta

        month_ago = datetime.utcnow() - timedelta(days=30)
        recent_events = (
            self.db.query(Event)
            .filter(Event.fridge_id == fridge_id, Event.created_at >= month_ago)
            .count()
        )

        total_value = 0
        items = (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )

        for item in items:
            if item.metadata and "price" in item.metadata:
                total_value += item.metadata["price"] * item.quantity

        return {
            "fridge_id": fridge_id,
            "name": fridge.name,
            "active_items": active_items,
            "pending_alerts": pending_alerts,
            "recent_events": recent_events,
            "estimated_value": round(total_value, 2),
            "created_at": fridge.created_at.isoformat(),
        }

    def get_fridge_summary(self, fridge_id: int) -> Dict[str, Any]:
        """Résumé rapide d'un frigo pour l'affichage"""
        stats = self.get_fridge_statistics(fridge_id)

        critical_alerts = (
            self.db.query(Alert)
            .filter(
                Alert.fridge_id == fridge_id,
                Alert.status == "pending",
                Alert.type.in_(["EXPIRED", "EXPIRY_SOON"]),
            )
            .count()
        )

        stats["critical_alerts"] = critical_alerts

        return stats
