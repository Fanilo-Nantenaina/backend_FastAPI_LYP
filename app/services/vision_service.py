import json
import io
from PIL import Image
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Tuple
from fastapi import UploadFile
from sqlalchemy.orm import Session
from google import genai
from google.genai import types
import unicodedata
import re
from pydantic import BaseModel

from app.middleware.transaction_handler import transactional
from app.core.config import settings
from app.models.product import Product
from app.models.inventory import InventoryItem
from app.models.event import Event
from app.schemas.vision import (
    DetectedProduct,
    DetectedProductMatch,
    ConsumeAnalysisResponse,
)
from difflib import SequenceMatcher


# BASE DE DONNÉES de durées de conservation par défaut
DEFAULT_SHELF_LIFE = {
    # Produits laitiers
    "lait": 7,
    "yaourt": 14,
    "fromage": 30,
    "beurre": 60,
    "crème": 10,
    # Viandes
    "poulet": 3,
    "bœuf": 5,
    "porc": 5,
    "poisson": 2,
    "viande hachée": 2,
    # Fruits
    "pomme": 14,
    "banane": 7,
    "orange": 14,
    "fraise": 5,
    "raisin": 7,
    "tomate": 7,
    "citron": 21,
    "mangue": 7,
    # Légumes
    "carotte": 21,
    "salade": 7,
    "concombre": 10,
    "poivron": 14,
    "oignon": 30,
    "pomme de terre": 60,
    "gingembre": 30,  # AJOUT
    "ail": 60,
    "chou": 14,
    "brocoli": 7,
    # Œufs et substituts
    "œuf": 28,
    "oeuf": 28,
    # Plats préparés
    "pizza": 3,
    "sandwich": 2,
    "plat cuisiné": 3,
    # Condiments
    "ketchup": 180,
    "mayonnaise": 60,
    "moutarde": 180,
    "sauce soja": 365,
    # Défaut pour catégories
    "produit laitier": 7,
    "viande": 3,
    "fruit": 7,
    "légume": 10,
    "plat préparé": 3,
    "condiment": 180,
}


class VisionService:
    def __init__(self, db: Session):
        self.db = db
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

    @staticmethod
    def normalize_product_name(name: str) -> str:
        """
        Normalise un nom de produit pour la comparaison
        - Supprime les accents
        - Minuscules
        - Supprime les pluriels (s/x)
        - Supprime les articles
        """
        if not name:
            return ""

        # 1. Minuscules + strip
        name = name.lower().strip()

        # 2. Supprimer les accents
        name = "".join(
            c
            for c in unicodedata.normalize("NFD", name)
            if unicodedata.category(c) != "Mn"
        )

        # 3. Supprimer les articles
        articles = [
            "le ",
            "la ",
            "les ",
            "un ",
            "une ",
            "des ",
            "du ",
            "de la ",
            "l'",
            "d'",
        ]
        for article in articles:
            if name.startswith(article):
                name = name[len(article) :]

        # 4. Supprimer les pluriels
        words = name.split()
        normalized_words = []
        for word in words:
            if len(word) > 3 and word[-1] in ["s", "x"] and not word.endswith("ss"):
                word = word[:-1]
            normalized_words.append(word)

        name = " ".join(normalized_words)

        # 5. Nettoyer
        name = re.sub(r"\s+", " ", name).strip()
        name = re.sub(r"[^\w\s-]", "", name)

        return name

    @staticmethod
    def calculate_similarity(str1: str, str2: str) -> float:
        """
        Calcule un score de similarité entre deux chaînes (0-100)
        Utilise SequenceMatcher de difflib
        """
        return SequenceMatcher(None, str1, str2).ratio() * 100

    def _find_best_product_match(
        self, detected_name: str, detected_category: str
    ) -> Tuple[Optional[Product], float]:
        """
        NOUVELLE MÉTHODE : Trouve le meilleur produit avec score

        Retourne : (Product ou None, score de 0-100)
        """
        import logging

        logger = logging.getLogger(__name__)

        normalized_search = self.normalize_product_name(detected_name)
        logger.info(
            f"🔍 Searching best match for: '{detected_name}' → normalized: '{normalized_search}'"
        )

        # Récupérer TOUS les produits
        all_products = self.db.query(Product).all()

        if not all_products:
            logger.info("  No products in database")
            return None, 0.0

        candidates = []  # Liste de (product, score)

        for product in all_products:
            normalized_db = self.normalize_product_name(product.name)
            score = 0.0

            # SCORING MULTI-CRITÈRES

            # 1️⃣ Match exact normalisé → 100 points
            if normalized_search == normalized_db:
                score = 100.0
                logger.info(f"  EXACT MATCH: '{product.name}' (score: {score})")

            # 2️⃣ Similarité de chaîne (difflib) → 0-95 points
            else:
                similarity = self.calculate_similarity(normalized_search, normalized_db)
                score = similarity

                # 3️⃣ Bonus : Un mot est contenu dans l'autre → +20 points
                words_search = set(normalized_search.split())
                words_db = set(normalized_db.split())

                if words_search.issubset(words_db) or words_db.issubset(words_search):
                    score += 20
                    logger.info(
                        f"  📝 Subset bonus: '{product.name}' ({similarity:.1f}% + 20 = {score:.1f})"
                    )

                # 4️⃣ Bonus : Même catégorie → +10 points
                if detected_category.lower() == product.category.lower():
                    score += 10
                    logger.info(f"  🏷️ Category bonus: '{product.name}' (same category)")

                # 5️⃣ Bonus : Début identique → +15 points
                min_len = min(len(normalized_search), len(normalized_db))
                if min_len >= 4 and normalized_search[:4] == normalized_db[:4]:
                    score += 15
                    logger.info(f"  🔤 Prefix bonus: '{product.name}' (same start)")

            # Cap à 100 max
            score = min(score, 100.0)

            if score >= 50:  # Seuil minimum de pertinence
                candidates.append((product, score))
                logger.info(f"Candidate: '{product.name}' (score: {score:.1f})")

        if not candidates:
            logger.info("No candidates above threshold (50%)")
            return None, 0.0

        # Trier par score décroissant
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_product, best_score = candidates[0]

        logger.info(
            f"BEST MATCH: '{best_product.name}' (ID: {best_product.id}, score: {best_score:.1f}%)"
        )

        # Log des autres candidats
        if len(candidates) > 1:
            logger.info(f"Other candidates:")
            for prod, sc in candidates[1:4]:  # Top 3 suivants
                logger.info(f"     - '{prod.name}': {sc:.1f}%")

        return best_product, best_score

    async def find_best_inventory_match(
        self,
        fridge_id: int,
        detected_name: str,
        detected_category: str,
        detected_count: int,
    ) -> DetectedProductMatch:
        """
        Trouve la meilleure correspondance dans l'inventaire

        Stratégie de matching:
        1. Nom exact (insensible à la casse)
        2. Similarité de chaîne (SequenceMatcher)
        3. Catégorie + mots-clés
        4. Si pas de match → retourne alternatives
        """

        # Récupérer inventaire actif
        inventory = (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .all()
        )

        if not inventory:
            return DetectedProductMatch(
                detected_name=detected_name,
                detected_count=detected_count,
                confidence=0.0,
                possible_matches=[],
            )

        # Normalisation
        normalized_detected = self.normalize_product_name(detected_name)

        best_match = None
        best_score = 0.0
        alternatives = []

        for item in inventory:
            product = (
                self.db.query(Product).filter(Product.id == item.product_id).first()
            )

            if not product:
                continue

            normalized_db = self.normalize_product_name(product.name)

            # Score 1: Nom exact
            if normalized_detected == normalized_db:
                score = 100.0
            else:
                # Score 2: Similarité de chaîne
                similarity = SequenceMatcher(
                    None, normalized_detected, normalized_db
                ).ratio()
                score = similarity * 100

                # Bonus si même catégorie
                if detected_category.lower() == product.category.lower():
                    score += 10
                    score = min(score, 100)  # Cap à 100

            match_info = {
                "item_id": item.id,
                "product_name": product.name,
                "available_quantity": item.quantity,
                "unit": item.unit,
                "score": round(score, 1),
            }

            if score > best_score:
                best_score = score
                best_match = match_info

            # Garder top 3 alternatives (score > 50%)
            if score >= 50:
                alternatives.append(match_info)

        # Trier alternatives par score décroissant
        alternatives.sort(key=lambda x: x["score"], reverse=True)
        alternatives = alternatives[:3]

        if best_match:
            return DetectedProductMatch(
                detected_name=detected_name,
                detected_count=detected_count,
                confidence=best_score / 100,
                matched_item_id=best_match["item_id"],
                matched_product_name=best_match["product_name"],
                available_quantity=best_match["available_quantity"],
                match_score=best_score,
                possible_matches=alternatives[1:],  # Exclure le best match
            )
        else:
            return DetectedProductMatch(
                detected_name=detected_name,
                detected_count=detected_count,
                confidence=0.0,
                possible_matches=alternatives,
            )

    def _find_existing_inventory_item(
        self, fridge_id: int, product_id: int, detected_name: str
    ) -> Optional[InventoryItem]:
        """
        SIMPLIFIÉ : Recherche par product_id uniquement
        (Le matching est déjà fait dans _find_or_create_product)
        """
        import logging

        logger = logging.getLogger(__name__)

        existing = (
            self.db.query(InventoryItem)
            .filter(
                InventoryItem.fridge_id == fridge_id,
                InventoryItem.product_id == product_id,
                InventoryItem.quantity > 0,
            )
            .first()
        )

        if existing:
            logger.info(f"  📦 Found existing inventory item (ID: {existing.id})")
        else:
            logger.info(f"  📦 No existing inventory item")

        return existing

    @transactional
    async def analyze_and_update_inventory(
        self, image_file: UploadFile, fridge_id: int
    ) -> Dict[str, Any]:
        """
        Analyse l'image et met à jour l'inventaire
        CORRECTION: Toujours définir une date d'expiration
        """

        detected_products = await self._analyze_image_with_gemini(image_file)

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

            # Plus besoin de needs_manual_entry car on définit toujours la date

        from app.models.event import Event

        event = Event(
            fridge_id=fridge_id,
            type="ITEM_DETECTED",  # Changé de INVENTORY_UPDATED
            payload={
                "source": "vision_scan",
                "timestamp": datetime.utcnow().isoformat(),
                "items_added": len(items_added),
                "items_updated": len(items_updated),
                "total_detected": len(detected_products),
            },
        )
        self.db.add(event)

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
            "Vous devez TOUJOURS répondre en FRANÇAIS, jamais en anglais.\n"
            "Vous êtes un assistant expert en inventaire de cuisine. Analysez l'image fournie et :\n"
            "1. Détectez TOUS les produits alimentaires visibles\n"
            "2. Comptez avec précision (ex: 6 œufs, 3 tomates)\n"
            "3. Lisez les textes sur les emballages (OCR) - nom du produit\n"
            "4. Cherchez les DATES DE PÉREMPTION sur les emballages (format DD/MM/YYYY ou similaire)\n"
            "5. Si pas de date visible, estimez la durée de conservation en jours\n"
            "IMPORTANT : Répondez UNIQUEMENT en français, avec des noms de produits en français.\n"
            "Répondez en JSON structuré."
        )

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
        AMÉLIORATION : Ajoute notifications smart pour détection vision
        """
        import logging

        logger = logging.getLogger(__name__)

        product = self._find_or_create_product(detected)

        # Calculer la date d'expiration (logique existante)
        expiry_date = None
        if detected.expiry_date_text:
            expiry_date = self._parse_expiry_date(detected.expiry_date_text)
        if not expiry_date and detected.estimated_shelf_life_days:
            expiry_date = date.today() + timedelta(
                days=detected.estimated_shelf_life_days
            )
        if not expiry_date and product.shelf_life_days:
            expiry_date = date.today() + timedelta(days=product.shelf_life_days)
        if not expiry_date:
            days = self._estimate_shelf_life(detected.product_name, detected.category)
            expiry_date = date.today() + timedelta(days=days)

        # Calculer le statut de fraîcheur
        freshness_status = "fresh"
        if expiry_date:
            days_until_expiry = (expiry_date - date.today()).days
            if days_until_expiry < 0:
                freshness_status = "expired"
            elif days_until_expiry == 0:
                freshness_status = "expires_today"
            elif days_until_expiry <= 3:
                freshness_status = "expiring_soon"

        existing_item = self._find_existing_inventory_item(
            fridge_id=fridge_id,
            product_id=product.id,
            detected_name=detected.product_name,
        )

        now = datetime.utcnow()

        # Préparer le NotificationService
        from app.services.notification_service import NotificationService

        notification_service = NotificationService(self.db)

        if existing_item:
            # MISE À JOUR d'un item existant
            old_quantity = existing_item.quantity
            existing_item.quantity += detected.count
            existing_item.last_seen_at = now

            # Gestion de la date d'expiration (logique existante)
            existing_expiry = existing_item.expiry_date
            new_expiry = expiry_date

            try:
                if existing_expiry is None:
                    logger.info(f"  ➡️ Setting expiry_date (was None)")
                    existing_item.expiry_date = new_expiry
                elif isinstance(existing_expiry, date) and isinstance(new_expiry, date):
                    if new_expiry > existing_expiry:
                        logger.info(
                            f"  ➡️ Updating expiry_date ({existing_expiry} -> {new_expiry})"
                        )
                        existing_item.expiry_date = new_expiry
                    else:
                        logger.info(
                            f"  ➡️ Keeping existing expiry_date ({existing_expiry})"
                        )
                else:
                    logger.warning(f"  Type mismatch, forcing update to {new_expiry}")
                    existing_item.expiry_date = new_expiry
            except Exception as e:
                logger.error(f"  Error comparing dates: {e}")
                existing_item.expiry_date = new_expiry

            # Event
            event = Event(
                fridge_id=fridge_id,
                inventory_item_id=existing_item.id,
                type="ITEM_DETECTED",
                payload={
                    "source": "vision",
                    "added_quantity": detected.count,
                    "new_total": existing_item.quantity,
                    "expiry_date_updated": str(existing_item.expiry_date),
                    "freshness_status": freshness_status,
                },
            )
            self.db.add(event)

            # NOTIFICATION SMART pour UPDATE
            try:
                notification_service.send_smart_inventory_notification(
                    fridge_id=fridge_id,
                    action="updated",  # Action = updated
                    product_name=product.name,
                    quantity=detected.count,  # Quantité ajoutée
                    remaining_quantity=existing_item.quantity,  # Total après ajout
                    unit=existing_item.unit,
                    freshness_status=freshness_status,
                    expiry_date=existing_item.expiry_date,
                    source="vision",
                )
                logger.info(
                    f"Smart notification sent for vision update: {product.name}"
                )
            except Exception as e:
                logger.error(f"Failed to send vision update notification: {e}")

            return {
                "action": "updated",
                "item": existing_item,
                "expiry_date_detected": True,
            }

        else:
            # CRÉATION d'un nouvel item
            logger.info(f"Creating new item for product '{product.name}':")

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
                    "expiry_date": expiry_date.isoformat(),
                    "freshness_status": freshness_status,
                },
            )
            self.db.add(event)

            # NOTIFICATION SMART pour ADD
            try:
                notification_service.send_smart_inventory_notification(
                    fridge_id=fridge_id,
                    action="added",  # Action = added
                    product_name=product.name,
                    quantity=detected.count,
                    unit=new_item.unit,
                    freshness_status=freshness_status,
                    expiry_date=expiry_date,
                    source="vision",
                )
                logger.info(f"Smart notification sent for vision add: {product.name}")
            except Exception as e:
                logger.error(f"Failed to send vision add notification: {e}")

            return {
                "action": "added",
                "item": new_item,
                "expiry_date_detected": True,
            }

    def _estimate_shelf_life(self, product_name: str, category: str) -> int:
        """
        Estime intelligemment la durée de conservation

        Ordre de priorité:
        1. Nom exact du produit
        2. Mot-clé dans le nom
        3. Catégorie
        4. Défaut conservateur (7 jours)
        """
        product_lower = product_name.lower()
        category_lower = category.lower()

        # 1. Recherche exacte
        if product_lower in DEFAULT_SHELF_LIFE:
            return DEFAULT_SHELF_LIFE[product_lower]

        # 2. Recherche par mot-clé
        for keyword, days in DEFAULT_SHELF_LIFE.items():
            if keyword in product_lower:
                return days

        # 3. Recherche par catégorie
        if category_lower in DEFAULT_SHELF_LIFE:
            return DEFAULT_SHELF_LIFE[category_lower]

        # 4. Heuristiques par catégorie
        if "lait" in category_lower or "dairy" in category_lower:
            return 7
        elif "viande" in category_lower or "meat" in category_lower:
            return 3
        elif "fruit" in category_lower:
            return 7
        elif "légume" in category_lower or "vegetable" in category_lower:
            return 10
        elif "poisson" in category_lower or "fish" in category_lower:
            return 2
        elif "congel" in category_lower or "frozen" in category_lower:
            return 180  # 6 mois

        # 5. Défaut sécuritaire
        return 7

    def _find_or_create_product(self, detected: DetectedProduct) -> Product:
        """
        REFONTE COMPLÈTE : Utilise le nouveau système de scoring

        Seuil de matching : 70%
        - >= 70% : Utilise le produit existant
        - < 70% : Crée un nouveau produit
        """
        import logging

        logger = logging.getLogger(__name__)

        detected_name = detected.product_name.strip()
        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 PRODUCT MATCHING: '{detected_name}'")
        logger.info(f"{'='*60}")

        # Recherche avec scoring
        best_product, best_score = self._find_best_product_match(
            detected_name, detected.category
        )

        # DÉCISION basée sur le score
        MATCH_THRESHOLD = 70.0  # Seuil configurable

        if best_product and best_score >= MATCH_THRESHOLD:
            logger.info(
                f"USING EXISTING: '{best_product.name}' (score: {best_score:.1f}% >= {MATCH_THRESHOLD}%)"
            )
            return best_product

        # Pas de match suffisant → Créer nouveau produit
        logger.info(f"CREATING NEW PRODUCT: '{detected_name}'")
        if best_product:
            logger.info(
                f"   (best match was '{best_product.name}' with {best_score:.1f}%, below threshold)"
            )

        shelf_life = self._estimate_shelf_life(detected_name, detected.category)

        new_product = Product(
            name=detected_name.capitalize(),
            category=detected.category,
            shelf_life_days=shelf_life,
            default_unit="pièce",
        )
        self.db.add(new_product)
        self.db.flush()

        logger.info(f"Created: '{new_product.name}' (ID: {new_product.id})")
        logger.info(f"{'='*60}\n")

        return new_product

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
        self, item_id: int, expiry_date: date, fridge_id: int
    ) -> Optional[InventoryItem]:
        """Mise à jour manuelle de la date de péremption"""
        item = (
            self.db.query(InventoryItem)
            .filter(
                InventoryItem.id == item_id,
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
            self.db.commit()

        return item
