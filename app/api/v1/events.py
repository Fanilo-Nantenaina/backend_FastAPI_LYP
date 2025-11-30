from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.core.dependencies import get_user_fridge
from app.models.fridge import Fridge
from app.models.event import Event
from app.schemas.event import EventResponse
from typing import Dict, Any

router = APIRouter(prefix="/fridges/{fridge_id}/events", tags=["Events"])


# @router.get("", response_model=List[EventResponse])
@router.get("", response_model=Dict[str, Any])
def list_events(
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    offset = (page - 1) * page_size

    query = db.query(Event).filter(Event.fridge_id == fridge.id)
    total = query.count()

    events = (
        query.order_by(Event.created_at.desc()).offset(offset).limit(page_size).all()
    )

    return {
        "items": events,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/all")
async def stream_fridge_events(
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
):
    """
    📡 STREAM SSE (Server-Sent Events)

    Le client mobile s'abonne à ce stream pour recevoir
    les mises à jour en temps réel de l'inventaire.

    Événements envoyés :
    - INVENTORY_UPDATED : Nouveau scan vision
    - ITEM_CONSUMED : Produit consommé
    - ALERT_CREATED : Nouvelle alerte
    - ITEM_EXPIRED : Produit périmé

    Usage Flutter :
    ```dart
    final eventSource = EventSource(
      url: '$baseUrl/realtime/fridges/$fridgeId/events',
      headers: {'Authorization': 'Bearer $token'},
    );

    eventSource.listen((event) {
      if (event.event == 'INVENTORY_UPDATED') {
        _loadInventory();  // Recharger l'inventaire
      }
    });
    ```
    """

    async def event_generator() -> AsyncGenerator[dict, None]:
        last_event_id = 0

        while True:
            try:
                # Récupérer les nouveaux événements
                new_events = (
                    db.query(Event)
                    .filter(
                        Event.fridge_id == fridge.id,
                        Event.id > last_event_id,
                    )
                    .order_by(Event.id.asc())
                    .limit(10)
                    .all()
                )

                for event in new_events:
                    # Filtrer les événements pertinents pour le client
                    if event.type in [
                        "INVENTORY_UPDATED",
                        "ITEM_ADDED",
                        "ITEM_CONSUMED",
                        "ITEM_DETECTED",
                        "ALERT_CREATED",
                        "ITEM_EXPIRED",
                    ]:
                        yield {
                            "event": event.type,
                            "id": str(event.id),
                            "data": json.dumps(
                                {
                                    "event_id": event.id,
                                    "type": event.type,
                                    "payload": event.payload,
                                    "timestamp": event.created_at.isoformat(),
                                }
                            ),
                        }

                        last_event_id = event.id

                # Attendre 2 secondes avant la prochaine vérification
                await asyncio.sleep(2)

            except Exception as e:
                # En cas d'erreur, envoyer un événement d'erreur et continuer
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(e)}),
                }
                await asyncio.sleep(5)

    return EventSourceResponse(event_generator())


@router.post("/notify")
async def notify_inventory_update(
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
):
    """
    🔵 KIOSK ROUTE

    Appelée par le kiosk après un scan vision réussi.
    Crée un événement "INVENTORY_UPDATED" qui sera
    diffusé aux clients mobiles connectés via SSE.
    """
    from app.services.event_service import EventService

    event_service = EventService(db)
    event_service.create_event(
        fridge_id=fridge.id,
        event_type="INVENTORY_UPDATED",
        payload={
            "source": "vision_scan",
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    return {"message": "Notification sent"}
