from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime


class EventResponse(BaseModel):
    id: int
    fridge_id: int
    inventory_item_id: Optional[int]
    type: str
    payload: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class EventCreateRequest(BaseModel):
    """Schéma pour créer un événement manuellement"""

    event_type: str = Field(
        ..., description="Type d'événement (ITEM_ADDED, ITEM_CONSUMED, etc.)"
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict, description="Données de l'événement"
    )
    inventory_item_id: Optional[int] = Field(None, description="ID de l'item concerné")


class EventFilterParams(BaseModel):
    """Paramètres de filtrage pour les événements"""

    event_type: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)


class EventFilterParams(BaseModel):
    """Paramètres de filtrage pour les événements"""

    event_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class PaginatedEventsResponse(BaseModel):
    """Réponse paginée pour la liste des événements"""

    items: List[EventResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    filters: EventFilterParams

    class Config:
        from_attributes = True
