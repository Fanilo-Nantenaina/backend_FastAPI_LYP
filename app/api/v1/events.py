from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.core.dependencies import get_user_fridge
from app.models.fridge import Fridge
from app.models.event import Event
from app.schemas.event import EventResponse

router = APIRouter(prefix="/fridges/{fridge_id}/events", tags=["Events"])


@router.get("", response_model=List[EventResponse])
async def list_events(
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
    event_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    """CU5: Consulter l'Historique des événements"""
    query = db.query(Event).filter(Event.fridge_id == fridge.id)

    if event_type:
        query = query.filter(Event.type == event_type)

    return query.order_by(Event.created_at.desc()).offset(offset).limit(limit).all()
