from sqlalchemy import Column, Integer, String, ARRAY, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    barcode = Column(String, unique=True, index=True)
    name = Column(String, nullable=False, index=True)
    category = Column(String, index=True)

                                                  
    shelf_life_days = Column(Integer, default=7)                                 
    default_unit = Column(String, default="piece")                      

                 
    image_url = Column(String)
    tags = Column(
        ARRAY(String), default=list
    )                                               

    extra_data = Column(JSON, default=dict)              

               
    inventory_items = relationship("InventoryItem", back_populates="product")
    recipe_ingredients = relationship("RecipeIngredient", back_populates="product")
    shopping_list_items = relationship("ShoppingListItem", back_populates="product")

    def __repr__(self):
        return f"<Product(id={self.id}, name={self.name}, category={self.category})>"
