from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_user_fridge
from app.models.user import User
from app.models.fridge import Fridge
from app.models.shopping_list import ShoppingList, ShoppingListItem
from app.schemas.shopping_list import (
    ShoppingListResponse,
    ShoppingListCreate,
    ShoppingListItemCreate,
    GenerateShoppingListRequest,
)
from app.services.shopping_service import ShoppingService

router = APIRouter(prefix="/shopping-lists", tags=["Shopping Lists"])


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


@router.get("", response_model=List[ShoppingListResponse])
def list_shopping_lists(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    fridge_id: int = None,
):
    """Liste toutes les listes de courses de l'utilisateur"""
    query = db.query(ShoppingList).filter(ShoppingList.user_id == current_user.id)

    if fridge_id:
        query = query.filter(ShoppingList.fridge_id == fridge_id)

    return query.order_by(ShoppingList.created_at.desc()).all()


@router.get("/{list_id}", response_model=ShoppingListResponse)
def get_shopping_list(
    list_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Récupérer une liste de courses spécifique"""
    shopping_list = (
        db.query(ShoppingList)
        .filter(ShoppingList.id == list_id, ShoppingList.user_id == current_user.id)
        .first()
    )

    if not shopping_list:
        raise HTTPException(status_code=404, detail="Shopping list not found")

    return shopping_list


@router.put("/{list_id}/items/{item_id}/status")
def update_item_status(
    list_id: int,
    item_id: int,
    status: str,
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

    if status.lower() not in ["pending", "purchased", "cancelled"]:
        raise HTTPException(status_code=400, detail="Invalid status value")

    item.status = status.lower()
    db.commit()

    return {"message": "Item status updated"}


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
