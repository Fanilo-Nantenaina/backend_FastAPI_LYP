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
