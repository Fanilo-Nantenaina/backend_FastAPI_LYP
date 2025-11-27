"""
API v1 routes
"""

from fastapi import APIRouter
from app.api.v1 import (
    auth,
    users,
    fridges,
    products,
    inventory,
    vision,
    alerts,
    recipes,
    shopping_lists,
    events,
    devices,
)

api_router = APIRouter()

# Inclure tous les routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(fridges.router, prefix="/fridges", tags=["Fridges"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(inventory.router, prefix="/fridges", tags=["Inventory"])
api_router.include_router(vision.router, prefix="/fridges", tags=["Vision AI"])
api_router.include_router(alerts.router, prefix="/fridges", tags=["Alerts"])
api_router.include_router(recipes.router, prefix="/recipes", tags=["Recipes"])
api_router.include_router(
    shopping_lists.router, prefix="/shopping-lists", tags=["Shopping Lists"]
)
api_router.include_router(events.router, prefix="/fridges", tags=["Events"])
api_router.include_router(devices.router, prefix="/fridges", tags=["Devices"])

__all__ = ["api_router"]
