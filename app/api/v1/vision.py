from fastapi import APIRouter, File, UploadFile, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.core.dependencies import get_user_fridge
from app.models.fridge import Fridge
from app.services.vision_service import VisionService
from app.schemas.vision import (
    VisionAnalysisResponse,
    ManualEntryRequest,
    DetectedProductMatch,
    ConsumeAnalysisResponse,
)
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime

router = APIRouter(prefix="/fridges/{fridge_id}/vision", tags=["Vision AI"])


@router.post("/analyze", response_model=VisionAnalysisResponse)
async def analyze_fridge_image(
    fridge_id: int,
    file: UploadFile = File(...),
    x_kiosk_id: Optional[str] = Header(None, alias="X-Kiosk-ID"),
    db: Session = Depends(get_db),
):
    """

    CU2: Enregistrer un Article via IA/Vision

    Cette route analyse une image du frigo et :
    1. Détecte les produits visibles
    2. Estime les quantités
    3. Lit les textes (OCR) pour identifier les produits emballés
    4. Met à jour l'inventaire automatiquement
    5. Demande confirmation manuelle si date de péremption non détectable
    """

    if not x_kiosk_id:
        raise HTTPException(status_code=401, detail="X-Kiosk-ID header required")

    fridge = (
        db.query(Fridge)
        .filter(
            Fridge.id == fridge_id,
            Fridge.kiosk_id == x_kiosk_id,
            Fridge.is_paired == True,
        )
        .first()
    )

    if not fridge:
        raise HTTPException(
            status_code=403, detail="Access denied to this fridge or fridge not paired"
        )

    vision_service = VisionService(db)

    try:
        result = await vision_service.analyze_and_update_inventory(
            image_file=file, fridge_id=fridge.id
        )
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vision analysis failed: {str(e)}")


@router.post("/manual-entry", status_code=200)
async def manual_expiry_entry(
    fridge_id: int,
    request: ManualEntryRequest,
    x_kiosk_id: Optional[str] = Header(None, alias="X-Kiosk-ID"),
    db: Session = Depends(get_db),
):
    """

    Entrée manuelle de la date de péremption si non détectée par l'IA

    L'utilisateur reçoit une notification si l'IA n'a pas pu détecter
    la date de péremption, et peut la saisir via cette route.
    """

    if not x_kiosk_id:
        raise HTTPException(status_code=401, detail="X-Kiosk-ID header required")

    fridge = (
        db.query(Fridge)
        .filter(
            Fridge.id == fridge_id,
            Fridge.kiosk_id == x_kiosk_id,
            Fridge.is_paired == True,
        )
        .first()
    )

    if not fridge:
        raise HTTPException(status_code=403, detail="Access denied to this fridge")

    vision_service = VisionService(db)

    try:
        updated_item = vision_service.update_expiry_date_manually(
            item_id=request.inventory_item_id,
            fridge_id=fridge.id,
            expiry_date=request.expiry_date,
        )

        if updated_item is None:
            raise HTTPException(
                status_code=404,
                detail=f"Item with ID {request.inventory_item_id} not found in fridge {fridge.id}",
            )

        return {"message": "Expiry date updated successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Manual update failed: {str(e)}")


@router.post("/analyze-consume", response_model=ConsumeAnalysisResponse)
async def analyze_for_consumption(
    fridge_id: int,
    file: UploadFile = File(...),
    x_kiosk_id: Optional[str] = Header(None, alias="X-Kiosk-ID"),
    db: Session = Depends(get_db),
):
    """
    NOUVEAU : Analyse d'image pour SORTIE de produits

    Flow:
    1. Détecte produits via Gemini (comme /analyze)
    2. Pour chaque produit détecté → cherche correspondance dans inventaire
    3. Retourne liste avec matching automatique + alternatives
    4. Frontend confirme → route PATCH /consume-batch fait la soustraction
    """

    if not x_kiosk_id:
        raise HTTPException(status_code=401, detail="X-Kiosk-ID required")

    fridge = (
        db.query(Fridge)
        .filter(
            Fridge.id == fridge_id,
            Fridge.kiosk_id == x_kiosk_id,
            Fridge.is_paired == True,
        )
        .first()
    )

    if not fridge:
        raise HTTPException(status_code=403, detail="Access denied")

    vision_service = VisionService(db)

    detected_products = await vision_service._analyze_image_with_gemini(file)

    matched_results = []
    requires_review = False

    for detected in detected_products:
        match_result = await vision_service.find_best_inventory_match(
            fridge_id=fridge_id,
            detected_name=detected.product_name,
            detected_category=detected.category,
            detected_count=detected.count,
        )

        matched_results.append(match_result)

        if match_result.match_score is None or match_result.match_score < 80:
            requires_review = True

    return ConsumeAnalysisResponse(
        timestamp=datetime.utcnow().isoformat(),
        detected_count=len(detected_products),
        detected_products=matched_results,
        requires_manual_review=requires_review,
    )
