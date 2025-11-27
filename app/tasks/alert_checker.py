"""
Tâche périodique de vérification des alertes (CU7)
Exécutée automatiquement par le scheduler toutes les heures
"""

from app.core.database import SessionLocal
from app.services.alert_service import AlertService
from app.services.notification_service import NotificationService
from app.models.fridge import Fridge
import logging

logger = logging.getLogger(__name__)


def check_all_alerts():
    """
    CU7: Tâche principale de vérification des alertes

    Cette fonction est appelée automatiquement par le scheduler
    pour vérifier tous les frigos et créer/envoyer les alertes nécessaires

    Règles appliquées:
    - RG10: Alertes de péremption
    - RG11: Alertes d'objets perdus
    - RG12: Pas de duplication d'alertes
    """
    logger.info("🔍 Starting alert check task...")

    db = SessionLocal()
    try:
        alert_service = AlertService(db)
        notification_service = NotificationService(db)

        # Vérifier et créer les alertes pour tous les frigos
        stats = alert_service.check_and_create_alerts(
            fridge_id=None, send_notifications=True  # Tous les frigos
        )

        logger.info(
            f"✅ Alert check completed. Stats: "
            f"EXPIRY_SOON={stats['EXPIRY_SOON']}, "
            f"EXPIRED={stats['EXPIRED']}, "
            f"LOST_ITEM={stats['LOST_ITEM']}, "
            f"LOW_STOCK={stats['LOW_STOCK']}, "
            f"Total notified={stats['total_notified']}"
        )

        return stats

    except Exception as e:
        logger.error(f"❌ Error during alert check: {e}", exc_info=True)
        raise
    finally:
        db.close()


def check_fridge_alerts(fridge_id: int):
    """
    Vérifie les alertes pour un frigo spécifique

    Utile pour les vérifications manuelles ou déclenchées par événement
    """
    logger.info(f"🔍 Checking alerts for fridge {fridge_id}...")

    db = SessionLocal()
    try:
        alert_service = AlertService(db)

        stats = alert_service.check_and_create_alerts(
            fridge_id=fridge_id, send_notifications=True
        )

        logger.info(f"✅ Alert check completed for fridge {fridge_id}")
        return stats

    except Exception as e:
        logger.error(f"❌ Error checking alerts for fridge {fridge_id}: {e}")
        raise
    finally:
        db.close()


def send_daily_summaries():
    """
    Envoie les résumés quotidiens à tous les utilisateurs

    Cette tâche devrait être planifiée une fois par jour (ex: 8h00)
    """
    logger.info("📧 Starting daily summary email task...")

    db = SessionLocal()
    try:
        notification_service = NotificationService(db)

        # Récupérer tous les frigos
        fridges = db.query(Fridge).all()

        sent_count = 0
        failed_count = 0

        for fridge in fridges:
            user = fridge.owner

            if not user:
                continue

            try:
                success = notification_service.send_daily_summary_email(
                    user=user, fridge_id=fridge.id
                )

                if success:
                    sent_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                logger.error(f"Failed to send daily summary for user {user.id}: {e}")
                failed_count += 1

        logger.info(
            f"✅ Daily summaries sent. Success: {sent_count}, Failed: {failed_count}"
        )

        return {"sent": sent_count, "failed": failed_count}

    except Exception as e:
        logger.error(f"❌ Error during daily summary task: {e}", exc_info=True)
        raise
    finally:
        db.close()


def cleanup_old_data():
    """
    Nettoie les anciennes données (alertes résolues, événements anciens)

    Cette tâche devrait être planifiée une fois par jour
    """
    logger.info("🧹 Starting data cleanup task...")

    db = SessionLocal()
    try:
        from app.services.alert_service import AlertService
        from app.services.event_service import EventService

        alert_service = AlertService(db)
        event_service = EventService(db)

        # Supprimer les alertes résolues de plus de 30 jours
        deleted_alerts = alert_service.delete_old_alerts(days=30)

        # Supprimer les événements de plus de 90 jours
        deleted_events = event_service.cleanup_old_events(days=90)

        logger.info(
            f"✅ Cleanup completed. "
            f"Deleted {deleted_alerts} old alerts, "
            f"{deleted_events} old events"
        )

        return {"deleted_alerts": deleted_alerts, "deleted_events": deleted_events}

    except Exception as e:
        logger.error(f"❌ Error during cleanup task: {e}", exc_info=True)
        raise
    finally:
        db.close()


def check_lost_items_only():
    """
    Vérifie uniquement les objets perdus (pas vu depuis longtemps)

    Peut être exécuté plus fréquemment que la vérification complète
    """
    logger.info("🔍 Checking for lost items only...")

    db = SessionLocal()
    try:
        from app.models.inventory import InventoryItem
        from app.models.fridge import Fridge
        from datetime import datetime, timedelta

        alert_service = AlertService(db)

        # Récupérer tous les frigos
        fridges = db.query(Fridge).all()

        total_lost_items = 0

        for fridge in fridges:
            config = fridge.config or {}
            lost_hours = config.get("lost_item_threshold_hours", 72)

            # Récupérer les items qui n'ont pas été vus depuis longtemps
            threshold = datetime.utcnow() - timedelta(hours=lost_hours)

            items = (
                db.query(InventoryItem)
                .filter(
                    InventoryItem.fridge_id == fridge.id,
                    InventoryItem.quantity > 0,
                    InventoryItem.last_seen_at < threshold,
                )
                .all()
            )

            for item in items:
                # Créer l'alerte si elle n'existe pas (RG12)
                alert = alert_service._check_lost_item_alert(
                    item, fridge.id, lost_hours
                )
                if alert:
                    total_lost_items += 1

        logger.info(f"✅ Lost items check completed. Found {total_lost_items} items")
        return {"lost_items": total_lost_items}

    except Exception as e:
        logger.error(f"❌ Error checking lost items: {e}")
        raise
    finally:
        db.close()
