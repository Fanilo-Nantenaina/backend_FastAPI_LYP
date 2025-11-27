"""Tests des listes de courses"""

import pytest


def test_create_shopping_list(client, auth_headers, test_fridge, test_product):
    """CU4: Test de création manuelle d'une liste"""
    response = client.post(
        "/api/v1/shopping-lists",
        headers=auth_headers,
        json={
            "fridge_id": test_fridge.id,
            "items": [{"product_id": test_product.id, "quantity": 5, "unit": "piece"}],
        },
    )
    assert response.status_code == 201


def test_generate_shopping_list(client, auth_headers, test_fridge):
    """CU4: Test de génération automatique (RG15)"""
    response = client.post(
        "/api/v1/shopping-lists/generate",
        headers=auth_headers,
        json={"fridge_id": test_fridge.id},
    )
    assert response.status_code == 201


def test_shopping_list_ownership(client, auth_headers_user2, test_fridge):
    """Test RG13: Vérification de propriété du frigo"""
    response = client.post(
        "/api/v1/shopping-lists/generate",
        headers=auth_headers_user2,
        json={"fridge_id": test_fridge.id},
    )
    assert response.status_code == 404  # User2 ne possède pas ce frigo
