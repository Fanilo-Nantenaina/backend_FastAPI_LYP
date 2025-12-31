from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Fridge(Base):
    __tablename__ = "fridges"

                  
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )                      

                              
    name = Column(String, nullable=False, default="Mon Frigo")
    location = Column(String)
    
    device_id = Column(String, unique=True, index=True)

                                    
    kiosk_id = Column(
        String, unique=True, nullable=False, index=True
    )                        
    device_name = Column(String)                                           

             
    pairing_code = Column(String, unique=True, index=True)                              
    is_paired = Column(Boolean, default=False)
    paired_at = Column(DateTime)

               
    last_heartbeat = Column(DateTime)

                                               
    kiosk_metadata = Column(JSON, default=dict)

                   
    config = Column(JSON, default=dict)

           
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

               
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
