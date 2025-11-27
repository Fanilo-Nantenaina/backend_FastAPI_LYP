from sqlalchemy import Column, Integer, String, ARRAY, JSON, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class User(Base):
    """
    Modèle User - Utilisateur de l'application
    CU1: Gérer le Profil et les Préférences
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String)
    timezone = Column(String, default="UTC")

    # CU1: Préférences utilisateur
    preferred_cuisine = Column(String)  # Cuisine préférée (italienne, française, etc.)
    dietary_restrictions = Column(
        ARRAY(String), default=list
    )  # RG14: Restrictions alimentaires
    prefs = Column(JSON, default=dict)  # Autres préférences en JSON

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
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
