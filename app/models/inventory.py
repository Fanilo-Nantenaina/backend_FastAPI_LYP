from sqlalchemy import Column, Integer, Float, String, ForeignKey, Date, DateTime, JSON, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    fridge_id = Column(
        Integer, ForeignKey("fridges.id", ondelete="CASCADE"), nullable=False
    )
    product_id = Column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

               
    quantity = Column(Float, nullable=False)                       
    initial_quantity = Column(Float)                                     
    unit = Column(String, nullable=False)                      

           
    added_at = Column(DateTime, default=datetime.utcnow)
    open_date = Column(Date)                                                   
    expiry_date = Column(Date)                      

              
    source = Column(String)                                 
    last_seen_at = Column(
        DateTime, default=datetime.utcnow, index=True
    )                                      

                 
    extra_data = Column(JSON, default=dict)

               
    fridge = relationship("Fridge", back_populates="inventory_items")
    product = relationship("Product", back_populates="inventory_items")
    events = relationship("Event", back_populates="inventory_item")
    alerts = relationship("Alert", back_populates="inventory_item")
    
    __table_args__ = (
        Index('ix_inventory_fridge_quantity', 'fridge_id', 'quantity'),
        Index('ix_inventory_fridge_expiry', 'fridge_id', 'expiry_date'),
        Index('ix_inventory_fridge_lastseen', 'fridge_id', 'last_seen_at'),
        Index('ix_inventory_expiry_quantity', 'expiry_date', 'quantity'),
    )

    def __repr__(self):
        return f"<InventoryItem(id={self.id}, product_id={self.product_id}, quantity={self.quantity} {self.unit})>"
