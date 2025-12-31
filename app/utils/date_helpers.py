from datetime import datetime, date, timedelta
from typing import Optional


def days_until_expiry(expiry_date: Optional[date]) -> Optional[int]:
    if not expiry_date:
        return None

    delta = expiry_date - date.today()
    return delta.days


def is_expired(expiry_date: Optional[date]) -> bool:
    if not expiry_date:
        return False

    return expiry_date < date.today()


def estimate_expiry_date(
    added_at: datetime, shelf_life_days: Optional[int]
) -> Optional[date]:
    if not shelf_life_days:
        return None

    return added_at.date() + timedelta(days=shelf_life_days)


def format_datetime_for_timezone(dt: datetime, timezone: str) -> str:
    return dt.isoformat()
