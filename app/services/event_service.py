from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from app.models.event import Event
from app.models.inventory import InventoryItem

logger = logging.getLogger(__name__)


class EventService:
    """
    Service de gestion des événements (CU5)
    Gère l'historique complet des actions
    """

    def __init__(self, db: Session):
        self.db = db

    def create_event(
        self,
        fridge_id: int,
        event_type: str,
        payload: Dict[str, Any],
        inventory_item_id: Optional[int] = None,
    ) -> Event:
        """
        RG5: Crée un nouvel événement

        Types d'événements:
        - ITEM_ADDED
        - ITEM_REMOVED
        - ITEM_CONSUMED
        - ITEM_DETECTED (vision)
        - QUANTITY_UPDATED
        - EXPIRY_UPDATED
        - ALERT_CREATED
        - ALERT_RESOLVED
        """
        event = Event(
            fridge_id=fridge_id,
            inventory_item_id=inventory_item_id,
            type=event_type,
            payload=payload,
        )

        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        logger.debug(f"Event created: {event.type} for fridge {fridge_id}")
        return event

    def get_events(
        self,
        fridge_id: int,
        event_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Event]:
        """CU5: Récupère l'historique des événements avec filtres"""
        query = self.db.query(Event).filter(Event.fridge_id == fridge_id)

        if event_type:
            query = query.filter(Event.type == event_type)

        if start_date:
            query = query.filter(Event.created_at >= start_date)

        if end_date:
            query = query.filter(Event.created_at <= end_date)

        return query.order_by(Event.created_at.desc()).offset(offset).limit(limit).all()

    def get_event_statistics(self, fridge_id: int, days: int = 30) -> Dict[str, Any]:
        """Génère des statistiques sur les événements"""
        from sqlalchemy import func

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Compter par type
        type_counts = (
            self.db.query(Event.type, func.count(Event.id).label("count"))
            .filter(Event.fridge_id == fridge_id, Event.created_at >= cutoff_date)
            .group_by(Event.type)
            .all()
        )

        # Total d'événements
        total = sum(count for _, count in type_counts)

        # Événements par jour (derniers 7 jours)
        week_ago = datetime.utcnow() - timedelta(days=7)
        daily_counts = (
            self.db.query(
                func.date(Event.created_at).label("date"),
                func.count(Event.id).label("count"),
            )
            .filter(Event.fridge_id == fridge_id, Event.created_at >= week_ago)
            .group_by(func.date(Event.created_at))
            .all()
        )

        return {
            "period_days": days,
            "total_events": total,
            "by_type": {event_type: count for event_type, count in type_counts},
            "daily_activity": [
                {"date": str(date), "count": count} for date, count in daily_counts
            ],
        }

    def get_item_history(self, inventory_item_id: int, limit: int = 20) -> List[Event]:
        """Récupère l'historique complet d'un item spécifique"""
        return (
            self.db.query(Event)
            .filter(Event.inventory_item_id == inventory_item_id)
            .order_by(Event.created_at.desc())
            .limit(limit)
            .all()
        )

    def cleanup_old_events(self, days: int = 90) -> int:
        """
        Nettoie les anciens événements pour optimiser la DB

        Returns:
            Nombre d'événements supprimés
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        old_events = self.db.query(Event).filter(Event.created_at < cutoff_date).all()

        count = len(old_events)

        for event in old_events:
            self.db.delete(event)

        self.db.commit()

        logger.info(f"Cleaned up {count} old events")
        return count
