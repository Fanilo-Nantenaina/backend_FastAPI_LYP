from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.fridge import Fridge
from app.models.alert import Alert
from app.services.alert_service import AlertService
from app.schemas.alert import AlertResponse, AlertUpdateRequest

router = APIRouter(prefix="/fridges/{fridge_id}/alerts", tags=["Alerts"])


def get_fridge_access_hybrid(
    fridge_id: int,
    x_kiosk_id: Optional[str] = Header(None, alias="X-Kiosk-ID"),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Fridge:
    """Auth hybride : kiosk OU user mobile"""

    if x_kiosk_id:
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
                status_code=403,
                detail="Access denied to this fridge or fridge not paired",
            )

        return fridge

    elif current_user:
        fridge = (
            db.query(Fridge)
            .filter(
                Fridge.id == fridge_id,
                Fridge.user_id == current_user.id,
            )
            .first()
        )

        if not fridge:
            raise HTTPException(
                status_code=404,
                detail="Fridge not found or access denied",
            )

        return fridge

    else:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )


@router.get("", response_model=List[AlertResponse])
def list_alerts(
    fridge: Fridge = Depends(get_fridge_access_hybrid),
    db: Session = Depends(get_db),
    status: str = None,
):
    """Liste les alertes - COMPATIBLE MOBILE ET KIOSK"""
    query = db.query(Alert).filter(Alert.fridge_id == fridge.id)

    if status:
        query = query.filter(Alert.status == status)
        return query.order_by(Alert.resolved_at.desc()).all()

    return query.order_by(Alert.created_at.desc()).all()


@router.put("/{alert_id}", response_model=AlertResponse)
def update_alert_status(
    alert_id: int,
    request: AlertUpdateRequest,
    fridge: Fridge = Depends(get_fridge_access_hybrid),
    db: Session = Depends(get_db),
):
    """Met à jour le statut d'une alerte - COMPATIBLE MOBILE ET KIOSK"""
    alert = (
        db.query(Alert)
        .filter(Alert.id == alert_id, Alert.fridge_id == fridge.id)
        .first()
    )

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if request.status:
        alert.status = request.status
        alert.resolved_at = datetime.utcnow()

    db.commit()
    db.refresh(alert)
    return alert


@router.post("/trigger-check")
def trigger_alert_check(
    fridge: Fridge = Depends(get_fridge_access_hybrid), db: Session = Depends(get_db)
):
    """Déclenche une vérification manuelle - COMPATIBLE MOBILE ET KIOSK"""
    alert_service = AlertService(db)
    alert_service.check_and_create_alerts(fridge_id=fridge.id)

    return {"message": "Alert check completed"}
