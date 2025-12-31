from fastapi import APIRouter, Depends, Query, HTTPException, Path
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.core.database import get_db
from app.core.dependencies import get_user_fridge, get_current_user
from app.models.fridge import Fridge
from app.models.user import User
from app.models.event import Event
from app.services.event_service import EventService
from app.schemas.event import EventResponse, PaginatedEventsResponse

router = APIRouter(prefix="/fridges/{fridge_id}/events", tags=["Events"])


@router.get("", response_model=PaginatedEventsResponse)
def list_events(
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
    event_type: Optional[str] = Query(None, description="Filtrer par type d'événement"),
    start_date: Optional[datetime] = Query(
        None, description="Date de début (ISO 8601)"
    ),
    end_date: Optional[datetime] = Query(None, description="Date de fin (ISO 8601)"),
    page: int = Query(1, ge=1, description="Numéro de page"),
    page_size: int = Query(50, ge=1, le=100, description="Nombre d'éléments par page"),
):
    event_service = EventService(db)

    offset = (page - 1) * page_size

    events = event_service.get_events(
        fridge_id=fridge.id,
        event_type=event_type,
        limit=page_size,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
    )

    query = db.query(Event).filter(Event.fridge_id == fridge.id)
    if event_type:
        query = query.filter(Event.type == event_type)
    if start_date:
        query = query.filter(Event.created_at >= start_date)
    if end_date:
        query = query.filter(Event.created_at <= end_date)

    total = query.count()

    return {
        "items": events,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "filters": {
            "event_type": event_type,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
    }


@router.get("/statistics", response_model=Dict[str, Any])
def get_event_statistics(
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365, description="Nombre de jours d'historique"),
):
    event_service = EventService(db)
    return event_service.get_event_statistics(fridge.id, days)


@router.get("/items/{item_id}/history", response_model=List[EventResponse])
def get_item_event_history(
    item_id: int = Path(..., description="ID de l'item d'inventaire"),
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100, description="Nombre max d'événements"),
):
    event_service = EventService(db)

    from app.models.inventory import InventoryItem

    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.id == item_id, InventoryItem.fridge_id == fridge.id)
        .first()
    )

    if not item:
        raise HTTPException(
            status_code=404, detail=f"Item {item_id} not found in your fridge"
        )

    events = event_service.get_item_history(item_id, limit=limit)

    return events


@router.delete("/cleanup", response_model=Dict[str, Any])
def cleanup_old_events(
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
    days: int = Query(
        90, ge=30, le=365, description="Supprimer les événements plus vieux que X jours"
    ),
    current_user: User = Depends(get_current_user),
):
    event_service = EventService(db)

    deleted_count = event_service.cleanup_old_events(days=days)

    return {
        "success": True,
        "deleted_count": deleted_count,
        "cutoff_days": days,
        "message": f"{deleted_count} événements supprimés (plus de {days} jours)",
    }


@router.get("/types", response_model=Dict[str, Any])
def get_event_types():
    event_types = {
        "ITEM_ADDED": {
            "description": "Un produit a été ajouté au frigo",
            "payload_fields": ["product_name", "quantity", "unit", "source"],
            "sources": ["manual", "vision", "scan"],
        },
        "ITEM_REMOVED": {
            "description": "Un produit a été retiré du frigo",
            "payload_fields": ["product_name", "reason"],
        },
        "ITEM_CONSUMED": {
            "description": "Un produit a été consommé",
            "payload_fields": ["product_name", "quantity_consumed"],
        },
        "ITEM_DETECTED": {
            "description": "Un produit a été détecté par vision IA",
            "payload_fields": ["product_name", "confidence", "detected_items"],
        },
        "QUANTITY_UPDATED": {
            "description": "La quantité d'un produit a été modifiée",
            "payload_fields": ["product_name", "old_quantity", "new_quantity"],
        },
        "EXPIRY_UPDATED": {
            "description": "La date d'expiration a été modifiée",
            "payload_fields": ["product_name", "old_expiry", "new_expiry"],
        },
        "ALERT_CREATED": {
            "description": "Une alerte a été créée",
            "payload_fields": ["alert_type", "message", "severity"],
        },
        "ALERT_RESOLVED": {
            "description": "Une alerte a été résolue",
            "payload_fields": ["alert_id", "resolution"],
        },
        "ITEM_EXPIRED": {
            "description": "Un produit a expiré",
            "payload_fields": ["product_name", "expiry_date"],
        },
    }

    return {
        "event_types": event_types,
        "total_types": len(event_types),
    }


@router.get("/statistics/by-type", response_model=Dict[str, Any])
def get_statistics_by_event_type(
    event_type: str = Query(..., description="Type d'événement à analyser"),
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365, description="Nombre de jours d'historique"),
):
    event_service = EventService(db)

    from datetime import datetime, timedelta

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    events = event_service.get_events(
        fridge_id=fridge.id,
        event_type=event_type,
        start_date=cutoff_date,
        limit=1000,
    )

    total_count = len(events)

    events_by_day = {}
    for event in events:
        day = event.created_at.date().isoformat()
        events_by_day[day] = events_by_day.get(day, 0) + 1

    timeline = sorted(
        [{"date": date, "count": count} for date, count in events_by_day.items()],
        key=lambda x: x["date"],
    )

    avg_per_day = total_count / days if days > 0 else 0

    return {
        "event_type": event_type,
        "period_days": days,
        "total_count": total_count,
        "average_per_day": round(avg_per_day, 2),
        "timeline": timeline,
        "first_event": events[-1].created_at.isoformat() if events else None,
        "last_event": events[0].created_at.isoformat() if events else None,
    }
