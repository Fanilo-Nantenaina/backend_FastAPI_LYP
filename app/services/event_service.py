from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from app.middleware.transaction_handler import transactional
from app.models.event import Event
from app.models.inventory import InventoryItem
from app.models.product import Product

logger = logging.getLogger(__name__)


class EventService:
    """
    Service de gestion des événements (CU5)
    Gère l'historique complet des actions
    """

    def __init__(self, db: Session):
        self.db = db

    @transactional
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
        """
        Génère des statistiques complètes sur les événements du frigo

        Args:
            fridge_id: ID du frigo
            days: Nombre de jours d'historique (1-365)

        Returns:
            Dictionnaire complet avec toutes les statistiques
        """
        from sqlalchemy import func

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        total_events = (
            self.db.query(func.count(Event.id))
            .filter(Event.fridge_id == fridge_id, Event.created_at >= cutoff_date)
            .scalar()
            or 0
        )

        events_by_type = (
            self.db.query(Event.type, func.count(Event.id).label("count"))
            .filter(Event.fridge_id == fridge_id, Event.created_at >= cutoff_date)
            .group_by(Event.type)
            .all()
        )

        by_type = {event_type: count for event_type, count in events_by_type}

        top_consumed = self._get_top_consumed_products(fridge_id, cutoff_date)

        activity_by_day = self._get_activity_by_day(fridge_id, cutoff_date)

        sources = self._get_source_distribution(fridge_id, cutoff_date)

        daily_activity = self._get_daily_activity(fridge_id, cutoff_date)

        items_added = by_type.get("ITEM_ADDED", 0)
        items_consumed = by_type.get("ITEM_CONSUMED", 0)
        utilization_rate = (
            round((items_consumed / items_added * 100), 1) if items_added > 0 else 0
        )

        return {
            "period_days": days,
            "total_events": total_events,
            "by_type": by_type,
            "top_consumed_products": top_consumed,
            "activity_by_day": activity_by_day,
            "source_distribution": sources,
            "daily_activity": daily_activity,
            "utilization_rate": utilization_rate,
            "items_added": items_added,
            "items_consumed": items_consumed,
        }

    def _get_top_consumed_products(
        self, fridge_id: int, cutoff_date: datetime, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Récupère les produits les plus consommés"""
        consumption_events = (
            self.db.query(Event)
            .filter(
                Event.fridge_id == fridge_id,
                Event.type == "ITEM_CONSUMED",
                Event.created_at >= cutoff_date,
            )
            .all()
        )

        product_consumption = {}
        for event in consumption_events:
            if event.inventory_item_id:
                item = (
                    self.db.query(InventoryItem)
                    .filter(InventoryItem.id == event.inventory_item_id)
                    .first()
                )

                if item:
                    product = (
                        self.db.query(Product)
                        .filter(Product.id == item.product_id)
                        .first()
                    )

                    if product:
                        product_name = product.name
                        qty_consumed = event.payload.get("quantity_consumed", 0)

                        if product_name not in product_consumption:
                            product_consumption[product_name] = {
                                "count": 0,
                                "total_quantity": 0,
                                "unit": item.unit,
                            }

                        product_consumption[product_name]["count"] += 1
                        product_consumption[product_name][
                            "total_quantity"
                        ] += qty_consumed

        top_consumed = sorted(
            product_consumption.items(), key=lambda x: x[1]["count"], reverse=True
        )[:limit]

        return [
            {
                "product_name": name,
                "consumption_count": data["count"],
                "total_quantity": data["total_quantity"],
                "unit": data["unit"],
            }
            for name, data in top_consumed
        ]

    def _get_activity_by_day(
        self, fridge_id: int, cutoff_date: datetime
    ) -> List[Dict[str, Any]]:
        """Récupère l'activité par jour de la semaine"""
        events = (
            self.db.query(Event)
            .filter(Event.fridge_id == fridge_id, Event.created_at >= cutoff_date)
            .all()
        )

        day_activity = {i: 0 for i in range(7)}
        for event in events:
            day = event.created_at.weekday()
            day_activity[day] += 1

        day_names = [
            "Lundi",
            "Mardi",
            "Mercredi",
            "Jeudi",
            "Vendredi",
            "Samedi",
            "Dimanche",
        ]

        return [
            {"day": day_names[i], "count": count} for i, count in day_activity.items()
        ]

    def _get_source_distribution(
        self, fridge_id: int, cutoff_date: datetime
    ) -> Dict[str, int]:
        """Récupère la distribution des sources d'ajout"""
        source_stats = (
            self.db.query(Event.payload)
            .filter(
                Event.fridge_id == fridge_id,
                Event.type == "ITEM_ADDED",
                Event.created_at >= cutoff_date,
            )
            .all()
        )

        sources = {"manual": 0, "vision": 0, "scan": 0, "other": 0}
        for (payload,) in source_stats:
            source = payload.get("source", "other")
            if source in sources:
                sources[source] += 1
            else:
                sources["other"] += 1

        return sources

    def _get_daily_activity(
        self, fridge_id: int, cutoff_date: datetime
    ) -> List[Dict[str, Any]]:
        """Récupère l'activité quotidienne"""
        events = (
            self.db.query(Event)
            .filter(Event.fridge_id == fridge_id, Event.created_at >= cutoff_date)
            .all()
        )

        daily_counts = {}
        for event in events:
            date_str = event.created_at.date().isoformat()
            daily_counts[date_str] = daily_counts.get(date_str, 0) + 1

        return sorted(
            [{"date": date, "count": count} for date, count in daily_counts.items()],
            key=lambda x: x["date"],
        )

    def get_item_history(self, inventory_item_id: int, limit: int = 20) -> List[Event]:
        """Récupère l'historique complet d'un item spécifique"""
        return (
            self.db.query(Event)
            .filter(Event.inventory_item_id == inventory_item_id)
            .order_by(Event.created_at.desc())
            .limit(limit)
            .all()
        )

    @transactional
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
