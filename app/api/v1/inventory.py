# api/v1/inventory.py - VERSION CORRIGÉE
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date

from app.core.database import get_db
from app.core.dependencies import get_current_user_optional
from app.models.user import User
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

router = APIRouter(prefix="/fridges/{fridge_id}/inventory", tags=["Inventory"])


def get_fridge_access_hybrid(
    fridge_id: int,
    x_kiosk_id: Optional[str] = Header(None, alias="X-Kiosk-ID"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Fridge:
    """HYBRIDE : Accepte soit kiosk_id (pour kiosk), soit JWT (pour mobile)"""
    if x_kiosk_id:
        fridge = (
            db.query(Fridge)
            .filter(
                Fridge.id == fridge_id,
                Fridge.kiosk_id == x_kiosk_id,
                Fridge.is_paired == True,
            )
            .first()
        )
        if not fridge:
            raise HTTPException(
                status_code=403,
                detail="Access denied to this fridge or fridge not paired",
            )
        return fridge
    elif current_user:
        fridge = (
            db.query(Fridge)
            .filter(Fridge.id == fridge_id, Fridge.user_id == current_user.id)
            .first()
        )
        if not fridge:
            raise HTTPException(
                status_code=404, detail="Fridge not found or access denied"
            )
        return fridge
    else:
        raise HTTPException(
            status_code=401,
            detail="Authentication required (JWT token or X-Kiosk-ID header)",
        )


def _enrich_inventory_response(item: InventoryItem, db: Session) -> dict:
    """
    ✅ CORRIGÉ: Enrichit la réponse avec TOUTES les infos du produit
    Inclut: nom, catégorie, statut de fraîcheur, jours avant expiration
    """
    product = db.query(Product).filter(Product.id == item.product_id).first()

    # Calculer le statut de fraîcheur
    freshness_status = "unknown"
    days_until_expiry = None
    freshness_label = None

    if item.expiry_date:
        today = date.today()
        days_until_expiry = (item.expiry_date - today).days

        if days_until_expiry < 0:
            freshness_status = "expired"
            freshness_label = f"Expiré depuis {abs(days_until_expiry)} jour(s)"
        elif days_until_expiry == 0:
            freshness_status = "expires_today"
            freshness_label = "Expire aujourd'hui"
        elif days_until_expiry <= 3:
            freshness_status = "expiring_soon"
            freshness_label = f"Expire dans {days_until_expiry} jour(s)"
        else:
            freshness_status = "fresh"
            freshness_label = "Frais"

    # Calculer les jours depuis l'ajout
    days_since_added = None
    if item.added_at:
        days_since_added = (datetime.utcnow() - item.added_at).days

    return {
        "id": item.id,
        "fridge_id": item.fridge_id,
        "product_id": item.product_id,
        "quantity": item.quantity,
        "initial_quantity": item.initial_quantity,
        "unit": item.unit,
        "added_at": item.added_at.isoformat() if item.added_at else None,
        "open_date": item.open_date.isoformat() if item.open_date else None,
        "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
        "source": item.source,
        "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
        "extra_data": item.extra_data,
        # ✅ Infos produit
        "product_name": product.name if product else f"Produit #{item.product_id}",
        "product_category": product.category if product else "Non catégorisé",
        "product_tags": product.tags if product else [],
        "shelf_life_days": product.shelf_life_days if product else None,
        # ✅ NOUVEAU: Statut de fraîcheur
        "freshness_status": freshness_status,
        "freshness_label": freshness_label,
        "days_until_expiry": days_until_expiry,
        "days_since_added": days_since_added,
        # ✅ NOUVEAU: Indicateur d'ouverture
        "is_opened": item.open_date is not None,
    }


@router.get("")
def list_inventory(
    fridge: Fridge = Depends(get_fridge_access_hybrid),
    db: Session = Depends(get_db),
    active_only: bool = True,
):
    """Liste l'inventaire du frigo avec les noms de produits"""
    query = db.query(InventoryItem).filter(InventoryItem.fridge_id == fridge.id)
    if active_only:
        query = query.filter(InventoryItem.quantity > 0)
    items = query.all()
    return [_enrich_inventory_response(item, db) for item in items]


@router.post("", status_code=201)
def add_inventory_item(
    request: InventoryItemCreate,
    fridge: Fridge = Depends(get_fridge_access_hybrid),
    db: Session = Depends(get_db),
):
    """Ajouter un article à l'inventaire."""
    product = None

    if request.product_id:
        product = db.query(Product).filter(Product.id == request.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
    elif request.product_name:
        existing = (
            db.query(Product).filter(Product.name.ilike(request.product_name)).first()
        )
        if existing:
            product = existing
        else:
            product = Product(
                name=request.product_name.strip().capitalize(),
                category=request.category or "Divers",
                default_unit=request.unit or "pièce",
                shelf_life_days=7,
            )
            db.add(product)
            db.flush()

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
    return _enrich_inventory_response(inventory_item, db)


@router.put("/{item_id}")
def update_inventory_item(
    item_id: int,
    request: InventoryItemUpdate,
    fridge: Fridge = Depends(get_fridge_access_hybrid),
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

    old_quantity = item.quantity
    old_expiry_date = item.expiry_date  # ✅ NOUVEAU

    if request.quantity is not None:
        if request.quantity < 0:
            raise HTTPException(status_code=400, detail="Quantity cannot be negative")
        item.quantity = request.quantity
    if request.expiry_date is not None:
        item.expiry_date = request.expiry_date
    if request.open_date is not None:
        item.open_date = request.open_date

    # ✅ NOUVEAU : Événement si quantité modifiée
    if request.quantity is not None and request.quantity != old_quantity:
        event = Event(
            fridge_id=fridge.id,
            inventory_item_id=item.id,
            type="QUANTITY_UPDATED",
            payload={
                "old_quantity": old_quantity,
                "new_quantity": request.quantity,
                "unit": item.unit,
            },
        )
        db.add(event)

    # ✅ NOUVEAU : Événement si date d'expiration modifiée
    if request.expiry_date is not None and request.expiry_date != old_expiry_date:
        event = Event(
            fridge_id=fridge.id,
            inventory_item_id=item.id,
            type="EXPIRY_UPDATED",
            payload={
                "old_expiry_date": (
                    old_expiry_date.isoformat() if old_expiry_date else None
                ),
                "new_expiry_date": request.expiry_date.isoformat(),
            },
        )
        db.add(event)

    db.commit()
    db.refresh(item)

    # ✅ NOUVEAU : Déclencher une vérification d'alerte immédiate
    if request.expiry_date is not None:
        from app.services.alert_service import AlertService

        alert_service = AlertService(db)

        # Vérifier uniquement les alertes d'expiration pour cet item
        config = fridge.config or {}
        expiry_days = config.get("expiry_warning_days", 3)

        # Supprimer les anciennes alertes de ce type pour cet item
        db.query(Alert).filter(
            Alert.inventory_item_id == item.id,
            Alert.type.in_(["EXPIRY_SOON", "EXPIRED"]),
            Alert.status == "pending",
        ).delete()

        # Créer une nouvelle alerte si nécessaire
        new_alert = alert_service._check_expiry_alert(item, fridge.id, expiry_days)
        if new_alert:
            logger.info(f"✅ New expiry alert created after update: {item.id}")

        db.commit()

    return _enrich_inventory_response(item, db)


@router.post("/{item_id}/consume")
def consume_item(
    item_id: int,
    request: ConsumeItemRequest,
    fridge: Fridge = Depends(get_fridge_access_hybrid),
    db: Session = Depends(get_db),
):
    """Déclarer la Consommation"""
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
    product = db.query(Product).filter(Product.id == item.product_id).first()

    event = Event(
        fridge_id=fridge.id,
        inventory_item_id=item.id,
        type="ITEM_CONSUMED",
        payload={
            "product_name": product.name if product else "Unknown",
            "quantity_consumed": request.quantity_consumed,
            "unit": item.unit,
            "remaining": new_quantity,
        },
    )
    db.add(event)
    db.commit()
    db.refresh(item)
    return _enrich_inventory_response(item, db)


@router.delete("/{item_id}", status_code=204)
def remove_inventory_item(
    item_id: int,
    fridge: Fridge = Depends(get_fridge_access_hybrid),
    db: Session = Depends(get_db),
):
    """Supprimer un item"""
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.id == item_id, InventoryItem.fridge_id == fridge.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    product = db.query(Product).filter(Product.id == item.product_id).first()
    event = Event(
        fridge_id=fridge.id,
        inventory_item_id=item.id,
        type="ITEM_REMOVED",
        payload={
            "product_name": product.name if product else "Unknown",
            "quantity": item.quantity,
            "reason": "user_delete",
        },
    )
    db.add(event)
    db.delete(item)
    db.commit()
    return None
