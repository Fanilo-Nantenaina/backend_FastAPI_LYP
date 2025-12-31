from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import logging
import secrets
import string
import uuid

from app.middleware.transaction_handler import transactional
from app.models.fridge import Fridge
from app.models.inventory import InventoryItem
from app.models.alert import Alert
from app.models.event import Event
from app.core.config import settings
from app.core.security import create_access_token

logger = logging.getLogger(__name__)


class FridgeService:
    def __init__(self, db: Session):
        self.db = db

    @transactional
    def init_kiosk(
        self, device_id: Optional[str] = None, device_name: Optional[str] = None
    ) -> Dict:
        if device_id:
            existing_fridge = (
                self.db.query(Fridge).filter(Fridge.device_id == device_id).first()
            )

            if existing_fridge:
                logger.info(f"Restoring kiosk from device_id: {device_id}")

                existing_fridge.last_heartbeat = datetime.utcnow()

                if existing_fridge.is_paired:
                    return {
                        "kiosk_id": existing_fridge.kiosk_id,
                        "is_paired": True,
                        "fridge_id": existing_fridge.id,
                        "fridge_name": existing_fridge.name,
                        "pairing_code": None,
                        "expires_in_minutes": 0,
                    }
                else:
                    timeout_minutes = settings.DEVICE_PAIRING_TIMEOUT_MINUTES
                    valid_after = datetime.utcnow() - timedelta(minutes=timeout_minutes)

                    if (
                        existing_fridge.created_at >= valid_after
                        and existing_fridge.pairing_code
                    ):
                        return {
                            "kiosk_id": existing_fridge.kiosk_id,
                            "pairing_code": existing_fridge.pairing_code,
                            "expires_in_minutes": settings.DEVICE_PAIRING_TIMEOUT_MINUTES,
                            "is_paired": False,
                        }
                    else:
                        existing_fridge.pairing_code = "".join(
                            secrets.choice(string.digits) for _ in range(6)
                        )
                        existing_fridge.created_at = datetime.utcnow()

                        return {
                            "kiosk_id": existing_fridge.kiosk_id,
                            "pairing_code": existing_fridge.pairing_code,
                            "expires_in_minutes": settings.DEVICE_PAIRING_TIMEOUT_MINUTES,
                            "is_paired": False,
                        }

        kiosk_id = str(uuid.uuid4())
        pairing_code = "".join(secrets.choice(string.digits) for _ in range(6))

        fridge = Fridge(
            kiosk_id=kiosk_id,
            device_id=device_id,
            device_name=device_name or "Smart Fridge Kiosk",
            pairing_code=pairing_code,
            is_paired=False,
            user_id=None,
            name="Mon Frigo",
        )

        self.db.add(fridge)

        logger.info(f"New kiosk initialized: {kiosk_id} (device_id: {device_id})")

        return {
            "kiosk_id": kiosk_id,
            "pairing_code": pairing_code,
            "expires_in_minutes": settings.DEVICE_PAIRING_TIMEOUT_MINUTES,
            "is_paired": False,
        }

    @transactional
    def update_heartbeat(self, kiosk_id: str):
        fridge = self.db.query(Fridge).filter(Fridge.kiosk_id == kiosk_id).first()

        if fridge:
            fridge.last_heartbeat = datetime.utcnow()
            logger.debug(f"Heartbeat updated for kiosk {kiosk_id}")

    def get_fridge_status(self, kiosk_id: str) -> Optional[Dict]:
        fridge = self.db.query(Fridge).filter(Fridge.kiosk_id == kiosk_id).first()

        if not fridge:
            return None

        return {
            "kiosk_id": fridge.kiosk_id,
            "is_paired": fridge.is_paired,
            "fridge_id": fridge.id if fridge.is_paired else None,
            "fridge_name": fridge.name if fridge.is_paired else None,
            "last_heartbeat": (
                fridge.last_heartbeat.isoformat() if fridge.last_heartbeat else None
            ),
            "paired_at": fridge.paired_at.isoformat() if fridge.paired_at else None,
        }

    @transactional
    def pair_fridge(
        self,
        pairing_code: str,
        user_id: int,
        fridge_name: str = "Mon Frigo",
        fridge_location: Optional[str] = None,
    ) -> Optional[Dict]:
        timeout_minutes = settings.DEVICE_PAIRING_TIMEOUT_MINUTES
        valid_after = datetime.utcnow() - timedelta(minutes=timeout_minutes)

        fridge = (
            self.db.query(Fridge)
            .filter(
                Fridge.pairing_code == pairing_code,
                Fridge.is_paired,
                Fridge.created_at >= valid_after,
            )
            .first()
        )

        if not fridge:
            logger.warning(f"Pairing failed: invalid or expired code {pairing_code}")
            return None

        fridge.user_id = user_id
        fridge.name = fridge_name
        fridge.location = fridge_location
        fridge.is_paired = True
        fridge.paired_at = datetime.utcnow()
        fridge.pairing_code = None
        fridge.last_heartbeat = datetime.utcnow()

        if not fridge.config:
            fridge.config = {
                "expiry_warning_days": 3,
                "lost_item_threshold_hours": 72,
                "low_stock_threshold": 2.0,
            }

        access_token = create_access_token(
            {
                "sub": str(user_id),
                "fridge_id": fridge.id,
            }
        )

        logger.info(f"Fridge paired: {fridge.id} to user {user_id}")

        return {
            "fridge_id": fridge.id,
            "fridge_name": fridge.name,
            "fridge_location": fridge.location,
            "kiosk_id": fridge.kiosk_id,
            "access_token": access_token,
        }

    @transactional
    def unpair_fridge(self, fridge_id: int, user_id: int) -> bool:
        fridge = self.db.query(Fridge).filter(Fridge.id == fridge_id).first()

        if not fridge:
            return False

        fridge.is_paired = False
        fridge.user_id = None
        fridge.paired_at = None
        fridge.name = "Mon Frigo"
        fridge.location = None

        fridge.pairing_code = "".join(secrets.choice(string.digits) for _ in range(6))

        self.db.query(InventoryItem).filter(
            InventoryItem.fridge_id == fridge_id
        ).delete()
        self.db.query(Alert).filter(Alert.fridge_id == fridge_id).delete()

        logger.info(f"Fridge unpaired: {fridge_id}")

        return True

    def get_fridge_by_id(
        self, fridge_id: int, user_id: Optional[int] = None
    ) -> Optional[Fridge]:
        query = self.db.query(Fridge).filter(Fridge.id == fridge_id)

        if user_id:
            query = query.filter(Fridge.user_id == user_id)

        return query.first()

    def get_user_fridges(self, user_id: int) -> List[Fridge]:
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

        logger.info(f"Fridge updated: {fridge_id}")
        return fridge

    @transactional
    def delete_fridge(self, fridge_id: int, user_id: int) -> bool:
        fridge = self.get_fridge_by_id(fridge_id, user_id)

        if not fridge:
            return False

        self.db.delete(fridge)

        logger.info(f"Fridge deleted: {fridge_id}")
        return True

    def get_fridge_statistics(self, fridge_id: int) -> Dict[str, Any]:
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
            if item.extra_data and "price" in item.extra_data:
                total_value += item.extra_data["price"] * item.quantity

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
