import json
import io
from PIL import Image
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from fastapi import UploadFile
from sqlalchemy.orm import Session
from google import genai
from google.genai import types

from app.middleware.transaction_handler import transactional
from app.core.config import settings
from app.models.product import Product
from app.models.inventory import InventoryItem
from app.models.event import Event
from app.schemas.vision import DetectedProduct


class VisionService:
    def __init__(self, db: Session):
        self.db = db
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

    @transactional
    async def analyze_and_update_inventory(
        self, image_file: UploadFile, fridge_id: int
    ) -> Dict[str, Any]:
        """
        Analyse l'image et met à jour l'inventaire
        RG7: Met à jour last_seen_at pour chaque produit détecté
        """
        # 1. Analyser l'image avec Gemini
        detected_products = await self._analyze_image_with_gemini(image_file)

        # 2. Traiter chaque produit détecté
        items_added = []
        items_updated = []
        needs_manual_entry = []

        for detected in detected_products:
            result = self._process_detected_product(
                detected=detected, fridge_id=fridge_id
            )

            if result["action"] == "added":
                items_added.append(result["item"])
            elif result["action"] == "updated":
                items_updated.append(result["item"])

            # Si pas de date de péremption détectée
            if not result.get("expiry_date_detected"):
                needs_manual_entry.append(
                    {
                        "inventory_item_id": result["item"].id,
                        "product_name": result["item"].product.name,
                    }
                )

        # self.db.commit()

        return {
            "timestamp": datetime.now().isoformat(),
            "detected_count": len(detected_products),
            "items_added": len(items_added),
            "items_updated": len(items_updated),
            "needs_manual_entry": needs_manual_entry,
            "detected_products": [
                {"product": d.product_name, "category": d.category, "count": d.count}
                for d in detected_products
            ],
        }

    async def _analyze_image_with_gemini(
        self, image_file: UploadFile
    ) -> List[DetectedProduct]:
        """Appel à l'API Gemini pour analyse d'image"""

        # Schéma de sortie
        output_schema = {
            "type": "object",
            "properties": {
                "detected_products": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product": {"type": "string"},
                            "category": {"type": "string"},
                            "count": {"type": "integer"},
                            "packaging_text": {"type": "string"},
                            "expiry_date_text": {"type": "string"},
                            "estimated_expiry_days": {"type": "integer"},
                        },
                        "required": ["product", "category", "count", "packaging_text"],
                    },
                }
            },
        }

        system_instruction = (
            "Vous êtes un assistant expert en inventaire de cuisine. Analysez l'image fournie et :\n"
            "1. Détectez TOUS les produits alimentaires visibles\n"
            "2. Comptez avec précision (ex: 6 œufs, 3 tomates)\n"
            "3. Lisez les textes sur les emballages (OCR) - nom du produit\n"
            "4. Cherchez les DATES DE PÉREMPTION sur les emballages (format DD/MM/YYYY ou similaire)\n"
            "5. Si pas de date visible, estimez la durée de conservation en jours\n"
            "Répondez en JSON structuré."
        )

        # Lire l'image
        contents = await image_file.read()
        image = Image.open(io.BytesIO(contents))

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=output_schema,
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                image,
                "Inventoriez tous les produits. Lisez attentivement les dates de péremption sur les emballages.",
            ],
            config=config,
        )

        data = json.loads(response.text)

        # Convertir en objets DetectedProduct
        detected = []
        for item in data.get("detected_products", []):
            detected.append(
                DetectedProduct(
                    product_name=item["product"],
                    category=item["category"],
                    count=item["count"],
                    packaging_text=item.get("packaging_text", ""),
                    expiry_date_text=item.get("expiry_date_text"),
                    estimated_shelf_life_days=item.get("estimated_expiry_days"),
                )
            )

        return detected

    def _process_detected_product(
        self, detected: DetectedProduct, fridge_id: int
    ) -> Dict[str, Any]:
        """
        Traite un produit détecté : crée ou met à jour l'inventaire
        RG3, RG4: Gère la relation Product ↔ InventoryItem
        """
        # 1. Trouver ou créer le produit
        product = self._find_or_create_product(detected)

        # 2. Calculer la date de péremption
        expiry_date = None
        expiry_detected = False

        if detected.expiry_date_text:
            expiry_date = self._parse_expiry_date(detected.expiry_date_text)
            expiry_detected = True
        elif detected.estimated_shelf_life_days:
            expiry_date = date.today() + timedelta(
                days=detected.estimated_shelf_life_days
            )
            expiry_detected = True

        # 3. Vérifier si l'item existe déjà dans le frigo
        existing_item = (
            self.db.query(InventoryItem)
            .filter(
                InventoryItem.fridge_id == fridge_id,
                InventoryItem.product_id == product.id,
                InventoryItem.quantity > 0,
            )
            .first()
        )

        now = datetime.utcnow()

        if existing_item:
            # Mise à jour (RG7: last_seen_at)
            existing_item.quantity += detected.count
            existing_item.last_seen_at = now

            # Event
            event = Event(
                fridge_id=fridge_id,
                inventory_item_id=existing_item.id,
                type="ITEM_DETECTED",
                payload={
                    "source": "vision",
                    "added_quantity": detected.count,
                    "new_total": existing_item.quantity,
                },
            )
            self.db.add(event)

            return {
                "action": "updated",
                "item": existing_item,
                "expiry_date_detected": expiry_detected,
            }
        else:
            # Nouvel item
            new_item = InventoryItem(
                fridge_id=fridge_id,
                product_id=product.id,
                quantity=detected.count,
                initial_quantity=detected.count,
                unit=product.default_unit,
                expiry_date=expiry_date,
                source="vision",
                last_seen_at=now,
            )
            self.db.add(new_item)
            self.db.flush()

            # Event
            event = Event(
                fridge_id=fridge_id,
                inventory_item_id=new_item.id,
                type="ITEM_ADDED",
                payload={
                    "source": "vision",
                    "product_name": product.name,
                    "quantity": detected.count,
                },
            )
            self.db.add(event)

            return {
                "action": "added",
                "item": new_item,
                "expiry_date_detected": expiry_detected,
            }

    def _find_or_create_product(self, detected: DetectedProduct) -> Product:
        """Trouve ou crée un produit dans la DB"""
        product = (
            self.db.query(Product)
            .filter(Product.name.ilike(f"%{detected.product_name}%"))
            .first()
        )

        if not product:
            product = Product(
                name=detected.product_name,
                category=detected.category,
                shelf_life_days=detected.estimated_shelf_life_days,
                default_unit="piece",
            )
            self.db.add(product)
            self.db.flush()

        return product

    def _parse_expiry_date(self, date_text: str) -> Optional[date]:
        """Parse une date de péremption depuis le texte OCR"""
        formats = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"]

        for fmt in formats:
            try:
                return datetime.strptime(date_text.strip(), fmt).date()
            except ValueError:
                continue

        return None

    @transactional
    def update_expiry_date_manually(
        self, inventory_item_id: int, expiry_date: date, fridge_id: int
    ) -> Optional[InventoryItem]:
        """Mise à jour manuelle de la date de péremption"""
        item = (
            self.db.query(InventoryItem)
            .filter(
                InventoryItem.id == inventory_item_id,
                InventoryItem.fridge_id == fridge_id,
            )
            .first()
        )

        if item:
            item.expiry_date = expiry_date

            event = Event(
                fridge_id=fridge_id,
                inventory_item_id=item.id,
                type="EXPIRY_UPDATED",
                payload={"source": "manual", "expiry_date": expiry_date.isoformat()},
            )
            self.db.add(event)
            # self.db.commit()

        return item
