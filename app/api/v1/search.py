# ==================================================
# Fichier : api/v1/search.py - NOUVEAU FICHIER À CRÉER
# ==================================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import logging

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.fridge import Fridge
from app.models.inventory import InventoryItem
from app.models.product import Product
from app.core.config import settings

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fridges/{fridge_id}/search", tags=["Search"])


# ==================================================
# SCHÉMAS PYDANTIC
# ==================================================


class SearchRequest(BaseModel):
    """Requête de recherche vocale/textuelle"""

    query: str


class SearchHistoryResponse(BaseModel):
    """Réponse historique d'une recherche"""

    id: str
    query: str
    response: str
    timestamp: str

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    """Réponse d'une recherche avec IA"""

    query: str
    response: str
    timestamp: str
    inventory_count: int


# ==================================================
# ROUTES
# ==================================================


@router.post("", response_model=SearchResponse)
async def search_inventory_with_ai(
    fridge_id: int,
    request: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    🔍 Recherche intelligente dans l'inventaire avec IA (Gemini)

    Cette route permet de poser des questions en langage naturel sur l'inventaire.

    Exemples de requêtes supportées :
    - "Combien d'œufs il me reste ?"
    - "Est-ce que j'ai du lait ?"
    - "Qu'est-ce qui expire bientôt ?"
    - "Qu'est-ce que je peux cuisiner ce soir ?"
    - "Qu'est-ce qu'il y a dans mon frigo ?"

    Args:
        fridge_id: ID du frigo
        request: Requête contenant la question
        current_user: Utilisateur authentifié
        db: Session de base de données

    Returns:
        Dict avec query, response, timestamp, inventory_count
    """

    # Vérifier l'accès au frigo (RG2)
    fridge = (
        db.query(Fridge)
        .filter(Fridge.id == fridge_id, Fridge.user_id == current_user.id)
        .first()
    )

    if not fridge:
        raise HTTPException(status_code=404, detail="Frigo non trouvé ou accès refusé")

    # Récupérer l'inventaire actuel
    inventory = (
        db.query(InventoryItem)
        .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
        .all()
    )

    # Construire le contexte pour l'IA
    inventory_context = []
    for item in inventory:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            # Calculer les jours avant expiration
            days_until_expiry = None
            if item.expiry_date:
                from datetime import date

                days_until_expiry = (item.expiry_date - date.today()).days

            inventory_context.append(
                {
                    "name": product.name,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "category": product.category,
                    "expiry_date": (
                        item.expiry_date.isoformat() if item.expiry_date else None
                    ),
                    "days_until_expiry": days_until_expiry,
                }
            )

    # Construire le prompt pour Gemini
    prompt = f"""Tu es l'assistant vocal d'un réfrigérateur intelligent. Réponds en français de manière naturelle et concise.

INVENTAIRE ACTUEL DU FRIGO:
{json.dumps(inventory_context, ensure_ascii=False, indent=2)}

QUESTION DE L'UTILISATEUR:
"{request.query}"

INSTRUCTIONS IMPORTANTES:
1. Réponds de manière conversationnelle et naturelle (comme si tu parlais à quelqu'un)
2. Sois précis sur les quantités et unités
3. Si un produit expire dans moins de 3 jours, MENTIONNE-LE explicitement
4. Si le produit n'existe pas, suggère des alternatives présentes dans le frigo
5. Pour les questions de recettes, suggère des idées UNIQUEMENT basées sur l'inventaire disponible
6. Limite ta réponse à 2-3 phrases maximum
7. Ne mentionne PAS les jours d'expiration si > 7 jours (sauf si demandé explicitement)
8. Utilise un ton amical et utile

RÉPONDS UNIQUEMENT LA RÉPONSE, PAS DE PRÉAMBULE NI D'INTRODUCTION."""

    try:
        # Initialiser le client Gemini
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Appeler Gemini
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[prompt],
        )

        ai_response = response.text.strip()

        logger.info(f"✅ AI Search successful for fridge {fridge_id}")

        # Sauvegarder dans l'historique (stocké dans fridge.config)
        if not fridge.config:
            fridge.config = {}

        if "search_history" not in fridge.config:
            fridge.config["search_history"] = []

        # Créer l'entrée d'historique
        history_entry = {
            "id": f"search_{datetime.utcnow().timestamp()}",
            "query": request.query,
            "response": ai_response,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Ajouter au début de la liste (les plus récents d'abord)
        fridge.config["search_history"].insert(0, history_entry)

        # Limiter à 100 entrées maximum
        fridge.config["search_history"] = fridge.config["search_history"][:100]

        # Marquer le champ comme modifié (important pour PostgreSQL JSONB)
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(fridge, "config")

        db.commit()

        logger.info(
            f"✅ Search saved to history (total: {len(fridge.config['search_history'])})"
        )

        return {
            "query": request.query,
            "response": ai_response,
            "timestamp": datetime.utcnow().isoformat(),
            "inventory_count": len(inventory_context),
        }

    except Exception as e:
        logger.error(f"❌ AI Search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Erreur lors de la recherche IA: {str(e)}"
        )


@router.get("/history", response_model=List[SearchHistoryResponse])
def get_search_history(
    fridge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    📜 Récupère l'historique des recherches pour un frigo

    Args:
        fridge_id: ID du frigo
        current_user: Utilisateur authentifié
        db: Session de base de données
        limit: Nombre maximum de résultats (défaut: 50)

    Returns:
        Liste des recherches précédentes (les plus récentes d'abord)
    """

    # Vérifier l'accès au frigo
    fridge = (
        db.query(Fridge)
        .filter(Fridge.id == fridge_id, Fridge.user_id == current_user.id)
        .first()
    )

    if not fridge:
        raise HTTPException(status_code=404, detail="Frigo non trouvé ou accès refusé")

    # Récupérer l'historique depuis config
    if not fridge.config or "search_history" not in fridge.config:
        return []

    history = fridge.config["search_history"][:limit]

    logger.info(
        f"📜 Retrieved {len(history)} search history entries for fridge {fridge_id}"
    )

    return history


@router.delete("/history", status_code=204)
def clear_search_history(
    fridge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    🗑️ Supprime tout l'historique de recherche pour un frigo

    Args:
        fridge_id: ID du frigo
        current_user: Utilisateur authentifié
        db: Session de base de données

    Returns:
        204 No Content
    """

    # Vérifier l'accès au frigo
    fridge = (
        db.query(Fridge)
        .filter(Fridge.id == fridge_id, Fridge.user_id == current_user.id)
        .first()
    )

    if not fridge:
        raise HTTPException(status_code=404, detail="Frigo non trouvé ou accès refusé")

    # Supprimer l'historique
    if fridge.config and "search_history" in fridge.config:
        deleted_count = len(fridge.config["search_history"])
        fridge.config["search_history"] = []

        # Marquer comme modifié
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(fridge, "config")

        db.commit()

        logger.info(
            f"🗑️ Deleted {deleted_count} search history entries for fridge {fridge_id}"
        )

    return None
