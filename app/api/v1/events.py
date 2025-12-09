from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, AsyncGenerator
from datetime import datetime
from sse_starlette.sse import EventSourceResponse
import asyncio
import json

from app.core.database import get_db
from app.core.dependencies import get_user_fridge
from app.models.fridge import Fridge
from app.models.event import Event
from app.core.database import SessionLocal

router = APIRouter(prefix="/fridges/{fridge_id}/events", tags=["Events"])


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
):
    """
    Stream SSE des événements du frigo

    CORRIGÉ:
    - Envoie seulement les NOUVEAUX événements (pas de répétition)
    - Garde trace du dernier event_id envoyé
    - Pas de regroupement artificiel qui cause des doublons
    """

    async def event_generator() -> AsyncGenerator[dict, None]:
        last_event_id = 0

        RELEVANT_EVENTS = {
            "ITEM_ADDED",
            "ITEM_CONSUMED",
            "ITEM_REMOVED",
            "ITEM_DETECTED",
            "QUANTITY_UPDATED",
            "ALERT_CREATED",
            "ITEM_EXPIRED",
        }

        db_init: Session = SessionLocal()
        try:
            last_event = (
                db_init.query(Event)
                .filter(Event.fridge_id == fridge.id)
                .order_by(Event.id.desc())
                .first()
            )
            if last_event:
                last_event_id = last_event.id
        finally:
            db_init.close()

        # CORRECTION: Tous les champs doivent être des strings valides
        yield {
            "event": "connected",
            "id": "0",
            "data": json.dumps(
                {
                    "type": "CONNECTED",  # Ajout du type
                    "message": "Connexion SSE établie",
                    "fridge_id": fridge.id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "payload": {},  # Ajout du payload vide
                }
            ),
        }

        while True:
            db_local: Session = SessionLocal()
            try:
                new_events = (
                    db_local.query(Event)
                    .filter(
                        Event.fridge_id == fridge.id,
                        Event.id > last_event_id,
                        Event.type.in_(RELEVANT_EVENTS),
                    )
                    .order_by(Event.id.asc())
                    .limit(10)
                    .all()
                )

                for event in new_events:
                    last_event_id = event.id

                    # CORRECTION: S'assurer que payload n'est jamais None
                    payload = event.payload if event.payload is not None else {}

                    # CORRECTION: S'assurer que le message n'est jamais None
                    message = _generate_event_message(event.type, payload)
                    if message is None:
                        message = "Mise à jour de l'inventaire"

                    # CORRECTION: S'assurer que le type n'est jamais None
                    event_type = event.type if event.type else "INVENTORY_UPDATED"

                    yield {
                        "event": event_type,
                        "id": str(event.id),
                        "data": json.dumps(
                            {
                                "event_id": event.id,
                                "type": event_type,
                                "message": message,
                                "payload": payload,
                                "timestamp": (
                                    event.created_at.isoformat()
                                    if event.created_at
                                    else datetime.utcnow().isoformat()
                                ),
                            }
                        ),
                    }

            except Exception as e:
                yield {
                    "event": "error",
                    "id": str(last_event_id),
                    "data": json.dumps(
                        {
                            "type": "ERROR",
                            "message": "Erreur interne",
                            "error": str(e),
                            "payload": {},
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    ),
                }

            finally:
                db_local.close()

            await asyncio.sleep(3)

    def _generate_event_message(event_type: str, payload: dict) -> str:
        """Génère un message lisible pour chaque type d'événement"""
        # CORRECTION: Gestion des valeurs None
        if payload is None:
            payload = {}

        product_name = payload.get("product_name") or "Produit"
        quantity = payload.get("quantity") or ""
        unit = payload.get("unit") or ""

        messages = {
            "ITEM_ADDED": f"{product_name} ajouté ({quantity} {unit})".strip(),
            "ITEM_CONSUMED": f"{product_name} consommé",
            "ITEM_REMOVED": f"{product_name} supprimé",
            "ITEM_DETECTED": f"{product_name} détecté par scan",
            "QUANTITY_UPDATED": f"Quantité de {product_name} mise à jour",
            "ALERT_CREATED": "Nouvelle alerte créée",
            "ITEM_EXPIRED": f"{product_name} a expiré",
        }

        return messages.get(event_type, "Mise à jour de l'inventaire")

    return EventSourceResponse(event_generator())


def _generate_event_message(event_type: str, payload: dict) -> str:
    """Génère un message lisible pour chaque type d'événement"""
    product_name = payload.get("product_name", "Produit")
    quantity = payload.get("quantity", "")
    unit = payload.get("unit", "")

    messages = {
        "ITEM_ADDED": f"{product_name} ajouté ({quantity} {unit})".strip(),
        "ITEM_CONSUMED": f"{product_name} consommé",
        "ITEM_REMOVED": f"{product_name} supprimé",
        "ITEM_DETECTED": f"{product_name} détecté par scan",
        "QUANTITY_UPDATED": f"Quantité de {product_name} mise à jour",
        "ALERT_CREATED": "Nouvelle alerte créée",
        "ITEM_EXPIRED": f"{product_name} a expiré",
    }

    return messages.get(event_type, "Mise à jour de l'inventaire")


@router.post("/notify")
async def notify_inventory_update(
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
):
    """
    KIOSK ROUTE - Les événements sont déjà créés par les autres services
    Cette route est juste un accusé de réception
    """
    return {
        "message": "Notification acknowledged",
        "note": "Events are created automatically by services",
    }
