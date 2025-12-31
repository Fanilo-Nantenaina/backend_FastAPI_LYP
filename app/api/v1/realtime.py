from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse
import asyncio
from app.core.database import get_db
from app.models.alert import Alert
from app.models.fridge import Fridge
from app.core.dependencies import get_fridge_access_hybrid
import json

router = APIRouter(prefix="/realtime", tags=["Real-time"])


@router.get("/alerts/{fridge_id}")
async def stream_alerts(
    fridge: Fridge = Depends(get_fridge_access_hybrid), db: Session = Depends(get_db)
):
    async def event_generator():
        last_alert_id = 0

        while True:
            new_alerts = (
                db.query(Alert)
                .filter(Alert.fridge_id == fridge.id, Alert.id > last_alert_id)
                .all()
            )

            for alert in new_alerts:
                yield {
                    "event": "alert",
                    "data": json.dumps(
                        {"id": alert.id, "type": alert.type, "message": alert.message}
                    ),
                }
                last_alert_id = alert.id

            await asyncio.sleep(5)

    return EventSourceResponse(event_generator())
