"""Tests des recettes"""

import pytest


def test_list_recipes(client):
    """Test de liste des recettes"""
    response = client.get("/api/v1/recipes")
    assert response.status_code == 200


def test_create_recipe(client, auth_headers, test_product):
    """Test de création d'une recette"""
    response = client.post(
        "/api/v1/recipes",
        headers=auth_headers,
        json={
            "title": "Test Recipe",
            "description": "A test recipe",
            "steps": "1. Mix\n2. Cook",
            "difficulty": "easy",
            "ingredients": [
                {"product_id": test_product.id, "quantity": 2, "unit": "piece"}
            ],
        },
    )
    assert response.status_code == 201


def test_dietary_restrictions(db, test_user, test_fridge, test_product):
    """Test RG14: Restrictions alimentaires"""
    from app.models.recipe import Recipe, RecipeIngredient
    from app.services.recipe_service import RecipeService

    # Créer une recette avec un produit contenant lactose
    recipe = Recipe(title="Milk Recipe", difficulty="easy")
    db.add(recipe)
    db.flush()

    # Marquer le produit avec le tag lactose
    test_product.tags = ["lactose"]
    db.commit()

    ingredient = RecipeIngredient(
        recipe_id=recipe.id, product_id=test_product.id, quantity=1, unit="piece"
    )
    db.add(ingredient)
    db.commit()

    # test_user a la restriction lactose
    recipe_service = RecipeService(db)
    feasible = recipe_service.find_feasible_recipes(test_fridge.id, test_user)

    # La recette ne devrait PAS être dans les résultats
    recipe_ids = [f["recipe"].id for f in feasible]
    assert recipe.id not in recipe_ids
