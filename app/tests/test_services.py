"""Tests des services"""

import pytest
from datetime import date, timedelta


def test_inventory_service_add_item(db, test_fridge, test_product):
    """Test du service d'inventaire"""
    from app.services.inventory_service import InventoryService

    service = InventoryService(db)
    item = service.add_item(
        fridge_id=test_fridge.id, product_id=test_product.id, quantity=5.0
    )

    assert item.id is not None
    assert item.quantity == 5.0


def test_inventory_service_consume(db, test_inventory_item):
    """Test de consommation via le service"""
    from app.services.inventory_service import InventoryService

    service = InventoryService(db)
    item = service.consume_item(test_inventory_item.id, 3.0)

    assert item.quantity == 7.0


def test_fridge_service_statistics(db, test_fridge):
    """Test des statistiques de frigo"""
    from app.services.fridge_service import FridgeService

    service = FridgeService(db)
    stats = service.get_fridge_statistics(test_fridge.id)

    assert "active_items" in stats
    assert "pending_alerts" in stats
