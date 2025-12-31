from sqlalchemy import Column, Integer, String, ARRAY, JSON, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String)
    timezone = Column(String, default="UTC")

                                  
    preferred_cuisine = Column(String)                                                 
    dietary_restrictions = Column(
        ARRAY(String), default=list
    )                                   
    prefs = Column(JSON, default=dict)                              

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

               
    fridges = relationship(
        "Fridge", back_populates="user", cascade="all, delete-orphan"
    )
    shopping_lists = relationship(
        "ShoppingList", back_populates="user", cascade="all, delete-orphan"
    )
    favorite_recipes = relationship(
        "RecipeFavorite", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, name={self.name})>"
