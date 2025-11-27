"""
SQLAlchemy models
"""

from app.models.user import User
from app.models.fridge import Fridge
from app.models.product import Product
from app.models.inventory import InventoryItem
from app.models.event import Event
from app.models.alert import Alert
from app.models.recipe import Recipe, RecipeIngredient, RecipeFavorite
from app.models.shopping_list import ShoppingList, ShoppingListItem
from app.models.device import FridgeDevice

__all__ = [
    "User",
    "Fridge",
    "Product",
    "InventoryItem",
    "Event",
    "Alert",
    "Recipe",
    "RecipeIngredient",
    "RecipeFavorite",
    "ShoppingList",
    "ShoppingListItem",
    "FridgeDevice",
]
