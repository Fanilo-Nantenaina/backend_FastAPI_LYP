"""Tests des utilisateurs"""

import pytest


def test_get_current_user(client, auth_headers, test_user):
    """Test de récupération du profil utilisateur"""
    response = client.get("/api/v1/users/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
    assert data["name"] == test_user.name


def test_get_current_user_unauthorized(client):
    """Test sans authentification"""
    response = client.get("/api/v1/users/me")
    assert response.status_code == 403


def test_update_user_profile(client, auth_headers):
    """Test de mise à jour du profil"""
    response = client.put(
        "/api/v1/users/me",
        headers=auth_headers,
        json={"name": "Updated Name", "preferred_cuisine": "Italian"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["preferred_cuisine"] == "Italian"
