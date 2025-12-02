from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.fridge import Fridge
from app.models.product import Product
from app.models.shopping_list import ShoppingList, ShoppingListItem
from app.schemas.shopping_list import (
    ShoppingListResponse,
    ShoppingListCreate,
    ShoppingListItemCreate,
    GenerateShoppingListRequest,
    GenerateFromIngredientsRequest,
)
from app.services.shopping_service import ShoppingService

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
                ),  # ✅
            }
        )

    return {
        "id": shopping_list.id,
        "user_id": shopping_list.user_id,
        "fridge_id": shopping_list.fridge_id,
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
    """CU4: Créer manuellement une liste de courses"""
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
        user_id=current_user.id, fridge_id=request.fridge_id, generated_by="manual"
    )
    db.add(shopping_list)
    db.flush()

    for item_data in request.items:
        item = ShoppingListItem(
            shopping_list_id=shopping_list.id,
            product_id=item_data.product_id,
            quantity=item_data.quantity,
            unit=item_data.unit,
            status="pending",
        )
        db.add(item)

    db.commit()
    db.refresh(shopping_list)
    return shopping_list


@router.post("/generate", response_model=ShoppingListResponse, status_code=201)
def generate_shopping_list(
    request: GenerateShoppingListRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    CU4: Générer automatiquement une liste de courses
    RG13: Vérifie que l'utilisateur possède le frigo
    RG15: Inclut seulement les produits en quantité insuffisante
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

    shopping_service = ShoppingService(db)

    shopping_list = shopping_service.generate_shopping_list(
        user_id=current_user.id,
        fridge_id=request.fridge_id,
        recipe_ids=request.recipe_ids,
    )

    return shopping_list


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

    Cette route est utilisée pour créer une liste de courses à partir
    des ingrédients manquants suggérés par l'IA pour une recette.

    Args:
        fridge_id: ID du frigo associé
        ingredients: Liste d'ingrédients avec nom, quantité et unité

    Returns:
        ShoppingListResponse avec les items créés
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
    )
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

    return shopping_list


# ✅ MODIFIER la route list_shopping_lists
@router.get("", response_model=List[Dict])  # Dict au lieu de ShoppingListResponse
def list_shopping_lists(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    fridge_id: int = None,
):
    """Liste toutes les listes de courses de l'utilisateur"""
    query = db.query(ShoppingList).filter(ShoppingList.user_id == current_user.id)

    if fridge_id:
        query = query.filter(ShoppingList.fridge_id == fridge_id)

    lists = query.order_by(ShoppingList.created_at.desc()).all()

    # ✅ Enrichir chaque liste avec les noms de produits
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
    request: dict,  # ✅ Accepter un body JSON
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

    # ✅ Extraire le statut du body
    status = request.get("status", "").lower()

    if status not in ["pending", "purchased", "cancelled"]:
        raise HTTPException(status_code=400, detail="Invalid status value")

    item.status = status
    db.commit()

    return {"message": "Item status updated", "new_status": status}


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

    # ✅ Mettre à jour tous les items pending
    updated_count = (
        db.query(ShoppingListItem)
        .filter(
            ShoppingListItem.shopping_list_id == list_id,
            ShoppingListItem.status == "pending",
        )
        .update({"status": "purchased"})
    )

    db.commit()

    return {
        "message": f"{updated_count} item(s) marqué(s) comme acheté(s)",
        "updated_count": updated_count,
    }


@router.post("/{list_id}/items", status_code=201)
def add_item_to_list(
    list_id: int,
    item_data: ShoppingListItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ajouter un item à une liste existante"""
    shopping_list = (
        db.query(ShoppingList)
        .filter(ShoppingList.id == list_id, ShoppingList.user_id == current_user.id)
        .first()
    )

    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    item = ShoppingListItem(
        shopping_list_id=list_id,
        product_id=item_data.product_id,
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
