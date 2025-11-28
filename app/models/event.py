from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Event(Base):
    """
    Modèle Event - Historique des événements
    RG5: Tout changement génère un événement
    CU5: Consulter l'Historique
    """

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    fridge_id = Column(
        Integer, ForeignKey("fridges.id", ondelete="CASCADE"), nullable=False
    )
    inventory_item_id = Column(
        Integer, ForeignKey("inventory_items.id", ondelete="SET NULL")
    )

    type = Column(String, nullable=False, index=True)
    # Types d'événements : ITEM_ADDED, ITEM_REMOVED, ITEM_CONSUMED,
    # ITEM_DETECTED, EXPIRY_UPDATED, ALERT_CREATED, etc.

    payload = Column(JSON, default=dict)  # Données de l'événement
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relations
    fridge = relationship("Fridge", back_populates="events")
    inventory_item = relationship("InventoryItem", back_populates="events")
    
    __table_args__ = (
        Index('ix_event_fridge_created', 'fridge_id', 'created_at'),
        Index('ix_event_fridge_type', 'fridge_id', 'type'),
        Index('ix_event_item_created', 'inventory_item_id', 'created_at'),
    )

    def __repr__(self):
        return f"<Event(id={self.id}, type={self.type}, fridge_id={self.fridge_id})>"
