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

    # Relations
    ingredients = relationship(
        "RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan"
    )
    favorites = relationship(
        "RecipeFavorite", back_populates="recipe", cascade="all, delete-orphan"
    )

    shopping_lists = relationship("ShoppingList", back_populates="recipe")

    def __repr__(self):
        return f"<Recipe(id={self.id}, title={self.title})>"


class RecipeIngredient(Base):
    """
    Modèle RecipeIngredient - Ingrédients d'une recette
    Table de liaison entre Recipe et Product
    """

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

    # Relations
    recipe = relationship("Recipe", back_populates="ingredients")
    product = relationship("Product", back_populates="recipe_ingredients")

    def __repr__(self):
        return f"<RecipeIngredient(recipe_id={self.recipe_id}, product_id={self.product_id})>"


class RecipeFavorite(Base):
    """
    Modèle RecipeFavorite - Recettes favorites des utilisateurs
    RG16: Un utilisateur ne peut pas ajouter deux fois la même recette
    """

    __tablename__ = "recipe_favorites"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    recipe_id = Column(
        Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    user = relationship("User", back_populates="favorite_recipes")
    recipe = relationship("Recipe", back_populates="favorites")

    def __repr__(self):
        return f"<RecipeFavorite(user_id={self.user_id}, recipe_id={self.recipe_id})>"
