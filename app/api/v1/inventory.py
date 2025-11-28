from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, date
from app.core.database import get_db
from app.core.dependencies import get_user_fridge
from app.models.fridge import Fridge
from app.models.inventory import InventoryItem
from app.models.product import Product
from app.models.event import Event
from app.schemas.inventory import (
    InventoryItemResponse,
    InventoryItemCreate,
    InventoryItemUpdate,
    ConsumeItemRequest,
)
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/fridges/{fridge_id}/inventory", tags=["Inventory"])


@router.get("", response_model=List[InventoryItemResponse])
def list_inventory(
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
    active_only: bool = True,
):
    """Liste l'inventaire du frigo (RG6)"""
    query = db.query(InventoryItem).filter(InventoryItem.fridge_id == fridge.id)

    if active_only:
        query = query.filter(InventoryItem.quantity > 0)

    return query.all()


@router.post("", response_model=InventoryItemResponse, status_code=201)
def add_inventory_item(
    request: InventoryItemCreate,
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
):
    """CU2: Enregistrer un Article manuellement"""
    product = db.query(Product).filter(Product.id == request.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    inventory_item = InventoryItem(
        fridge_id=fridge.id,
        product_id=product.id,
        quantity=request.quantity,
        initial_quantity=request.quantity,
        unit=request.unit or product.default_unit,
        expiry_date=request.expiry_date,
        source="manual",
        last_seen_at=datetime.utcnow(),
    )

    db.add(inventory_item)
    db.flush()

    event = Event(
        fridge_id=fridge.id,
        inventory_item_id=inventory_item.id,
        type="ITEM_ADDED",
        payload={
            "product_name": product.name,
            "quantity": request.quantity,
            "unit": inventory_item.unit,
            "source": "manual",
        },
    )
    db.add(event)

    db.commit()
    db.refresh(inventory_item)
    return inventory_item


@router.put("/{item_id}", response_model=InventoryItemResponse)
def update_inventory_item(
    item_id: int,
    request: InventoryItemUpdate,
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
):
    """Mettre à jour un item d'inventaire"""
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.id == item_id, InventoryItem.fridge_id == fridge.id)
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    if request.quantity is not None:
        if request.quantity < 0:
            raise HTTPException(status_code=400, detail="Quantity cannot be negative")
        item.quantity = request.quantity

    if request.expiry_date is not None:
        item.expiry_date = request.expiry_date

    if request.open_date is not None:
        item.open_date = request.open_date

    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/consume", response_model=InventoryItemResponse)
def consume_item(
    item_id: int,
    request: ConsumeItemRequest,
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
):
    """CU3: Déclarer la Consommation (Retrait)"""
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.id == item_id, InventoryItem.fridge_id == fridge.id)
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    new_quantity = item.quantity - request.quantity_consumed
    if new_quantity < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot consume more than available ({item.quantity} {item.unit})",
        )

    if new_quantity > 0 and not item.open_date:
        item.open_date = date.today()

    item.quantity = new_quantity

    event = Event(
        fridge_id=fridge.id,
        inventory_item_id=item.id,
        type="ITEM_CONSUMED",
        payload={
            "quantity_consumed": request.quantity_consumed,
            "unit": item.unit,
            "remaining": new_quantity,
        },
    )
    db.add(event)

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def remove_inventory_item(
    item_id: int,
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
):
    """Supprimer complètement un item"""
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.id == item_id, InventoryItem.fridge_id == fridge.id)
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    event = Event(
        fridge_id=fridge.id,
        inventory_item_id=item.id,
        type="ITEM_REMOVED",
        payload={
            "product_name": item.product.name if item.product else "Unknown",
            "quantity": item.quantity,
            "reason": "user_delete",
        },
    )
    db.add(event)

    db.delete(item)
    db.commit()
    return None
