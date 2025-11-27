from sqlalchemy import Column, Integer, Float, String, ForeignKey, Date, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class InventoryItem(Base):
    """
    Modèle InventoryItem - Articles dans le frigo
    RG4: Un item d'inventaire référence un produit du catalogue
    RG6: Quantités avec unités
    RG7: Suivi de la dernière détection
    RG8: Gestion des dates d'ouverture
    RG9: Quantité ne peut être négative
    """

    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    fridge_id = Column(
        Integer, ForeignKey("fridges.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    # Quantités
    quantity = Column(Float, nullable=False)  # RG9: Doit être >= 0
    initial_quantity = Column(Float)  # Quantité initiale lors de l'ajout
    unit = Column(String, nullable=False)  # kg, L, piece, etc.

    # Dates
    added_at = Column(DateTime, default=datetime.utcnow)
    open_date = Column(Date)  # RG8: Date d'ouverture si consommation partielle
    expiry_date = Column(Date)  # Date de péremption

    # Tracking
    source = Column(String)  # 'manual', 'vision', 'barcode'
    last_seen_at = Column(
        DateTime, default=datetime.utcnow
    )  # RG7: Dernière détection par vision

    # Métadonnées
    metadata = Column(JSON, default=dict)

    # Relations
    fridge = relationship("Fridge", back_populates="inventory_items")
    product = relationship("Product", back_populates="inventory_items")
    events = relationship("Event", back_populates="inventory_item")
    alerts = relationship("Alert", back_populates="inventory_item")

    def __repr__(self):
        return f"<InventoryItem(id={self.id}, product_id={self.product_id}, quantity={self.quantity} {self.unit})>"
