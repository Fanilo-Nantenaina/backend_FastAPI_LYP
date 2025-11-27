"""Tests des alertes"""

import pytest
from datetime import date, timedelta


def test_list_alerts(client, auth_headers, test_fridge):
    """CU8: Test de liste des alertes"""
    response = client.get(
        f"/api/v1/fridges/{test_fridge.id}/alerts", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_trigger_alert_check(client, auth_headers, test_fridge):
    """CU7: Test de déclenchement manuel de vérification"""
    response = client.post(
        f"/api/v1/fridges/{test_fridge.id}/alerts/trigger-check", headers=auth_headers
    )
    assert response.status_code == 200


def test_alert_creation_expiry(db, test_fridge, test_product):
    """Test de création d'alerte pour péremption (RG10)"""
    from app.models.inventory import InventoryItem
    from app.services.alert_service import AlertService

    # Créer un item qui expire demain
    item = InventoryItem(
        fridge_id=test_fridge.id,
        product_id=test_product.id,
        quantity=5,
        expiry_date=date.today() + timedelta(days=1),
    )
    db.add(item)
    db.commit()

    # Déclencher la vérification
    alert_service = AlertService(db)
    stats = alert_service.check_and_create_alerts(
        fridge_id=test_fridge.id, send_notifications=False
    )

    assert stats["EXPIRY_SOON"] >= 1


def test_alert_no_duplicate(db, test_fridge, test_product):
    """Test RG12: Pas de duplication d'alertes"""
    from app.models.inventory import InventoryItem
    from app.services.alert_service import AlertService

    item = InventoryItem(
        fridge_id=test_fridge.id,
        product_id=test_product.id,
        quantity=5,
        expiry_date=date.today() + timedelta(days=1),
    )
    db.add(item)
    db.commit()

    alert_service = AlertService(db)

    # Première vérification
    stats1 = alert_service.check_and_create_alerts(
        fridge_id=test_fridge.id, send_notifications=False
    )

    # Deuxième vérification (ne devrait pas créer de nouvelle alerte)
    stats2 = alert_service.check_and_create_alerts(
        fridge_id=test_fridge.id, send_notifications=False
    )

    # Le deuxième run ne devrait pas créer de nouvelles alertes
    assert stats2["EXPIRY_SOON"] == 0
