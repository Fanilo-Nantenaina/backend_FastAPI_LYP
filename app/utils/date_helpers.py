from datetime import datetime, date, timedelta
from typing import Optional


def days_until_expiry(expiry_date: Optional[date]) -> Optional[int]:
    """Calcule le nombre de jours avant expiration"""
    if not expiry_date:
        return None

    delta = expiry_date - date.today()
    return delta.days


def is_expired(expiry_date: Optional[date]) -> bool:
    """Vérifie si un produit est expiré"""
    if not expiry_date:
        return False

    return expiry_date < date.today()


def estimate_expiry_date(
    added_at: datetime, shelf_life_days: Optional[int]
) -> Optional[date]:
    """Estime la date de péremption basée sur la durée de conservation"""
    if not shelf_life_days:
        return None

    return added_at.date() + timedelta(days=shelf_life_days)


def format_datetime_for_timezone(dt: datetime, timezone: str) -> str:
    """Formate une datetime selon le fuseau horaire de l'utilisateur"""
    # Utiliser pytz pour une conversion complète en production
    return dt.isoformat()
