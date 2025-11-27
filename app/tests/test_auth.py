"""Tests d'authentification"""

import pytest


def test_register_user(client):
    """Test de l'inscription d'un nouvel utilisateur"""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "name": "New User",
            "password": "securepass123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_register_duplicate_email(client, test_user):
    """Test d'inscription avec un email déjà utilisé"""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": test_user.email,
            "name": "Duplicate User",
            "password": "securepass123",
        },
    )
    assert response.status_code == 400


def test_login_success(client, test_user):
    """Test de connexion réussie"""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "testpass123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password(client, test_user):
    """Test de connexion avec mauvais mot de passe"""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_login_non_existent_user(client):
    """Test de connexion avec utilisateur inexistant"""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "anypassword"},
    )
    assert response.status_code == 401
