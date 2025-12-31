from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import engine, Base
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.utils.exceptions import FridgeNotFoundError


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
    search,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Démarrage de l'application...")

    Base.metadata.create_all(bind=engine)

    start_scheduler()
    print("Scheduler démarré pour les alertes périodiques")

    yield

    print("Arrêt de l'application...")
    stop_scheduler()


app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)


origins = settings.ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


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
app.include_router(search.router, prefix="/api/v1")


@app.exception_handler(FridgeNotFoundError)
async def fridge_not_found_handler(request: Request, exc: FridgeNotFoundError):
    return JSONResponse(
        status_code=404,
        content={
            "error": "fridge_not_found",
            "message": f"Fridge {exc.fridge_id} not found or access denied",
            "fridge_id": exc.fridge_id,
        },
    )


@app.get("/")
async def root():
    return {"message": "Smart Fridge API", "version": settings.VERSION, "docs": "/docs"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
