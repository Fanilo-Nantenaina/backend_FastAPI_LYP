import secrets
import string
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Optional, Dict
from app.models.device import FridgeDevice
from app.models.fridge import Fridge
from app.core.config import settings


class DeviceService:
    def __init__(self, db: Session):
        self.db = db

    def generate_pairing_code(self, fridge_id: int, device_type: str) -> str:
        """
        Génère un code de jumelage temporaire pour connecter un appareil

        Scénario :
        1. Le S22 Ultra (kiosque) génère un code à 6 chiffres
        2. L'utilisateur entre ce code sur son téléphone mobile
        3. Le téléphone se connecte au frigo via ce code
        """
        # Générer un code à 6 chiffres
        code_length = settings.DEVICE_PAIRING_CODE_LENGTH
        pairing_code = "".join(
            secrets.choice(string.digits) for _ in range(code_length)
        )

        # Créer ou mettre à jour le device
        device = (
            self.db.query(FridgeDevice)
            .filter(
                FridgeDevice.fridge_id == fridge_id,
                FridgeDevice.device_type == device_type,
                FridgeDevice.is_paired == False,
            )
            .first()
        )

        if device:
            device.pairing_code = pairing_code
            device.created_at = datetime.utcnow()
        else:
            device_id = self._generate_device_id()
            device = FridgeDevice(
                fridge_id=fridge_id,
                device_type=device_type,
                device_id=device_id,
                pairing_code=pairing_code,
                is_paired=False,
            )
            self.db.add(device)

        self.db.commit()

        return pairing_code

    def pair_device(
        self, pairing_code: str, device_type: str, device_name: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Jumelle un appareil avec le code de jumelage

        Returns: {
            'fridge_id': int,
            'device_id': str,
            'access_token': str (JWT spécifique pour cet appareil)
        }
        """
        # Rechercher le code de jumelage valide
        timeout_minutes = settings.DEVICE_PAIRING_TIMEOUT_MINUTES
        valid_after = datetime.utcnow() - timedelta(minutes=timeout_minutes)

        device = (
            self.db.query(FridgeDevice)
            .filter(
                FridgeDevice.pairing_code == pairing_code,
                FridgeDevice.is_paired == False,
                FridgeDevice.created_at >= valid_after,
            )
            .first()
        )

        if not device:
            return None

        # Jumeler l'appareil
        device.is_paired = True
        device.device_type = device_type
        if device_name:
            device.device_name = device_name
        device.last_active_at = datetime.utcnow()
        device.pairing_code = None  # Supprimer le code

        self.db.commit()

        # Générer un token JWT spécifique pour cet appareil
        from app.core.security import create_access_token

        device_token = create_access_token(
            {
                "sub": device.fridge.user_id,
                "fridge_id": device.fridge_id,
                "device_id": device.device_id,
                "device_type": device.device_type,
            }
        )

        return {
            "fridge_id": device.fridge_id,
            "device_id": device.device_id,
            "device_name": device.device_name,
            "access_token": device_token,
        }

    def update_device_activity(self, device_id: str):
        """Met à jour la dernière activité d'un appareil"""
        device = (
            self.db.query(FridgeDevice)
            .filter(FridgeDevice.device_id == device_id)
            .first()
        )

        if device:
            device.last_active_at = datetime.utcnow()
            self.db.commit()

    def list_paired_devices(self, fridge_id: int) -> list:
        """Liste tous les appareils jumelés à un frigo"""
        return (
            self.db.query(FridgeDevice)
            .filter(FridgeDevice.fridge_id == fridge_id, FridgeDevice.is_paired == True)
            .all()
        )

    def unpair_device(self, device_id: str, user_id: int) -> bool:
        """Déjumeler un appareil"""
        device = (
            self.db.query(FridgeDevice)
            .join(Fridge)
            .filter(FridgeDevice.device_id == device_id, Fridge.user_id == user_id)
            .first()
        )

        if device:
            self.db.delete(device)
            self.db.commit()
            return True
        return False

    def _generate_device_id(self) -> str:
        """Génère un ID unique pour l'appareil"""
        import uuid

        return str(uuid.uuid4())
