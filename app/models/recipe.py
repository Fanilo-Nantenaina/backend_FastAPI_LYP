from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON, DateTime, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Recipe(Base):
    """Modèle Recipe - Recettes de cuisine"""

    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    description = Column(Text)
    steps = Column(Text)
    preparation_time = Column(Integer)
    difficulty = Column(String)
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    fridge_id = Column(
        Integer, ForeignKey("fridges.id", ondelete="CASCADE"), nullable=True, index=True
    )

    fridge = relationship("Fridge", back_populates="recipes")
    ingredients = relationship(
        "RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan"
    )
    favorites = relationship(
        "RecipeFavorite", back_populates="recipe", cascade="all, delete-orphan"
    )
    shopping_lists = relationship("ShoppingList", back_populates="recipe")

    def __repr__(self):
        return f"<Recipe(id={self.id}, title={self.title}, fridge_id={self.fridge_id})>"


class RecipeIngredient(Base):
    """Modèle RecipeIngredient - Ingrédients d'une recette"""

    __tablename__ = "recipe_ingredients"

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(
        Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    quantity = Column(Float)
    unit = Column(String)

    recipe = relationship("Recipe", back_populates="ingredients")
    product = relationship("Product", back_populates="recipe_ingredients")

    def __repr__(self):
        return f"<RecipeIngredient(recipe_id={self.recipe_id}, product_id={self.product_id})>"


class RecipeFavorite(Base):
    """Modèle RecipeFavorite - Recettes favorites des utilisateurs

    MODIFIÉ : Ajout de fridge_id pour avoir des favoris par frigo
    RG16: Un utilisateur ne peut pas ajouter deux fois la même recette (par frigo)
    """

    __tablename__ = "recipe_favorites"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    recipe_id = Column(
        Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )

    fridge_id = Column(
        Integer,
        ForeignKey("fridges.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="favorite_recipes")
    recipe = relationship("Recipe", back_populates="favorites")
    fridge = relationship("Fridge", back_populates="favorite_recipes")

    def __repr__(self):
        return f"<RecipeFavorite(user_id={self.user_id}, recipe_id={self.recipe_id}, fridge_id={self.fridge_id})>"
