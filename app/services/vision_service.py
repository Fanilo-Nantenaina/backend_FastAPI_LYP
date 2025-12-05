import json
import io
from PIL import Image
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from fastapi import UploadFile
from sqlalchemy.orm import Session
from google import genai
from google.genai import types
import unicodedata
import re

from app.middleware.transaction_handler import transactional
from app.core.config import settings
from app.models.product import Product
from app.models.inventory import InventoryItem
from app.models.event import Event
from app.schemas.vision import DetectedProduct


# ✅ BASE DE DONNÉES de durées de conservation par défaut
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
    "gingembre": 30,  # ✅ AJOUT
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

    def normalize_product_name(name: str) -> str:
        """
        Normalise un nom de produit pour la comparaison
        - Supprime les accents
        - Minuscules
        - Supprime les pluriels (s/x)
        - Supprime les articles (le, la, les, un, une, des)
        - Supprime les espaces multiples
        """
        if not name:
            return ""

        # 1. Minuscules
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

        # 4. Supprimer les pluriels (s, x à la fin)
        words = name.split()
        normalized_words = []
        for word in words:
            # Enlever 's' ou 'x' final si le mot fait plus de 3 caractères
            if len(word) > 3 and word[-1] in ["s", "x"]:
                # Ne pas enlever si c'est un 'ss' (ex: mousse)
                if not (word[-2:] == "ss"):
                    word = word[:-1]
            normalized_words.append(word)

        name = " ".join(normalized_words)

        # 5. Nettoyer les espaces multiples et caractères spéciaux
        name = re.sub(r"\s+", " ", name).strip()
        name = re.sub(r"[^\w\s-]", "", name)

        return name

    def _find_existing_inventory_item(
        self, fridge_id: int, product_id: int, detected_name: str
    ) -> Optional[InventoryItem]:
        """
        Recherche intelligente d'un item existant dans l'inventaire
        Gère les variations de produits similaires
        """
        import logging

        logger = logging.getLogger(__name__)

        # 1. Recherche par product_id exact
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
            logger.info(f"  📦 Found existing item by product_id: {product_id}")
            return existing

        # 2. Recherche par nom similaire (pour les cas où le product_id diffère légèrement)
        normalized_search = normalize_product_name(detected_name)

        all_items = (
            self.db.query(InventoryItem)
            .filter(
                InventoryItem.fridge_id == fridge_id,
                InventoryItem.quantity > 0,
            )
            .all()
        )

        for item in all_items:
            product = (
                self.db.query(Product).filter(Product.id == item.product_id).first()
            )
            if product:
                normalized_db = normalize_product_name(product.name)
                if normalized_db == normalized_search:
                    logger.info(
                        f"  📦 Found existing item by normalized name: '{product.name}'"
                    )
                    return item

        logger.info(f"  📦 No existing item found")
        return None

    @transactional
    async def analyze_and_update_inventory(
        self, image_file: UploadFile, fridge_id: int
    ) -> Dict[str, Any]:
        """
        Analyse l'image et met à jour l'inventaire
        ✅ CORRECTION: Toujours définir une date d'expiration
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

            # ✅ Plus besoin de needs_manual_entry car on définit toujours la date

        from app.models.event import Event

        event = Event(
            fridge_id=fridge_id,
            type="ITEM_DETECTED",  # ✅ Changé de INVENTORY_UPDATED
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
            "Vous êtes un assistant expert en inventaire de cuisine. Analysez l'image fournie et :\n"
            "1. Détectez TOUS les produits alimentaires visibles\n"
            "2. Comptez avec précision (ex: 6 œufs, 3 tomates)\n"
            "3. Lisez les textes sur les emballages (OCR) - nom du produit\n"
            "4. Cherchez les DATES DE PÉREMPTION sur les emballages (format DD/MM/YYYY ou similaire)\n"
            "5. Si pas de date visible, estimez la durée de conservation en jours\n"
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
        ✅ CORRECTION: Garantit TOUJOURS une date d'expiration
        """
        import logging

        logger = logging.getLogger(__name__)

        product = self._find_or_create_product(detected)

        # ✅ ÉTAPE 1: Essayer de lire la date sur l'emballage
        expiry_date = None
        if detected.expiry_date_text:
            expiry_date = self._parse_expiry_date(detected.expiry_date_text)

        # ✅ ÉTAPE 2: Sinon, utiliser l'estimation de l'IA
        if not expiry_date and detected.estimated_shelf_life_days:
            expiry_date = date.today() + timedelta(
                days=detected.estimated_shelf_life_days
            )

        # ✅ ÉTAPE 3: Sinon, utiliser la base de données produit
        if not expiry_date and product.shelf_life_days:
            expiry_date = date.today() + timedelta(days=product.shelf_life_days)

        # ✅ ÉTAPE 4: Sinon, utiliser notre base de connaissances
        if not expiry_date:
            days = self._estimate_shelf_life(detected.product_name, detected.category)
            expiry_date = date.today() + timedelta(days=days)

        # ✅ À ce stade, expiry_date ne peut JAMAIS être None

        existing_item = self._find_existing_inventory_item(
            fridge_id=fridge_id,
            product_id=product.id,
            detected_name=detected.product_name,
        )

        now = datetime.utcnow()

        if existing_item:
            existing_item.quantity += detected.count
            existing_item.last_seen_at = now

            # ✅ DEBUG : Identifier la source exacte du problème
            logger.info(f"🔍 Debug expiry dates for product '{product.name}':")
            logger.info(
                f"  - existing_item.expiry_date: {existing_item.expiry_date} (type: {type(existing_item.expiry_date).__name__})"
            )
            logger.info(
                f"  - new expiry_date: {expiry_date} (type: {type(expiry_date).__name__})"
            )

            # ✅ SUPER DÉFENSIF : Convertir les deux en date avant comparaison
            existing_expiry = existing_item.expiry_date
            new_expiry = expiry_date

            try:
                # Vérifier et mettre à jour la date d'expiration
                if existing_expiry is None:
                    # Pas de date existante, on définit la nouvelle
                    logger.info(f"  ➡️ Action: Setting expiry_date (was None)")
                    existing_item.expiry_date = new_expiry
                elif isinstance(existing_expiry, date) and isinstance(new_expiry, date):
                    # Les deux sont des dates valides, on compare
                    if new_expiry > existing_expiry:
                        logger.info(
                            f"  ➡️ Action: Updating expiry_date ({existing_expiry} -> {new_expiry})"
                        )
                        existing_item.expiry_date = new_expiry
                    else:
                        logger.info(
                            f"  ➡️ Action: Keeping existing expiry_date ({existing_expiry})"
                        )
                else:
                    # Types incompatibles, forcer la mise à jour
                    logger.warning(
                        f"  ⚠️ Type mismatch detected, forcing update to {new_expiry}"
                    )
                    existing_item.expiry_date = new_expiry
            except Exception as e:
                # Fallback ultime : toujours définir la nouvelle date
                logger.error(f"  ❌ Error comparing dates: {e}")
                logger.error(f"  ➡️ Fallback: forcing expiry_date to {new_expiry}")
                existing_item.expiry_date = new_expiry

            event = Event(
                fridge_id=fridge_id,
                inventory_item_id=existing_item.id,
                type="ITEM_DETECTED",
                payload={
                    "source": "vision",
                    "added_quantity": detected.count,
                    "new_total": existing_item.quantity,
                    "expiry_date_updated": str(existing_item.expiry_date),
                },
            )
            self.db.add(event)

            return {
                "action": "updated",
                "item": existing_item,
                "expiry_date_detected": True,
            }
        else:
            # Nouvel item
            logger.info(f"🆕 Creating new item for product '{product.name}':")
            logger.info(
                f"  - expiry_date: {expiry_date} (type: {type(expiry_date).__name__})"
            )

            new_item = InventoryItem(
                fridge_id=fridge_id,
                product_id=product.id,
                quantity=detected.count,
                initial_quantity=detected.count,
                unit=product.default_unit,
                expiry_date=expiry_date,  # ✅ Jamais None
                source="vision",
                last_seen_at=now,
            )
            self.db.add(new_item)
            self.db.flush()

            event = Event(
                fridge_id=fridge_id,
                inventory_item_id=new_item.id,
                type="ITEM_ADDED",
                payload={
                    "source": "vision",
                    "product_name": product.name,
                    "quantity": detected.count,
                    "expiry_date": expiry_date.isoformat(),
                },
            )
            self.db.add(event)

            return {
                "action": "added",
                "item": new_item,
                "expiry_date_detected": True,
            }

    def _estimate_shelf_life(self, product_name: str, category: str) -> int:
        """
        ✅ Estime intelligemment la durée de conservation

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
        Trouve ou crée un produit avec recherche intelligente
        Gère les variations de noms (pluriel, accents, etc.)
        """
        import logging

        logger = logging.getLogger(__name__)

        detected_name = detected.product_name.strip()
        normalized_search = normalize_product_name(detected_name)

        logger.info(
            f"🔍 Searching product: '{detected_name}' (normalized: '{normalized_search}')"
        )

        # ✅ ÉTAPE 1: Recherche exacte (cas idéal)
        product = (
            self.db.query(Product).filter(Product.name.ilike(detected_name)).first()
        )

        if product:
            logger.info(f"  ✅ Found exact match: '{product.name}' (ID: {product.id})")
            return product

        # ✅ ÉTAPE 2: Recherche par nom normalisé
        all_products = self.db.query(Product).all()

        for prod in all_products:
            normalized_db = normalize_product_name(prod.name)

            # Comparaison stricte des noms normalisés
            if normalized_db == normalized_search:
                logger.info(
                    f"  ✅ Found normalized match: '{prod.name}' (ID: {prod.id})"
                )
                return prod

            # Comparaison partielle (contient)
            if normalized_search in normalized_db or normalized_db in normalized_search:
                # Vérifier que c'est assez similaire (au moins 70% du nom)
                similarity = (
                    len(normalized_search) / len(normalized_db)
                    if len(normalized_db) > 0
                    else 0
                )
                if similarity > 0.7 or len(normalized_search) > 0.7 * len(
                    normalized_db
                ):
                    logger.info(
                        f"  ✅ Found partial match: '{prod.name}' (ID: {prod.id}, similarity: {similarity:.2%})"
                    )
                    return prod

        # ✅ ÉTAPE 3: Recherche par catégorie + mots-clés
        category_lower = detected.category.lower()
        words = normalized_search.split()

        if len(words) >= 2:  # Si au moins 2 mots (ex: "poivron vert")
            category_products = (
                self.db.query(Product)
                .filter(Product.category.ilike(f"%{category_lower}%"))
                .all()
            )

            for prod in category_products:
                normalized_db = normalize_product_name(prod.name)
                # Vérifier si tous les mots-clés sont présents
                if all(word in normalized_db for word in words):
                    logger.info(
                        f"  ✅ Found category+keyword match: '{prod.name}' (ID: {prod.id})"
                    )
                    return prod

        # ✅ ÉTAPE 4: Aucune correspondance, créer nouveau produit
        logger.info(f"  🆕 No match found, creating new product: '{detected_name}'")

        shelf_life = self._estimate_shelf_life(detected_name, detected.category)

        product = Product(
            name=detected_name.capitalize(),  # Première lettre majuscule
            category=detected.category,
            shelf_life_days=shelf_life,
            default_unit="pièce",
        )
        self.db.add(product)
        self.db.flush()

        logger.info(f"  ✅ Created product: '{product.name}' (ID: {product.id})")
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
