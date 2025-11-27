"""
Configuration complète du scheduler pour toutes les tâches périodiques
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.tasks.alert_checker import (
    check_all_alerts,
    send_daily_summaries,
    cleanup_old_data,
    check_lost_items_only,
)
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


def start_scheduler():
    """
    Démarre le scheduler avec toutes les tâches configurées

    Tâches planifiées:
    1. Vérification des alertes (toutes les heures)
    2. Résumés quotidiens (tous les jours à 8h00)
    3. Nettoyage des données (tous les jours à 3h00)
    4. Vérification des objets perdus (toutes les 6 heures)
    """

    if not settings.SCHEDULER_ENABLED:
        logger.warning("⚠️ Scheduler is disabled in settings")
        return

    logger.info("⏰ Starting scheduler...")

    # ==========================================
    # TÂCHE 1: Vérification des alertes (CU7)
    # ==========================================
    # Toutes les heures
    scheduler.add_job(
        check_all_alerts,
        trigger=IntervalTrigger(hours=settings.ALERT_CHECK_INTERVAL_HOURS),
        id="check_alerts",
        name="Check expiry and lost item alerts",
        replace_existing=True,
        misfire_grace_time=300,  # 5 minutes de grâce si le serveur était arrêté
    )
    logger.info("✓ Scheduled: Alert check (every hour)")

    # ==========================================
    # TÂCHE 2: Résumés quotidiens
    # ==========================================
    # Tous les jours à l'heure configurée (ex: 08:00)
    if settings.SEND_DAILY_SUMMARY:
        hour, minute = settings.DAILY_SUMMARY_TIME.split(":")

        scheduler.add_job(
            send_daily_summaries,
            trigger=CronTrigger(hour=int(hour), minute=int(minute)),
            id="daily_summaries",
            name="Send daily fridge summaries",
            replace_existing=True,
        )
        logger.info(
            f"✓ Scheduled: Daily summaries (every day at {settings.DAILY_SUMMARY_TIME})"
        )

    # ==========================================
    # TÂCHE 3: Nettoyage des données
    # ==========================================
    # Tous les jours à 3h00 du matin
    scheduler.add_job(
        cleanup_old_data,
        trigger=CronTrigger(hour=3, minute=0),
        id="cleanup_data",
        name="Cleanup old alerts and events",
        replace_existing=True,
    )
    logger.info("✓ Scheduled: Data cleanup (every day at 03:00)")

    # ==========================================
    # TÂCHE 4: Vérification des objets perdus
    # ==========================================
    # Toutes les 6 heures (plus fréquent que la vérification complète)
    scheduler.add_job(
        check_lost_items_only,
        trigger=IntervalTrigger(hours=6),
        id="check_lost_items",
        name="Check for lost items",
        replace_existing=True,
    )
    logger.info("✓ Scheduled: Lost items check (every 6 hours)")

    # ==========================================
    # Démarrer le scheduler
    # ==========================================
    scheduler.start()
    logger.info("✅ Scheduler started successfully")

    # Afficher les tâches planifiées
    logger.info("📋 Scheduled jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name} (ID: {job.id}, Next run: {job.next_run_time})")


def stop_scheduler():
    """Arrête proprement le scheduler"""
    logger.info("🛑 Stopping scheduler...")
    scheduler.shutdown(wait=True)
    logger.info("✅ Scheduler stopped")


def get_scheduler_status():
    """
    Retourne le statut du scheduler et de ses tâches

    Utile pour le monitoring
    """
    if not scheduler.running:
        return {"running": False, "jobs": []}

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
                "trigger": str(job.trigger),
            }
        )

    return {"running": True, "jobs": jobs}


def trigger_job_manually(job_id: str):
    """
    Déclenche manuellement une tâche planifiée

    Args:
        job_id: 'check_alerts', 'daily_summaries', 'cleanup_data', 'check_lost_items'

    Utile pour les tests ou les vérifications manuelles
    """
    try:
        job = scheduler.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        logger.info(f"🔧 Manually triggering job: {job_id}")
        job.modify(next_run_time=None)  # Exécuter immédiatement

        return True
    except Exception as e:
        logger.error(f"Failed to trigger job {job_id}: {e}")
        return False
