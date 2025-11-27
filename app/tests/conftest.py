"""Configuration et fixtures pytest"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import date, datetime

from app.core.database import Base, get_db
from app.main import app
from app.models.user import User
from app.models.fridge import Fridge
from app.models.product import Product
from app.models.inventory import InventoryItem
from app.core.security import get_password_hash, create_access_token

# Database de test en mémoire
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """Fixture de base de données pour les tests"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    """Fixture du client de test FastAPI"""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db):
    """Fixture d'un utilisateur de test"""
    user = User(
        email="test@example.com",
        name="Test User",
        password_hash=get_password_hash("testpass123"),
        timezone="UTC",
        dietary_restrictions=["lactose"],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_user2(db):
    """Fixture d'un second utilisateur"""
    user = User(
        email="test2@example.com",
        name="Test User 2",
        password_hash=get_password_hash("testpass123"),
        timezone="UTC",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_fridge(db, test_user):
    """Fixture d'un frigo de test"""
    fridge = Fridge(
        user_id=test_user.id,
        name="Test Fridge",
        location="Test Location",
        config={"expiry_warning_days": 3, "lost_item_threshold_hours": 72},
    )
    db.add(fridge)
    db.commit()
    db.refresh(fridge)
    return fridge


@pytest.fixture
def test_product(db):
    """Fixture d'un produit de test"""
    product = Product(
        name="Test Product",
        category="Test Category",
        shelf_life_days=7,
        default_unit="piece",
        tags=["test"],
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@pytest.fixture
def test_inventory_item(db, test_fridge, test_product):
    """Fixture d'un item d'inventaire"""
    item = InventoryItem(
        fridge_id=test_fridge.id,
        product_id=test_product.id,
        quantity=10.0,
        initial_quantity=10.0,
        unit="piece",
        expiry_date=date.today(),
        source="manual",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def auth_headers(test_user):
    """Fixture des headers d'authentification"""
    token = create_access_token({"sub": test_user.id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user2(test_user2):
    """Fixture des headers d'authentification pour user2"""
    token = create_access_token({"sub": test_user2.id})
    return {"Authorization": f"Bearer {token}"}
