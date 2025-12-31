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
def list_products(
    db: Session = Depends(get_db),
    search: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    query = db.query(Product)

    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))

    if category:
        query = query.filter(Product.category == category)

    return query.limit(limit).all()


@router.post("", response_model=ProductResponse, status_code=201)
def create_product(
    request: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = Product(**request.dict())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=404, detail="Product not found"
        )                     
    return product


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    request: ProductUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Modifier un produit"""
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = request.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)

    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    db.delete(product)
    db.commit()
    return None 
