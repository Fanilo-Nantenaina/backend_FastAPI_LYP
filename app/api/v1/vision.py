from fastapi import APIRouter, File, UploadFile, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_user_fridge
from app.models.fridge import Fridge
from app.services.vision_service import VisionService
from app.schemas.vision import VisionAnalysisResponse, ManualEntryRequest

router = APIRouter(prefix="/fridges/{fridge_id}/vision", tags=["Vision AI"])


@router.post("/analyze", response_model=VisionAnalysisResponse)
async def analyze_fridge_image(
    file: UploadFile = File(...),
    fridge: Fridge = Depends(get_user_fridge),
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
    vision_service = VisionService(db)

    try:
        result = await vision_service.analyze_and_update_inventory(
            image_file=file, fridge_id=fridge.id
        )
        return result

    except Exception as e:
        # Il est généralement préférable de loguer l'erreur avant de renvoyer 500
        # et de donner un message d'erreur générique si l'erreur interne est sensible.
        raise HTTPException(status_code=500, detail=f"Vision analysis failed: {str(e)}")


@router.post(
    "/manual-entry", status_code=200
)  # Changé 201 en 200 car c'est une mise à jour
async def manual_expiry_entry(
    request: ManualEntryRequest,
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
):
    """
    Entrée manuelle de la date de péremption si non détectée par l'IA

    L'utilisateur reçoit une notification si l'IA n'a pas pu détecter
    la date de péremption, et peut la saisir via cette route.
    """
    vision_service = VisionService(db)

    try:
        # Met à jour la date de péremption pour un article spécifique (request.item_id)
        # qui appartient au frigo actuel (fridge.id).
        updated_item = vision_service.update_expiry_date_manually(
            item_id=request.item_id,
            fridge_id=fridge.id,
            expiry_date=request.expiry_date,
        )

        if updated_item is None:
            # Lève une 404 si l'item n'est pas trouvé dans ce frigo
            raise HTTPException(
                status_code=404,
                detail=f"Item with ID {request.item_id} not found in fridge {fridge.id}",
            )

        # Si la mise à jour est réussie, on pourrait retourner l'item mis à jour,
        # mais la description n'inclut pas de response_model, on retourne donc un succès.
        return {"message": "Expiry date updated successfully"}

    except Exception as e:
        # Gestion d'une erreur interne du service (e.g., problème de base de données)
        raise HTTPException(status_code=500, detail=f"Manual update failed: {str(e)}")
