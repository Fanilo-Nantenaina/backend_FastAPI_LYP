from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Alert(Base):
    """
    Modèle Alert - Alertes et notifications
    RG10: Alerte de péremption
    RG11: Alerte d'objet perdu
    RG12: Pas de doublon d'alerte
    CU7: Déclencher les Alertes
    CU8: Consulter les alertes
    """

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    fridge_id = Column(
        Integer, ForeignKey("fridges.id", ondelete="CASCADE"), nullable=False
    )
    inventory_item_id = Column(
        Integer, ForeignKey("inventory_items.id", ondelete="CASCADE")
    )

    type = Column(String, nullable=False, index=True)
    # Types : EXPIRY_SOON, EXPIRED, LOST_ITEM, LOW_STOCK, etc.

    message = Column(String, nullable=False)
    status = Column(
        String, default="pending", index=True
    )  # pending, acknowledged, resolved

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime)

    # Relations
    fridge = relationship("Fridge", back_populates="alerts")
    inventory_item = relationship("InventoryItem", back_populates="alerts")

    def __repr__(self):
        return f"<Alert(id={self.id}, type={self.type}, status={self.status})>"
