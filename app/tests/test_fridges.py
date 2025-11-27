"""Tests des frigos"""

import pytest


def test_create_fridge(client, auth_headers):
    """Test de création d'un frigo"""
    response = client.post(
        "/api/v1/fridges",
        headers=auth_headers,
        json={"name": "My Fridge", "location": "Kitchen"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Fridge"
    assert data["location"] == "Kitchen"


def test_list_fridges(client, auth_headers, test_fridge):
    """Test de liste des frigos"""
    response = client.get("/api/v1/fridges", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == test_fridge.id


def test_get_fridge(client, auth_headers, test_fridge):
    """Test de récupération d'un frigo"""
    response = client.get(f"/api/v1/fridges/{test_fridge.id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_fridge.id


def test_get_fridge_not_owner(client, auth_headers_user2, test_fridge):
    """Test d'accès à un frigo non possédé (RG2)"""
    response = client.get(
        f"/api/v1/fridges/{test_fridge.id}", headers=auth_headers_user2
    )
    assert response.status_code == 404


def test_update_fridge(client, auth_headers, test_fridge):
    """Test de mise à jour d'un frigo"""
    response = client.put(
        f"/api/v1/fridges/{test_fridge.id}",
        headers=auth_headers,
        json={"name": "Updated Fridge"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Fridge"


def test_delete_fridge(client, auth_headers, test_fridge):
    """Test de suppression d'un frigo"""
    response = client.delete(f"/api/v1/fridges/{test_fridge.id}", headers=auth_headers)
    assert response.status_code == 204
