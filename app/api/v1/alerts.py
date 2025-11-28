from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.dependencies import get_user_fridge, get_current_user
from app.models.fridge import Fridge
from app.models.alert import Alert
from app.models.user import User
from app.services.alert_service import AlertService
from app.schemas.alert import AlertResponse, AlertUpdateRequest

router = APIRouter(prefix="/fridges/{fridge_id}/alerts", tags=["Alerts"])


@router.get("", response_model=List[AlertResponse])
def list_alerts(
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
    status: str = None,
):
    query = db.query(Alert).filter(Alert.fridge_id == fridge.id)

    if status:
        query = query.filter(Alert.status == status)

    return query.order_by(Alert.created_at.desc()).all()


@router.put("/{alert_id}", response_model=AlertResponse)
def update_alert_status(
    alert_id: int,
    request: AlertUpdateRequest,
    fridge: Fridge = Depends(get_user_fridge),
    db: Session = Depends(get_db),
):
    alert = (
        db.query(Alert)
        .filter(Alert.id == alert_id, Alert.fridge_id == fridge.id)
        .first()
    )

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if request.status:
        alert.status = request.status

    db.commit()
    db.refresh(alert)
    return alert


@router.post("/trigger-check")
def trigger_alert_check(
    fridge: Fridge = Depends(get_user_fridge), db: Session = Depends(get_db)
):
    alert_service = AlertService(db)
    alert_service.check_and_create_alerts(fridge_id=fridge.id)

    return {"message": "Alert check completed"}
