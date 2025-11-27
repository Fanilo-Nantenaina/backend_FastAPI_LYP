# ==========================================
# app/services/notification_service.py
# ==========================================
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

from app.models.user import User
from app.models.alert import Alert
from app.models.inventory import InventoryItem
from app.core.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service de notifications multi-canal : Email, Push, SMS
    Gère l'envoi des alertes aux utilisateurs
    """

    def __init__(self, db: Session):
        self.db = db

    # ==========================================
    # EMAIL NOTIFICATIONS
    # ==========================================

    def send_email_notification(
        self, user_email: str, subject: str, body: str, html_body: Optional[str] = None
    ) -> bool:
        """
        Envoie une notification par email

        Configuration nécessaire dans .env :
        - SMTP_HOST=smtp.gmail.com
        - SMTP_PORT=587
        - SMTP_USER=your-email@gmail.com
        - SMTP_PASSWORD=your-app-password
        - SMTP_FROM_EMAIL=noreply@smartfridge.com
        """
        try:
            smtp_host = getattr(settings, "SMTP_HOST", "smtp.gmail.com")
            smtp_port = getattr(settings, "SMTP_PORT", 587)
            smtp_user = getattr(settings, "SMTP_USER", None)
            smtp_password = getattr(settings, "SMTP_PASSWORD", None)
            from_email = getattr(settings, "SMTP_FROM_EMAIL", "noreply@smartfridge.com")

            if not smtp_user or not smtp_password:
                logger.warning("SMTP credentials not configured")
                return False

            # Créer le message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_email
            msg["To"] = user_email

            # Ajouter le corps en texte brut
            text_part = MIMEText(body, "plain", "utf-8")
            msg.attach(text_part)

            # Ajouter le corps HTML si fourni
            if html_body:
                html_part = MIMEText(html_body, "html", "utf-8")
                msg.attach(html_part)

            # Envoyer l'email
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            logger.info(f"Email sent successfully to {user_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {user_email}: {e}")
            return False

    def send_alert_email(self, alert: Alert, user: User) -> bool:
        """Envoie un email pour une alerte spécifique"""
        subject = self._get_alert_email_subject(alert)
        body = self._get_alert_email_body(alert)
        html_body = self._get_alert_email_html(alert)

        return self.send_email_notification(
            user_email=user.email, subject=subject, body=body, html_body=html_body
        )

    def _get_alert_email_subject(self, alert: Alert) -> str:
        """Génère le sujet de l'email selon le type d'alerte"""
        subjects = {
            "EXPIRY_SOON": "⚠️ Produits à consommer rapidement",
            "EXPIRED": "🚫 Produits périmés dans votre frigo",
            "LOST_ITEM": "🔍 Produits non détectés récemment",
            "LOW_STOCK": "📉 Stock faible",
        }
        return subjects.get(alert.type, "📬 Alerte Smart Fridge")

    def _get_alert_email_body(self, alert: Alert) -> str:
        """Génère le corps texte de l'email"""
        return f"""
Bonjour,

Vous avez une nouvelle alerte concernant votre réfrigérateur :

{alert.message}

Type d'alerte : {alert.type}
Date : {alert.created_at.strftime('%d/%m/%Y %H:%M')}

Connectez-vous à votre application Smart Fridge pour plus de détails.

Cordialement,
L'équipe Smart Fridge
        """

    def _get_alert_email_html(self, alert: Alert) -> str:
        """Génère le corps HTML de l'email"""
        icon_map = {
            "EXPIRY_SOON": "⚠️",
            "EXPIRED": "🚫",
            "LOST_ITEM": "🔍",
            "LOW_STOCK": "📉",
        }
        icon = icon_map.get(alert.type, "📬")

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                   color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
        .alert-box {{ background: white; padding: 20px; border-left: 4px solid #667eea; 
                      margin: 20px 0; border-radius: 5px; }}
        .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #666; }}
        .button {{ background: #667eea; color: white; padding: 12px 30px; 
                   text-decoration: none; border-radius: 5px; display: inline-block; 
                   margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{icon} Smart Fridge</h1>
            <p>Nouvelle alerte de votre réfrigérateur</p>
        </div>
        <div class="content">
            <div class="alert-box">
                <h2 style="margin-top: 0;">📋 {alert.type.replace('_', ' ').title()}</h2>
                <p style="font-size: 16px;">{alert.message}</p>
                <p style="color: #666; font-size: 14px;">
                    Date : {alert.created_at.strftime('%d/%m/%Y à %H:%M')}
                </p>
            </div>
            <p>Consultez votre application pour gérer cette alerte et voir les détails complets.</p>
            <a href="https://smartfridge.app/alerts/{alert.id}" class="button">
                Voir l'alerte
            </a>
        </div>
        <div class="footer">
            <p>© 2025 Smart Fridge - Votre cuisine intelligente</p>
        </div>
    </div>
</body>
</html>
        """

    def send_daily_summary_email(self, user: User, fridge_id: int) -> bool:
        """Envoie un résumé quotidien de l'état du frigo"""
        from app.models.fridge import Fridge

        fridge = self.db.query(Fridge).filter(Fridge.id == fridge_id).first()
        if not fridge:
            return False

        # Récupérer les alertes pending
        pending_alerts = (
            self.db.query(Alert)
            .filter(Alert.fridge_id == fridge_id, Alert.status == "pending")
            .all()
        )

        # Récupérer l'inventaire actif
        inventory_count = (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .count()
        )

        subject = f"📊 Résumé quotidien - {fridge.name}"

        body = f"""
Bonjour {user.name or 'cher utilisateur'},

Voici le résumé quotidien de votre frigo "{fridge.name}" :

📦 Articles en stock : {inventory_count}
⚠️ Alertes en attente : {len(pending_alerts)}

{'=' * 50}
ALERTES EN ATTENTE :
{'=' * 50}

"""

        if pending_alerts:
            for alert in pending_alerts:
                body += f"• [{alert.type}] {alert.message}\n"
        else:
            body += "Aucune alerte en attente. Tout va bien ! ✅\n"

        body += f"""

{'=' * 50}

Consultez votre application pour plus de détails.

Bonne journée !
L'équipe Smart Fridge
        """

        return self.send_email_notification(
            user_email=user.email, subject=subject, body=body
        )

    # ==========================================
    # PUSH NOTIFICATIONS
    # ==========================================

    def send_push_notification(
        self, user_id: int, title: str, body: str, data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Envoie une notification push via Firebase Cloud Messaging (FCM)

        Configuration nécessaire dans .env :
        - FCM_SERVER_KEY=your-fcm-server-key

        Les device tokens doivent être stockés dans la table fridge_devices
        """
        try:
            import requests

            fcm_server_key = getattr(settings, "FCM_SERVER_KEY", None)
            if not fcm_server_key:
                logger.warning("FCM server key not configured")
                return False

            # Récupérer les device tokens de l'utilisateur
            from app.models.device import FridgeDevice
            from app.models.fridge import Fridge

            devices = (
                self.db.query(FridgeDevice)
                .join(Fridge)
                .filter(
                    Fridge.user_id == user_id,
                    FridgeDevice.is_paired == True,
                    FridgeDevice.device_type.in_(["mobile", "tablet"]),
                )
                .all()
            )

            if not devices:
                logger.info(f"No mobile devices found for user {user_id}")
                return False

            # Préparer le payload
            notification_payload = {
                "title": title,
                "body": body,
                "sound": "default",
                "badge": "1",
            }

            # Envoyer à chaque appareil
            success_count = 0
            for device in devices:
                # Note: device.metadata devrait contenir le FCM token
                fcm_token = (
                    device.metadata.get("fcm_token") if device.metadata else None
                )

                if not fcm_token:
                    continue

                payload = {
                    "to": fcm_token,
                    "notification": notification_payload,
                    "data": data or {},
                    "priority": "high",
                }

                headers = {
                    "Authorization": f"key={fcm_server_key}",
                    "Content-Type": "application/json",
                }

                response = requests.post(
                    "https://fcm.googleapis.com/fcm/send", json=payload, headers=headers
                )

                if response.status_code == 200:
                    success_count += 1
                    logger.info(f"Push notification sent to device {device.device_id}")
                else:
                    logger.error(
                        f"Failed to send push to device {device.device_id}: {response.text}"
                    )

            return success_count > 0

        except Exception as e:
            logger.error(f"Failed to send push notification: {e}")
            return False

    def send_alert_push(self, alert: Alert, user_id: int) -> bool:
        """Envoie une notification push pour une alerte"""
        title_map = {
            "EXPIRY_SOON": "⚠️ Produits à consommer",
            "EXPIRED": "🚫 Produits périmés",
            "LOST_ITEM": "🔍 Produit non détecté",
            "LOW_STOCK": "📉 Stock faible",
        }

        title = title_map.get(alert.type, "📬 Nouvelle alerte")

        return self.send_push_notification(
            user_id=user_id,
            title=title,
            body=alert.message,
            data={
                "alert_id": alert.id,
                "alert_type": alert.type,
                "fridge_id": alert.fridge_id,
                "action": "open_alert",
            },
        )

    # ==========================================
    # SMS NOTIFICATIONS (via Twilio)
    # ==========================================

    def send_sms_notification(self, phone_number: str, message: str) -> bool:
        """
        Envoie une notification par SMS via Twilio

        Configuration nécessaire dans .env :
        - TWILIO_ACCOUNT_SID=your-account-sid
        - TWILIO_AUTH_TOKEN=your-auth-token
        - TWILIO_PHONE_NUMBER=your-twilio-number
        """
        try:
            from twilio.rest import Client

            account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
            auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
            from_number = getattr(settings, "TWILIO_PHONE_NUMBER", None)

            if not all([account_sid, auth_token, from_number]):
                logger.warning("Twilio credentials not configured")
                return False

            client = Client(account_sid, auth_token)

            message = client.messages.create(
                body=message, from_=from_number, to=phone_number
            )

            logger.info(f"SMS sent successfully to {phone_number}: {message.sid}")
            return True

        except Exception as e:
            logger.error(f"Failed to send SMS to {phone_number}: {e}")
            return False

    def send_alert_sms(self, alert: Alert, user: User) -> bool:
        """Envoie un SMS pour une alerte critique"""
        # Récupérer le numéro de téléphone (devrait être dans user.metadata)
        if not user.metadata or "phone_number" not in user.metadata:
            logger.info(f"No phone number for user {user.id}")
            return False

        phone_number = user.metadata["phone_number"]

        message = f"Smart Fridge Alert: {alert.message}. Consultez l'app pour plus de détails."

        return self.send_sms_notification(phone_number, message)

    # ==========================================
    # MÉTHODE UNIFIÉE
    # ==========================================

    def notify_alert(
        self, alert: Alert, user: User, channels: List[str] = ["push", "email"]
    ) -> Dict[str, bool]:
        """
        Envoie une notification sur plusieurs canaux

        Args:
            alert: L'alerte à notifier
            user: L'utilisateur à notifier
            channels: Liste des canaux ('push', 'email', 'sms')

        Returns:
            Dict avec le statut de chaque canal
        """
        results = {}

        if "email" in channels:
            results["email"] = self.send_alert_email(alert, user)

        if "push" in channels:
            results["push"] = self.send_alert_push(alert, user.id)

        if "sms" in channels:
            results["sms"] = self.send_alert_sms(alert, user)

        return results

    def notify_expiry_batch(self, fridge_id: int, user: User) -> bool:
        """
        Envoie une notification groupée pour plusieurs produits proches de l'expiration
        """
        from datetime import date, timedelta

        # Récupérer tous les items qui expirent dans les 3 prochains jours
        warning_date = date.today() + timedelta(days=3)

        expiring_items = (
            self.db.query(InventoryItem)
            .filter(
                InventoryItem.fridge_id == fridge_id,
                InventoryItem.quantity > 0,
                InventoryItem.expiry_date <= warning_date,
                InventoryItem.expiry_date >= date.today(),
            )
            .all()
        )

        if not expiring_items:
            return False

        # Construire le message
        items_list = "\n".join(
            [
                f"• {item.product.name} - expire le {item.expiry_date.strftime('%d/%m/%Y')}"
                for item in expiring_items
            ]
        )

        subject = f"⚠️ {len(expiring_items)} produits à consommer rapidement"
        body = f"""
Bonjour {user.name or 'cher utilisateur'},

Vous avez {len(expiring_items)} produit(s) qui vont bientôt expirer :

{items_list}

Pensez à les consommer avant leur date de péremption !

Cordialement,
L'équipe Smart Fridge
        """

        return self.send_email_notification(
            user_email=user.email, subject=subject, body=body
        )
