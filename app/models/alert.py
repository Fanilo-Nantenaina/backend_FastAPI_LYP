from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    fridge_id = Column(
        Integer, ForeignKey("fridges.id", ondelete="CASCADE"), nullable=False
    )
    inventory_item_id = Column(
        Integer, ForeignKey("inventory_items.id", ondelete="CASCADE")
    )

    type = Column(String, nullable=False, index=True)
                                                              

    message = Column(String, nullable=False)
    status = Column(
        String, default="pending", index=True
    )                                   

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime)

               
    fridge = relationship("Fridge", back_populates="alerts")
    inventory_item = relationship("InventoryItem", back_populates="alerts")

    __table_args__ = (
        Index("ix_alert_fridge_status", "fridge_id", "status"),
        Index("ix_alert_fridge_type_status", "fridge_id", "type", "status"),
        Index("ix_alert_created_status", "created_at", "status"),
    )

    def __repr__(self):
        return f"<Alert(id={self.id}, type={self.type}, status={self.status})>"
