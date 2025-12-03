from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional, Dict, Any
import logging

from app.middleware.transaction_handler import transactional
from app.models.alert import Alert
from app.models.inventory import InventoryItem
from app.models.fridge import Fridge
from app.models.user import User
from app.core.config import settings
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class AlertService:
    """
    Service complet de gestion des alertes
    - CU7: Vérification automatique périodique
    - CU8: Gestion du statut des alertes
    - RG10, RG11, RG12: Règles de génération des alertes
    """

    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)

    def check_and_create_alerts(
        self, fridge_id: Optional[int] = None, send_notifications: bool = True
    ) -> Dict[str, int]:
        """
        CU7: Vérifie l'inventaire et crée les alertes nécessaires

        Cette méthode est appelée automatiquement par le scheduler
        toutes les heures pour tous les frigos.

        Returns:
            Dict avec le nombre d'alertes créées par type
        """
        stats = {
            "EXPIRY_SOON": 0,
            "EXPIRED": 0,
            "LOST_ITEM": 0,
            "LOW_STOCK": 0,
            "total_notified": 0,
        }

        query = self.db.query(Fridge)
        if fridge_id:
            query = query.filter(Fridge.id == fridge_id)

        fridges = query.all()
        logger.info(f"Checking alerts for {len(fridges)} fridge(s)")

        for fridge in fridges:
            config = fridge.config or {}
            expiry_days = config.get(
                "expiry_warning_days", settings.EXPIRY_WARNING_DAYS
            )
            lost_hours = config.get(
                "lost_item_threshold_hours", settings.LOST_ITEM_HOURS
            )
            low_stock_threshold = config.get("low_stock_threshold", 2.0)

            user = fridge.user

            items = (
                self.db.query(InventoryItem)
                .filter(
                    InventoryItem.fridge_id == fridge.id, InventoryItem.quantity > 0
                )
                .all()
            )

            logger.info(f"Checking {len(items)} items in fridge {fridge.id}")

            new_alerts = []

            for item in items:
                expiry_alert = self._check_expiry_alert(item, fridge.id, expiry_days)
                if expiry_alert:
                    new_alerts.append(expiry_alert)
                    stats[expiry_alert.type] += 1

                lost_alert = self._check_lost_item_alert(item, fridge.id, lost_hours)
                if lost_alert:
                    new_alerts.append(lost_alert)
                    stats["LOST_ITEM"] += 1

                stock_alert = self._check_low_stock_alert(
                    item, fridge.id, low_stock_threshold
                )
                if stock_alert:
                    new_alerts.append(stock_alert)
                    stats["LOW_STOCK"] += 1

            if send_notifications and new_alerts and user:
                self._send_alert_notifications(new_alerts, user)
                stats["total_notified"] += len(new_alerts)

        logger.info(f"Alert check completed. Stats: {stats}")
        return stats

    def _check_expiry_alert(
        self, item: InventoryItem, fridge_id: int, warning_days: int
    ) -> Optional[Alert]:
        """
        RG10: Crée une alerte si le produit approche de sa date de péremption
        ou si elle est dépassée
        """
        if not item.expiry_date:
            return None

        days_until_expiry = (item.expiry_date - date.today()).days

        alert_type = None
        message = None
        priority = "normal"

        if days_until_expiry < 0:
            alert_type = "EXPIRED"
            message = (
                f"🚫 {item.product.name} a expiré il y a {abs(days_until_expiry)} jour(s). "
                f"Quantité : {item.quantity} {item.unit}. "
                f"À retirer immédiatement du réfrigérateur."
            )
            priority = "high"
        elif days_until_expiry == 0:
            alert_type = "EXPIRY_SOON"
            message = (
                f"⚠️ {item.product.name} expire AUJOURD'HUI ! "
                f"Quantité : {item.quantity} {item.unit}. "
                f"À consommer rapidement."
            )
            priority = "high"
        elif days_until_expiry <= warning_days:
            alert_type = "EXPIRY_SOON"
            message = (
                f"⏰ {item.product.name} expire dans {days_until_expiry} jour(s) "
                f"({item.expiry_date.strftime('%d/%m/%Y')}). "
                f"Quantité : {item.quantity} {item.unit}."
            )
            priority = "normal"

        if alert_type:
            return self._create_alert_if_not_exists(
                fridge_id=fridge_id,
                inventory_item_id=item.id,
                alert_type=alert_type,
                message=message,
                metadata={"priority": priority, "days_until_expiry": days_until_expiry},
            )

        return None

    def _check_lost_item_alert(
        self, item: InventoryItem, fridge_id: int, threshold_hours: int
    ) -> Optional[Alert]:
        """
        RG11: Crée une alerte si l'objet n'a pas été vu depuis longtemps
        (n'a pas été détecté par le système de vision)
        """
        if not item.last_seen_at:
            return None

        hours_since_seen = (
            datetime.utcnow() - item.last_seen_at
        ).total_seconds() / 3600

        if hours_since_seen > threshold_hours:
            days = int(hours_since_seen / 24)
            hours = int(hours_since_seen % 24)

            message = (
                f"🔍 {item.product.name} n'a pas été détecté depuis "
                f"{days} jour(s) et {hours} heure(s). "
                f"Quantité théorique : {item.quantity} {item.unit}. "
                f"Le produit a peut-être été consommé ou déplacé."
            )

            return self._create_alert_if_not_exists(
                fridge_id=fridge_id,
                inventory_item_id=item.id,
                alert_type="LOST_ITEM",
                message=message,
                metadata={
                    "hours_since_seen": int(hours_since_seen),
                    "last_seen_at": item.last_seen_at.isoformat(),
                },
            )

        return None

    def _check_low_stock_alert(
        self, item: InventoryItem, fridge_id: int, threshold: float
    ) -> Optional[Alert]:
        """
        Crée une alerte si la quantité est en dessous du seuil configuré
        """
        # ❌ AVANT (ligne 206)
        # min_quantity = item.product.metadata.get("min_quantity")
        
        # ✅ APRÈS - Vérifier que metadata existe et est un dict
        if not item.product.extra_data:
            return None
        
        min_quantity = item.product.extra_data.get("min_quantity")
        if min_quantity is None:
            return None

        if item.quantity <= min_quantity:
            message = (
                f"📉 Stock faible pour {item.product.name}. "
                f"Quantité actuelle : {item.quantity} {item.unit}. "
                f"Seuil minimum : {min_quantity} {item.unit}. "
                f"Pensez à en racheter."
            )

            return self._create_alert_if_not_exists(
                fridge_id=fridge_id,
                inventory_item_id=item.id,
                alert_type="LOW_STOCK",
                message=message,
                metadata={
                    "current_quantity": item.quantity,
                    "min_quantity": min_quantity,
                },
            )

        return None

    @transactional
    def _create_alert_if_not_exists(
        self,
        fridge_id: int,
        inventory_item_id: int,
        alert_type: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Alert]:
        """
        RG12: Ne crée pas de doublon si une alerte pending du même type existe

        Returns:
            L'alerte créée, ou None si elle existe déjà
        """
        existing = (
            self.db.query(Alert)
            .filter(
                and_(
                    Alert.fridge_id == fridge_id,
                    Alert.inventory_item_id == inventory_item_id,
                    Alert.type == alert_type,
                    Alert.status == "pending",
                )
            )
            .first()
        )

        if existing:
            logger.debug(
                f"Alert already exists: {alert_type} for item {inventory_item_id}"
            )
            return None

        alert = Alert(
            fridge_id=fridge_id,
            inventory_item_id=inventory_item_id,
            type=alert_type,
            message=message,
            status="pending",
        )

        if metadata:
            from app.models.event import Event

            event = Event(
                fridge_id=fridge_id,
                inventory_item_id=inventory_item_id,
                type="ALERT_CREATED",
                payload={"alert_type": alert_type, "metadata": metadata},
            )
            self.db.add(event)

        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)

        logger.info(f"Created alert: {alert_type} for item {inventory_item_id}")
        return alert

    def _send_alert_notifications(self, alerts: List[Alert], user: User):
        """Envoie les notifications pour les nouvelles alertes"""
        try:
            high_priority_alerts = [
                a for a in alerts if a.type in ["EXPIRED", "EXPIRY_SOON"]
            ]

            if high_priority_alerts:
                for alert in high_priority_alerts:
                    self.notification_service.notify_alert(
                        alert=alert, user=user, channels=["push", "email"]
                    )
            else:
                for alert in alerts:
                    self.notification_service.notify_alert(
                        alert=alert, user=user, channels=["push"]
                    )

            logger.info(
                f"Sent notifications for {len(alerts)} alerts to user {user.id}"
            )

        except Exception as e:
            logger.error(f"Failed to send alert notifications: {e}")

    def get_alerts(
        self,
        fridge_id: int,
        status: Optional[str] = None,
        alert_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Alert]:
        """Récupère les alertes avec filtres optionnels"""
        query = self.db.query(Alert).filter(Alert.fridge_id == fridge_id)

        if status:
            query = query.filter(Alert.status == status)

        if alert_type:
            query = query.filter(Alert.type == alert_type)

        return query.order_by(Alert.created_at.desc()).limit(limit).all()

    @transactional
    def resolve_alert(self, alert_id: int, user_id: int) -> bool:
        """
        CU8: Marque une alerte comme résolue

        Returns:
            True si l'alerte a été résolue, False sinon
        """
        alert = (
            self.db.query(Alert)
            .join(Fridge)
            .filter(Alert.id == alert_id, Fridge.user_id == user_id)
            .first()
        )

        if not alert:
            return False

        alert.status = "resolved"

        from app.models.event import Event

        event = Event(
            fridge_id=alert.fridge_id,
            inventory_item_id=alert.inventory_item_id,
            type="ALERT_RESOLVED",
            payload={
                "alert_id": alert.id,
                "alert_type": alert.type,
                "resolved_at": datetime.utcnow().isoformat(),
            },
        )
        self.db.add(event)

        self.db.commit()
        logger.info(f"Alert {alert_id} resolved by user {user_id}")
        return True

    @transactional
    def bulk_resolve_alerts(
        self, fridge_id: int, user_id: int, alert_type: Optional[str] = None
    ) -> int:
        """
        Résout plusieurs alertes en une fois

        Returns:
            Nombre d'alertes résolues
        """
        query = (
            self.db.query(Alert)
            .join(Fridge)
            .filter(
                Alert.fridge_id == fridge_id,
                Alert.status == "pending",
                Fridge.user_id == user_id,
            )
        )

        if alert_type:
            query = query.filter(Alert.type == alert_type)

        alerts = query.all()
        count = len(alerts)

        for alert in alerts:
            alert.status = "resolved"

        self.db.commit()
        logger.info(f"Bulk resolved {count} alerts for fridge {fridge_id}")
        return count

    @transactional
    def delete_old_alerts(self, days: int = 30) -> int:
        """
        Nettoie les anciennes alertes résolues

        Args:
            days: Nombre de jours à conserver

        Returns:
            Nombre d'alertes supprimées
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        old_alerts = (
            self.db.query(Alert)
            .filter(Alert.status == "resolved", Alert.created_at < cutoff_date)
            .all()
        )

        count = len(old_alerts)

        for alert in old_alerts:
            self.db.delete(alert)

        self.db.commit()
        logger.info(f"Deleted {count} old alerts")
        return count

    def get_alert_statistics(self, fridge_id: int) -> Dict[str, Any]:
        """Génère des statistiques sur les alertes d'un frigo"""
        from sqlalchemy import func

        type_stats = (
            self.db.query(Alert.type, func.count(Alert.id).label("count"))
            .filter(Alert.fridge_id == fridge_id)
            .group_by(Alert.type)
            .all()
        )

        status_stats = (
            self.db.query(Alert.status, func.count(Alert.id).label("count"))
            .filter(Alert.fridge_id == fridge_id)
            .group_by(Alert.status)
            .all()
        )

        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_count = (
            self.db.query(Alert)
            .filter(Alert.fridge_id == fridge_id, Alert.created_at >= week_ago)
            .count()
        )

        return {
            "by_type": {stat.type: stat.count for stat in type_stats},
            "by_status": {stat.status: stat.count for stat in status_stats},
            "recent_alerts": recent_count,
            "pending_count": sum(
                stat.count for stat in status_stats if stat.status == "pending"
            ),
        }
