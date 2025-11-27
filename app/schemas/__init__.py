"""
Pydantic schemas for request/response validation
"""

from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserResponse, UserUpdateRequest
from app.schemas.fridge import FridgeCreate, FridgeUpdate, FridgeResponse
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse
from app.schemas.inventory import (
    InventoryItemCreate,
    InventoryItemUpdate,
    InventoryItemResponse,
    ConsumeItemRequest,
)
from app.schemas.vision import (
    VisionAnalysisResponse,
    ManualEntryRequest,
    DetectedProduct,
)
from app.schemas.alert import AlertResponse, AlertUpdateRequest
from app.schemas.event import EventResponse
from app.schemas.recipe import (
    RecipeCreate,
    RecipeResponse,
    RecipeIngredientResponse,
    FeasibleRecipeResponse,
)
from app.schemas.shopping_list import (
    ShoppingListCreate,
    ShoppingListResponse,
    GenerateShoppingListRequest,
)
from app.schemas.device import (
    PairingCodeResponse,
    PairingRequest,
    PairingResponse,
    DeviceResponse,
)

__all__ = [
    # Auth
    "LoginRequest",
    "RegisterRequest",
    "TokenResponse",
    # User
    "UserResponse",
    "UserUpdateRequest",
    # Fridge
    "FridgeCreate",
    "FridgeUpdate",
    "FridgeResponse",
    # Product
    "ProductCreate",
    "ProductUpdate",
    "ProductResponse",
    # Inventory
    "InventoryItemCreate",
    "InventoryItemUpdate",
    "InventoryItemResponse",
    "ConsumeItemRequest",
    # Vision
    "VisionAnalysisResponse",
    "ManualEntryRequest",
    "DetectedProduct",
    # Alert
    "AlertResponse",
    "AlertUpdateRequest",
    # Event
    "EventResponse",
    # Recipe
    "RecipeCreate",
    "RecipeResponse",
    "RecipeIngredientResponse",
    "FeasibleRecipeResponse",
    # Shopping List
    "ShoppingListCreate",
    "ShoppingListResponse",
    "GenerateShoppingListRequest",
    # Device
    "PairingCodeResponse",
    "PairingRequest",
    "PairingResponse",
    "DeviceResponse",
]
