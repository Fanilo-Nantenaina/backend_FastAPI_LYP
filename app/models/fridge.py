from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Fridge(Base):
    """
    Modèle Fridge unifié - Représente le frigo physique (kiosk) ET logique

    WORKFLOW SIMPLIFIÉ:
    1. init_kiosk() : Crée un Fridge avec kiosk_id et pairing_code
    2. pair_fridge() : Associe le Fridge à un utilisateur
    3. heartbeat : Maintient la connexion active

    Un Fridge = UN kiosk Samsung physique
    """

    __tablename__ = "fridges"

    # Identifiants
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )  # NULL avant pairing

    # Informations utilisateur
    name = Column(String, nullable=False, default="Mon Frigo")
    location = Column(String)
    
    device_id = Column(String, unique=True, index=True)

    # Informations du kiosk physique
    kiosk_id = Column(
        String, unique=True, nullable=False, index=True
    )  # UUID unique du kiosk
    device_name = Column(String)  # Nom du kiosk (ex: "Samsung Family Hub")

    # Pairing
    pairing_code = Column(String, unique=True, index=True)  # Code 6 chiffres temporaire
    is_paired = Column(Boolean, default=False)
    paired_at = Column(DateTime)

    # Heartbeat
    last_heartbeat = Column(DateTime)

    # Métadonnées du kiosk (IP, firmware, etc.)
    kiosk_metadata = Column(JSON, default=dict)

    # Configuration
    config = Column(JSON, default=dict)

    # Dates
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
    
    recipes = relationship(
        "Recipe", 
        back_populates="fridge", 
        cascade="all, delete-orphan"
    )
    
    favorite_recipes = relationship(
        "RecipeFavorite",
        back_populates="fridge",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        status = "PAIRED" if self.is_paired else "UNPAIRED"
        return f"<Fridge(id={self.id}, kiosk_id={self.kiosk_id}, status={status})>"
