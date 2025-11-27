from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Fridge(Base):
    """
    Modèle Fridge - Réfrigérateur
    RG1: Un utilisateur peut avoir plusieurs frigos
    RG2: Chaque frigo appartient à un seul utilisateur
    """

    __tablename__ = "fridges"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String, nullable=False)
    location = Column(String)  # Cuisine, Garage, Bureau, etc.

    # Configuration du frigo (seuils d'alerte personnalisés)
    config = Column(JSON, default=dict)
    # Exemple: {"expiry_warning_days": 3, "lost_item_threshold_hours": 72}

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    user = relationship("User", back_populates="fridges")
    inventory_items = relationship(
        "InventoryItem", back_populates="fridge", cascade="all, delete-orphan"
    )
    events = relationship(
        "Event", back_populates="fridge", cascade="all, delete-orphan"
    )
    alerts = relationship(
        "Alert", back_populates="fridge", cascade="all, delete-orphan"
    )
    shopping_lists = relationship(
        "ShoppingList", back_populates="fridge", cascade="all, delete-orphan"
    )
    devices = relationship(
        "FridgeDevice", back_populates="fridge", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Fridge(id={self.id}, name={self.name}, user_id={self.user_id})>"
