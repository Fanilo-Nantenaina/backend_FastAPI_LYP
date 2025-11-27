from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class FridgeDevice(Base):
    """
    Modèle FridgeDevice - Appareils connectés au frigo
    Pour gérer le jumelage S22 Ultra (kiosque) ↔ Téléphone mobile
    """

    __tablename__ = "fridge_devices"

    id = Column(Integer, primary_key=True, index=True)
    fridge_id = Column(
        Integer, ForeignKey("fridges.id", ondelete="CASCADE"), nullable=False
    )

    device_id = Column(String, unique=True, nullable=False, index=True)  # UUID
    device_type = Column(String, nullable=False)  # 'kiosk', 'mobile', 'tablet', 'web'
    device_name = Column(String)  # Nom personnalisé de l'appareil

    # Jumelage
    pairing_code = Column(
        String, unique=True, index=True
    )  # Code temporaire à 6 chiffres
    is_paired = Column(Boolean, default=False)

    # Tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active_at = Column(DateTime)

    # Relations
    fridge = relationship("Fridge", back_populates="devices")

    def __repr__(self):
        return f"<FridgeDevice(id={self.id}, device_type={self.device_type}, paired={self.is_paired})>"
