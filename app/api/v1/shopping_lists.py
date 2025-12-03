from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict
from datetime import datetime

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.fridge import Fridge
from app.models.product import Product
from app.models.recipe import Recipe
from app.models.shopping_list import ShoppingList, ShoppingListItem
from app.schemas.shopping_list import (
    ShoppingListResponse,
    ShoppingListCreate,
    ShoppingListItemCreate,
    GenerateShoppingListRequest,
    GenerateFromIngredientsRequest,
)
from app.services.shopping_service import ShoppingService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shopping-lists", tags=["Shopping Lists"])


def _enrich_shopping_list_response(shopping_list: ShoppingList, db: Session) -> Dict:
    """Enrichit la réponse avec les noms de produits"""
    items = []
    for item in shopping_list.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()

        items.append(
            {
                "id": item.id,
                "shopping_list_id": item.shopping_list_id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit": item.unit,
                "status": item.status,
                "product_name": (
                    product.name if product else f"Produit #{item.product_id}"
                ),
            }
        )

    return {
        "id": shopping_list.id,
        "user_id": shopping_list.user_id,
        "fridge_id": shopping_list.fridge_id,
        "name": shopping_list.name,
        "created_at": shopping_list.created_at,
        "generated_by": shopping_list.generated_by,
        "items": items,
    }


@router.post("", response_model=ShoppingListResponse, status_code=201)
def create_shopping_list(
    request: ShoppingListCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    CU4: Créer manuellement une liste de courses

    ✅ AMÉLIORÉ : Accepte les articles personnalisés (sans product_id)
    - Si product_id fourni : utilise le produit existant
    - Si product_name fourni : crée le produit ou trouve un existant
    """
    fridge = (
        db.query(Fridge)
        .filter(Fridge.id == request.fridge_id, Fridge.user_id == current_user.id)
        .first()
    )

    if not fridge:
        raise HTTPException(
            status_code=404, detail="Fridge not found or access denied (RG13)"
        )

    shopping_list = ShoppingList(
        user_id=current_user.id,
        fridge_id=request.fridge_id,
        generated_by="manual",
        name=request.name,
    )

    db.add(shopping_list)
    db.flush()

    for item_data in request.items:
        product_id = item_data.product_id

        # ✅ Si pas de product_id, chercher ou créer le produit par son nom
        if product_id is None and item_data.product_name:
            product_name = item_data.product_name.strip()

            # Chercher un produit existant avec ce nom (insensible à la casse)
            existing_product = (
                db.query(Product).filter(Product.name.ilike(product_name)).first()
            )

            if existing_product:
                product_id = existing_product.id
            else:
                # Créer un nouveau produit
                new_product = Product(
                    name=product_name.capitalize(),
                    category="Divers",
                    default_unit=item_data.unit or "pièce",
                    shelf_life_days=7,
                )
                db.add(new_product)
                db.flush()
                product_id = new_product.id

        # Créer l'item de la liste
        if product_id:
            item = ShoppingListItem(
                shopping_list_id=shopping_list.id,
                product_id=product_id,
                quantity=item_data.quantity,
                unit=item_data.unit,
                status="pending",
            )
            db.add(item)

    db.commit()
    db.refresh(shopping_list)
    return _enrich_shopping_list_response(shopping_list, db)


@router.post("/generate", response_model=ShoppingListResponse, status_code=201)
def generate_shopping_list(
    request: GenerateShoppingListRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fridge = (
        db.query(Fridge)
        .filter(Fridge.id == request.fridge_id, Fridge.user_id == current_user.id)
        .first()
    )

    if not fridge:
        raise HTTPException(status_code=404, detail="Fridge not found or access denied")

    # ✅ Déterminer le nom ET le recipe_id AVANT la génération
    shopping_list_name = "Liste personnalisée"
    recipe_id = None

    if request.recipe_ids:
        if len(request.recipe_ids) == 1:
            recipe = db.query(Recipe).filter(Recipe.id == request.recipe_ids[0]).first()
            if recipe:
                shopping_list_name = recipe.title
                recipe_id = recipe.id  # ✅ Défini ICI
        else:
            shopping_list_name = f"Liste pour {len(request.recipe_ids)} recettes"

    shopping_service = ShoppingService(db)

    # ✅ MODIFIÉ : Passer recipe_id directement au service
    shopping_list = shopping_service.generate_shopping_list(
        user_id=current_user.id,
        fridge_id=request.fridge_id,
        recipe_ids=request.recipe_ids,
        name=shopping_list_name,
        recipe_id=recipe_id,  # ✅ NOUVEAU paramètre
    )

    # Plus besoin d'assigner manuellement
    db.commit()
    db.refresh(shopping_list)

    logger.info(
        f"📋 Shopping list created: id={shopping_list.id}, "
        f"name={shopping_list.name}, recipe_id={shopping_list.recipe_id}"
    )

    return _enrich_shopping_list_response(shopping_list, db)


@router.post("/{list_id}/complete")
def complete_shopping_list(
    list_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Marque une liste comme complétée"""
    shopping_list = (
        db.query(ShoppingList)
        .filter(ShoppingList.id == list_id, ShoppingList.user_id == current_user.id)
        .first()
    )

    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    # Marquer tous les items comme purchased
    db.query(ShoppingListItem).filter(
        ShoppingListItem.shopping_list_id == list_id,
        ShoppingListItem.status == "pending",
    ).update({"status": "purchased"})

    # Marquer la liste comme complétée
    shopping_list.status = "completed"
    shopping_list.completed_at = datetime.utcnow()

    db.commit()

    return {
        "message": "Liste complétée",
        "status": "completed",
        "completed_at": shopping_list.completed_at.isoformat(),
    }


@router.post(
    "/generate-from-ingredients", response_model=ShoppingListResponse, status_code=201
)
def generate_shopping_list_from_ingredients(
    request: GenerateFromIngredientsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    🆕 Génère une liste de courses depuis des ingrédients bruts (suggestion IA)
    ✅ CORRIGÉ : Accepte maintenant un recipe_id optionnel
    """
    # Vérifier que le frigo appartient à l'utilisateur
    fridge = (
        db.query(Fridge)
        .filter(Fridge.id == request.fridge_id, Fridge.user_id == current_user.id)
        .first()
    )

    if not fridge:
        raise HTTPException(status_code=404, detail="Fridge not found or access denied")

    # Créer la liste de courses
    shopping_list = ShoppingList(
        user_id=current_user.id,
        fridge_id=request.fridge_id,
        generated_by="ai_suggestion",
        recipe_id=request.recipe_id,
    )

    if request.recipe_id:
        recipe = db.query(Recipe).filter(Recipe.id == request.recipe_id).first()
        if recipe:
            shopping_list.name = recipe.title

    db.add(shopping_list)
    db.flush()

    items_added = 0

    for ingredient in request.ingredients:
        ingredient_name = ingredient.get("name", "").strip()
        if not ingredient_name:
            continue

        # Chercher le produit dans la base de données
        product = (
            db.query(Product).filter(Product.name.ilike(f"%{ingredient_name}%")).first()
        )

        # Si le produit n'existe pas, le créer
        if not product:
            product = Product(
                name=ingredient_name.capitalize(),
                category="Divers",
                default_unit=ingredient.get("unit", "pièce"),
            )
            db.add(product)
            db.flush()

        # Ajouter l'item à la liste
        item = ShoppingListItem(
            shopping_list_id=shopping_list.id,
            product_id=product.id,
            quantity=ingredient.get("quantity", 1),
            unit=ingredient.get("unit", product.default_unit),
            status="pending",
        )
        db.add(item)
        items_added += 1

    db.commit()
    db.refresh(shopping_list)

    logger.info(
        f"✅ Created shopping list {shopping_list.id} with {items_added} items, "
        f"recipe_id={shopping_list.recipe_id}"
    )

    return shopping_list


@router.get("", response_model=List[Dict])
def list_shopping_lists(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    fridge_id: int = None,
    sort_by: str = "date",  # ✅ NOUVEAU : date, name, status
    order: str = "desc",  # ✅ NOUVEAU : asc, desc
):
    query = db.query(ShoppingList).filter(ShoppingList.user_id == current_user.id)

    if fridge_id:
        query = query.filter(ShoppingList.fridge_id == fridge_id)

    # ✅ AJOUT : Tri dynamique
    if sort_by == "name":
        query = query.order_by(
            ShoppingList.name.desc() if order == "desc" else ShoppingList.name.asc()
        )
    elif sort_by == "status":
        query = query.order_by(
            ShoppingList.status.desc() if order == "desc" else ShoppingList.status.asc()
        )
    else:  # date par défaut
        query = query.order_by(
            ShoppingList.created_at.desc()
            if order == "desc"
            else ShoppingList.created_at.asc()
        )

    lists = query.all()
    return [_enrich_shopping_list_response(lst, db) for lst in lists]


# ✅ MODIFIER la route get_shopping_list
@router.get("/{list_id}", response_model=Dict)  # Dict au lieu de ShoppingListResponse
def get_shopping_list(
    list_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Récupère une liste de courses spécifique"""
    shopping_list = (
        db.query(ShoppingList)
        .filter(ShoppingList.id == list_id, ShoppingList.user_id == current_user.id)
        .first()
    )

    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    # ✅ Enrichir avec les noms de produits
    return _enrich_shopping_list_response(shopping_list, db)


@router.put("/{list_id}/items/{item_id}/status")
def update_item_status(
    list_id: int,
    item_id: int,
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Marquer un item comme acheté/pending/annulé"""
    shopping_list = (
        db.query(ShoppingList)
        .filter(ShoppingList.id == list_id, ShoppingList.user_id == current_user.id)
        .first()
    )

    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    item = (
        db.query(ShoppingListItem)
        .filter(
            ShoppingListItem.id == item_id, ShoppingListItem.shopping_list_id == list_id
        )
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    status = request.get("status", "").lower()

    if status not in ["pending", "purchased", "cancelled"]:
        raise HTTPException(status_code=400, detail="Invalid status value")

    item.status = status

    # ✅ NOUVEAU : Mettre à jour automatiquement le statut de la liste
    all_items = (
        db.query(ShoppingListItem)
        .filter(ShoppingListItem.shopping_list_id == list_id)
        .all()
    )

    # Vérifier si tous les items sont "purchased"
    all_purchased = all(i.status == "purchased" for i in all_items)
    any_pending = any(i.status == "pending" for i in all_items)

    if all_purchased and len(all_items) > 0:
        shopping_list.status = "completed"
        shopping_list.completed_at = datetime.utcnow()
    elif any_pending:
        shopping_list.status = "active"
        shopping_list.completed_at = None

    db.commit()

    return {
        "message": "Item status updated",
        "new_status": status,
        "list_status": shopping_list.status,
    }


@router.post("/{list_id}/mark-all-purchased")
def mark_all_as_purchased(
    list_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Marque tous les items pending comme purchased"""
    shopping_list = (
        db.query(ShoppingList)
        .filter(ShoppingList.id == list_id, ShoppingList.user_id == current_user.id)
        .first()
    )

    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    updated_count = (
        db.query(ShoppingListItem)
        .filter(
            ShoppingListItem.shopping_list_id == list_id,
            ShoppingListItem.status == "pending",
        )
        .update({"status": "purchased"})
    )

    # ✅ NOUVEAU : Mettre à jour le statut de la liste
    shopping_list.status = "completed"
    shopping_list.completed_at = datetime.utcnow()

    db.commit()

    return {
        "message": f"{updated_count} item(s) marqué(s) comme achetés",
        "updated_count": updated_count,
        "list_status": "completed",
    }


@router.post("/{list_id}/items", status_code=201)
def add_item_to_list(
    list_id: int,
    item_data: ShoppingListItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Ajouter un item à une liste existante

    ✅ AMÉLIORÉ : Accepte product_id OU product_name
    """
    shopping_list = (
        db.query(ShoppingList)
        .filter(ShoppingList.id == list_id, ShoppingList.user_id == current_user.id)
        .first()
    )

    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    product_id = item_data.product_id

    # ✅ Si pas de product_id, chercher ou créer le produit par son nom
    if product_id is None and item_data.product_name:
        product_name = item_data.product_name.strip()

        # Chercher un produit existant avec ce nom (insensible à la casse)
        existing_product = (
            db.query(Product).filter(Product.name.ilike(product_name)).first()
        )

        if existing_product:
            product_id = existing_product.id
        else:
            # Créer un nouveau produit
            new_product = Product(
                name=product_name.capitalize(),
                category="Divers",
                default_unit=item_data.unit or "pièce",
                shelf_life_days=7,
            )
            db.add(new_product)
            db.flush()
            product_id = new_product.id

    if not product_id:
        raise HTTPException(
            status_code=400,
            detail="Vous devez fournir soit product_id, soit product_name",
        )

    # Vérifier si l'item existe déjà dans la liste
    existing_item = (
        db.query(ShoppingListItem)
        .filter(
            ShoppingListItem.shopping_list_id == list_id,
            ShoppingListItem.product_id == product_id,
        )
        .first()
    )

    if existing_item:
        # ✅ Si l'item existe déjà, augmenter la quantité
        existing_item.quantity += item_data.quantity
        db.commit()
        return {"message": "Quantité mise à jour", "item_id": existing_item.id}

    # Créer le nouvel item
    item = ShoppingListItem(
        shopping_list_id=list_id,
        product_id=product_id,
        quantity=item_data.quantity,
        unit=item_data.unit,
        status="pending",
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    return {"message": "Item added", "item_id": item.id}


@router.delete("/{list_id}/items/{item_id}", status_code=204)
def delete_shopping_list_item(
    list_id: int,
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Supprimer un item spécifique de la liste de courses"""
    shopping_list = (
        db.query(ShoppingList)
        .filter(ShoppingList.id == list_id, ShoppingList.user_id == current_user.id)
        .first()
    )

    if not shopping_list:
        raise HTTPException(
            status_code=404, detail="Shopping list not found or access denied"
        )

    item = (
        db.query(ShoppingListItem)
        .filter(
            ShoppingListItem.id == item_id, ShoppingListItem.shopping_list_id == list_id
        )
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Item not found in this list")

    db.delete(item)
    db.commit()
    return None


@router.delete("/{list_id}", status_code=204)
def delete_shopping_list(
    list_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Supprimer une liste de courses et tous ses items"""
    shopping_list = (
        db.query(ShoppingList)
        .filter(ShoppingList.id == list_id, ShoppingList.user_id == current_user.id)
        .first()
    )

    if not shopping_list:
        raise HTTPException(
            status_code=404, detail="Shopping list not found or access denied"
        )

    db.delete(shopping_list)
    db.commit()

    return None
