# Dans models/shopping_list.py - Ajoutez le champ recipe_id

from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class ShoppingList(Base):
    """
    Modèle ShoppingList - Listes de courses
    AMÉLIORÉ : Ajout de la relation avec Recipe
    """

    __tablename__ = "shopping_lists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    fridge_id = Column(
        Integer, ForeignKey("fridges.id", ondelete="CASCADE"), nullable=False
    )

    # NOUVEAU : Relation optionnelle avec une recette
    recipe_id = Column(
        Integer, ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
    )

    name = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    generated_by = Column(String)  # 'manual', 'auto_recipe', 'ai_suggestion'

    # NOUVEAU : Statut de la liste
    status = Column(String, default="active")  # 'active', 'completed', 'cancelled'
    completed_at = Column(DateTime, nullable=True)

    # Relations
    user = relationship("User", back_populates="shopping_lists")
    fridge = relationship("Fridge", back_populates="shopping_lists")
    recipe = relationship("Recipe", back_populates="shopping_lists")  # NOUVEAU
    items = relationship(
        "ShoppingListItem", back_populates="shopping_list", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<ShoppingList(id={self.id}, user_id={self.user_id}, fridge_id={self.fridge_id})>"


class ShoppingListItem(Base):
    """Modèle ShoppingListItem - Articles d'une liste de courses"""

    __tablename__ = "shopping_list_items"

    id = Column(Integer, primary_key=True, index=True)
    shopping_list_id = Column(
        Integer, ForeignKey("shopping_lists.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    quantity = Column(Float)
    unit = Column(String)
    status = Column(String, default="pending")  # pending, purchased, cancelled

    # Relations
    shopping_list = relationship("ShoppingList", back_populates="items")
    product = relationship("Product", back_populates="shopping_list_items")

    def __repr__(self):
        return f"<ShoppingListItem(id={self.id}, product_id={self.product_id}, status={self.status})>"
