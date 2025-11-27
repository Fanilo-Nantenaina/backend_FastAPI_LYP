from sqlalchemy import Column, Integer, String, ARRAY, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class Product(Base):
    """
    Modèle Product - Catalogue de produits
    RG3: Catalogue centralisé des produits
    """

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    barcode = Column(String, unique=True, index=True)  # Code-barres EAN, UPC, etc.
    name = Column(String, nullable=False, index=True)
    category = Column(String, index=True)  # Fruits, Légumes, Laitages, Viandes, etc.

    # Informations nutritionnelles et conservation
    shelf_life_days = Column(Integer)  # Durée de conservation estimée
    default_unit = Column(String, default="piece")  # piece, kg, L, etc.

    # Métadonnées
    image_url = Column(String)
    tags = Column(
        ARRAY(String), default=list
    )  # vegan, gluten-free, dairy, etc. (pour RG14)
    metadata = Column(JSON, default=dict)  # Informations supplémentaires

    # Relations
    inventory_items = relationship("InventoryItem", back_populates="product")
    recipe_ingredients = relationship("RecipeIngredient", back_populates="product")
    shopping_list_items = relationship("ShoppingListItem", back_populates="product")

    def __repr__(self):
        return f"<Product(id={self.id}, name={self.name}, category={self.category})>"
