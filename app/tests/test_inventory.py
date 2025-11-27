"""Tests de l'inventaire"""

import pytest
from datetime import date, timedelta


def test_add_inventory_item(client, auth_headers, test_fridge, test_product):
    """CU2: Test d'ajout d'un item à l'inventaire"""
    response = client.post(
        f"/api/v1/fridges/{test_fridge.id}/inventory",
        headers=auth_headers,
        json={
            "product_id": test_product.id,
            "quantity": 5,
            "unit": "piece",
            "expiry_date": str(date.today() + timedelta(days=7)),
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["quantity"] == 5
    assert data["product_id"] == test_product.id


def test_list_inventory(client, auth_headers, test_fridge, test_inventory_item):
    """Test de liste de l'inventaire"""
    response = client.get(
        f"/api/v1/fridges/{test_fridge.id}/inventory", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


def test_consume_item(client, auth_headers, test_fridge, test_inventory_item):
    """CU3: Test de consommation d'un item (RG8, RG9)"""
    response = client.post(
        f"/api/v1/fridges/{test_fridge.id}/inventory/{test_inventory_item.id}/consume",
        headers=auth_headers,
        json={"quantity_consumed": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 7  # 10 - 3


def test_consume_item_excessive(client, auth_headers, test_fridge, test_inventory_item):
    """Test de consommation excessive (RG9: quantité négative interdite)"""
    response = client.post(
        f"/api/v1/fridges/{test_fridge.id}/inventory/{test_inventory_item.id}/consume",
        headers=auth_headers,
        json={"quantity_consumed": 15},  # Plus que disponible
    )
    assert response.status_code == 400


def test_update_inventory_item(client, auth_headers, test_fridge, test_inventory_item):
    """Test de mise à jour d'un item"""
    new_date = str(date.today() + timedelta(days=10))
    response = client.put(
        f"/api/v1/fridges/{test_fridge.id}/inventory/{test_inventory_item.id}",
        headers=auth_headers,
        json={"expiry_date": new_date},
    )
    assert response.status_code == 200
