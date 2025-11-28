from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
import asyncio

router = APIRouter(prefix="/realtime", tags=["Real-time"])


@router.get("/alerts/{fridge_id}")
async def stream_alerts(
    fridge: Fridge = Depends(get_user_fridge), db: Session = Depends(get_db)
):
    """Stream des alertes en temps réel"""

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
