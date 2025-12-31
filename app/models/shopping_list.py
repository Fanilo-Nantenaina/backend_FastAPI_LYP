                                                           

from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class ShoppingList(Base):
    __tablename__ = "shopping_lists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    fridge_id = Column(
        Integer, ForeignKey("fridges.id", ondelete="CASCADE"), nullable=False
    )

                                                     
    recipe_id = Column(
        Integer, ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
    )

    name = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    generated_by = Column(String)                                            

                                  
    status = Column(String, default="active")                                      
    completed_at = Column(DateTime, nullable=True)

               
    user = relationship("User", back_populates="shopping_lists")
    fridge = relationship("Fridge", back_populates="shopping_lists")
    recipe = relationship("Recipe", back_populates="shopping_lists")           
    items = relationship(
        "ShoppingListItem", back_populates="shopping_list", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<ShoppingList(id={self.id}, user_id={self.user_id}, fridge_id={self.fridge_id})>"


class ShoppingListItem(Base):
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
    status = Column(String, default="pending")                                 

               
    shopping_list = relationship("ShoppingList", back_populates="items")
    product = relationship("Product", back_populates="shopping_list_items")

    def __repr__(self):
        return f"<ShoppingListItem(id={self.id}, product_id={self.product_id}, status={self.status})>"
