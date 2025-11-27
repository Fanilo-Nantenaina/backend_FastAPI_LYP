from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import engine, Base
from app.tasks.scheduler import start_scheduler, stop_scheduler

# Import des routes
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    # Startup
    print("🚀 Démarrage de l'application...")

    # Créer les tables (en production, utiliser Alembic)
    Base.metadata.create_all(bind=engine)

    # Démarrer le scheduler pour les alertes
    start_scheduler()
    print("⏰ Scheduler démarré pour les alertes périodiques")

    yield

    # Shutdown
    print("🛑 Arrêt de l'application...")
    stop_scheduler()


app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production : spécifier les domaines autorisés
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(fridges.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(inventory.router, prefix="/api/v1")
app.include_router(vision.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(recipes.router, prefix="/api/v1")
app.include_router(shopping_lists.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(devices.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "Smart Fridge API", "version": settings.VERSION, "docs": "/docs"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
