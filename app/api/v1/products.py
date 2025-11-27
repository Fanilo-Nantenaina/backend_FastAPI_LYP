from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductResponse, ProductCreate, ProductUpdate

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=List[ProductResponse])
async def list_products(
    db: Session = Depends(get_db),
    search: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    """Liste tous les produits disponibles"""
    query = db.query(Product)

    if search:
        # Recherche insensible à la casse dans le nom
        query = query.filter(Product.name.ilike(f"%{search}%"))

    if category:
        query = query.filter(Product.category == category)

    return query.limit(limit).all()


@router.post("", response_model=ProductResponse, status_code=201)
async def create_product(
    request: ProductCreate,
    current_user: User = Depends(
        get_current_user
    ),  # On suppose que seuls les admins/utilisateurs authentifiés peuvent créer des produits
    db: Session = Depends(get_db),
):
    """Créer un nouveau produit"""
    # Note : Vérification de l'unicité du produit (ex: par code-barres) pourrait être ajoutée ici
    product = Product(**request.dict())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int, db: Session = Depends(get_db)):
    """Récupérer un produit spécifique"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=404, detail="Product not found"
        )  # Complète la ligne
    return product


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    request: ProductUpdate,
    current_user: User = Depends(
        get_current_user
    ),  # Sécurité : s'assurer que seul un utilisateur autorisé peut mettre à jour
    db: Session = Depends(get_db),
):
    """Modifier un produit"""
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Mise à jour des champs (on n'utilise que les champs définis dans ProductUpdate qui ne sont pas None)
    update_data = request.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)

    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: int,
    current_user: User = Depends(
        get_current_user
    ),  # Sécurité : s'assurer que seul un utilisateur autorisé peut supprimer
    db: Session = Depends(get_db),
):
    """Supprimer un produit"""
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        # On pourrait retourner 204 même si l'élément n'existe pas,
        # mais 404 est plus informatif dans un contexte de gestion.
        raise HTTPException(status_code=404, detail="Product not found")

    db.delete(product)
    db.commit()
    return None  # Retourne un statut 204 (No Content)
