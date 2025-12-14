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
from app.models.fridge import Fridge
from app.core.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service de notifications multi-canal : Email, Push, SMS
    Gère l'envoi des alertes aux utilisateurs
    """

    def __init__(self, db: Session):
        self.db = db

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

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_email
            msg["To"] = user_email

            text_part = MIMEText(body, "plain", "utf-8")
            msg.attach(text_part)

            if html_body:
                html_part = MIMEText(html_body, "html", "utf-8")
                msg.attach(html_part)

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
            "EXPIRY_SOON": "Produits à consommer rapidement",
            "EXPIRED": "Produits périmés dans votre frigo",
            "LOST_ITEM": "Produits non détectés récemment",
            "LOW_STOCK": "Stock faible",
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
                <h2 style="margin-top: 0;">{alert.type.replace('_', ' ').title()}</h2>
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
        fridge = self.db.query(Fridge).filter(Fridge.id == fridge_id).first()
        if not fridge:
            return False

        pending_alerts = (
            self.db.query(Alert)
            .filter(Alert.fridge_id == fridge_id, Alert.status == "pending")
            .all()
        )

        inventory_count = (
            self.db.query(InventoryItem)
            .filter(InventoryItem.fridge_id == fridge_id, InventoryItem.quantity > 0)
            .count()
        )

        subject = f"Résumé quotidien - {fridge.name}"

        body = f"""
Bonjour {user.name or 'cher utilisateur'},

Voici le résumé quotidien de votre frigo "{fridge.name}" :

        - Articles en stock : {inventory_count}
        - Alertes en attente : {len(pending_alerts)}

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

    def _sanitize_fcm_data(self, data: Optional[Dict[str, Any]]) -> Dict[str, str]:
        """
        Convertit toutes les valeurs en strings pour FCM

        FCM n'accepte que des strings dans le champ 'data'.
        Convertit : int → str, bool → "true"/"false", None → ""
        """
        if not data:
            return {}

        safe_data = {}
        for key, value in data.items():
            if value is None:
                safe_data[key] = ""
            elif isinstance(value, bool):
                safe_data[key] = "true" if value else "false"
            else:
                safe_data[key] = str(value)

        return safe_data

    def send_push_notification(
        self, user_id: int, title: str, body: str, data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Envoie une notification push via Firebase Cloud Messaging (FCM)
        VERSION MODERNE avec firebase-admin SDK

        Args:
            user_id: ID de l'utilisateur
            title: Titre de la notification
            body: Corps du message
            data: Données supplémentaires (seront converties en strings)

        Returns:
            True si au moins une notification a été envoyée avec succès
        """
        try:
            import firebase_admin
            from firebase_admin import credentials, messaging

            # Initialiser Firebase Admin SDK (une seule fois)
            if not firebase_admin._apps:
                cred = credentials.Certificate(
                    "smart-fridge-357b0-firebase-adminsdk-fbsvc-e5dbd0f2cb.json"
                )
                firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin SDK initialized")

            # Récupérer les tokens FCM depuis les frigos de l'utilisateur
            fridges = (
                self.db.query(Fridge)
                .filter(Fridge.user_id == user_id, Fridge.is_paired == True)
                .all()
            )

            if not fridges:
                logger.info(f"No paired fridges found for user {user_id}")
                return False

            # Sanitizer les données (convertir en strings)
            safe_data = self._sanitize_fcm_data(data)

            success_count = 0

            # Parcourir les frigos pour envoyer aux tokens FCM
            for fridge in fridges:
                fcm_tokens = []

                if fridge.kiosk_metadata:
                    if "fcm_tokens" in fridge.kiosk_metadata:
                        fcm_tokens = fridge.kiosk_metadata["fcm_tokens"]
                    elif "fcm_token" in fridge.kiosk_metadata:
                        fcm_tokens = [fridge.kiosk_metadata["fcm_token"]]

                for fcm_token in fcm_tokens:
                    if not fcm_token:
                        continue

                    # Créer le message Firebase
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title=title,
                            body=body,
                        ),
                        data=safe_data,  # Toutes les valeurs sont des strings
                        token=fcm_token,
                        android=messaging.AndroidConfig(
                            priority="high",
                            notification=messaging.AndroidNotification(
                                sound="default",
                                channel_id="smart_fridge_alerts",
                                color="#3B82F6",  # Couleur bleue
                            ),
                        ),
                        apns=messaging.APNSConfig(
                            payload=messaging.APNSPayload(
                                aps=messaging.Aps(
                                    sound="default",
                                    badge=1,
                                    content_available=True,
                                ),
                            ),
                        ),
                    )

                    # Envoyer via Firebase Admin SDK
                    try:
                        response = messaging.send(message)
                        success_count += 1
                        logger.info(
                            f"Push notification sent to fridge {fridge.id}: {response}"
                        )
                    except messaging.UnregisteredError:
                        logger.warning(
                            f"Token invalid/expired for fridge {fridge.id}, "
                            f"removing from database"
                        )
                        # Supprimer le token invalide
                        if "fcm_tokens" in fridge.kiosk_metadata:
                            fridge.kiosk_metadata["fcm_tokens"].remove(fcm_token)
                            from sqlalchemy.orm.attributes import flag_modified

                            flag_modified(fridge, "kiosk_metadata")
                            self.db.commit()

                    except Exception as e:
                        logger.error(f"Failed to send push to fridge {fridge.id}: {e}")

            return success_count > 0

        except Exception as e:
            logger.error(f"Failed to send push notification: {e}", exc_info=True)
            return False

    def send_alert_push(self, alert: Alert, user_id: int) -> bool:
        """Envoie une notification push pour une alerte"""
        title_map = {
            "EXPIRY_SOON": "Produits à consommer",
            "EXPIRED": "Produits périmés",
            "LOST_ITEM": "Produit non détecté",
            "LOW_STOCK": "Stock faible",
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
        if not user.prefs or "phone_number" not in user.prefs:
            logger.info(f"No phone number for user {user.id}")
            return False

        phone_number = user.prefs["phone_number"]

        message = f"Smart Fridge Alert: {alert.message}. Consultez l'app pour plus de détails."

        return self.send_sms_notification(phone_number, message)

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

        items_list = "\n".join(
            [
                f"• {item.product.name} - expire le {item.expiry_date.strftime('%d/%m/%Y')}"
                for item in expiring_items
            ]
        )

        subject = f"{len(expiring_items)} produits à consommer rapidement"
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

    def register_fcm_token(self, fridge_id: int, fcm_token: str, user_id: int) -> bool:
        """
        NOUVEAU : Enregistre un token FCM pour un frigo

        Appelé par l'app mobile après le pairing pour enregistrer son token FCM

        Args:
            fridge_id: ID du frigo
            fcm_token: Token FCM de l'appareil mobile
            user_id: ID de l'utilisateur (pour vérifier la propriété)

        Returns:
            True si enregistré avec succès
        """
        try:
            fridge = (
                self.db.query(Fridge)
                .filter(Fridge.id == fridge_id, Fridge.user_id == user_id)
                .first()
            )

            if not fridge:
                logger.warning(f"Fridge {fridge_id} not found for user {user_id}")
                return False

            # Initialiser kiosk_metadata si nécessaire
            if not fridge.kiosk_metadata:
                fridge.kiosk_metadata = {}

            # Ajouter le token à la liste (éviter les doublons)
            if "fcm_tokens" not in fridge.kiosk_metadata:
                fridge.kiosk_metadata["fcm_tokens"] = []

            if fcm_token not in fridge.kiosk_metadata["fcm_tokens"]:
                fridge.kiosk_metadata["fcm_tokens"].append(fcm_token)
                self.db.commit()
                logger.info(f"FCM token registered for fridge {fridge_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to register FCM token: {e}")
            self.db.rollback()
            return False

    def unregister_fcm_token(
        self, fridge_id: int, fcm_token: str, user_id: int
    ) -> bool:
        """
        NOUVEAU : Supprime un token FCM pour un frigo

        Appelé quand l'utilisateur se déconnecte ou désinstalle l'app

        Args:
            fridge_id: ID du frigo
            fcm_token: Token FCM à supprimer
            user_id: ID de l'utilisateur (pour vérifier la propriété)

        Returns:
            True si supprimé avec succès
        """
        try:
            fridge = (
                self.db.query(Fridge)
                .filter(Fridge.id == fridge_id, Fridge.user_id == user_id)
                .first()
            )

            if not fridge or not fridge.kiosk_metadata:
                return False

            if "fcm_tokens" in fridge.kiosk_metadata:
                if fcm_token in fridge.kiosk_metadata["fcm_tokens"]:
                    fridge.kiosk_metadata["fcm_tokens"].remove(fcm_token)
                    self.db.commit()
                    logger.info(f"FCM token unregistered for fridge {fridge_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to unregister FCM token: {e}")
            self.db.rollback()
            return False

    def send_inventory_notification(
        self,
        fridge_id: int,
        action: str,
        product_name: str,
        quantity: float = None,
        unit: str = None,
        source: str = "manual",
    ) -> bool:
        """
        📦 NOUVEAU : Envoie une notification pour une action d'inventaire

        Args:
            fridge_id: ID du frigo
            action: "added", "updated", "consumed", "removed"
            product_name: Nom du produit
            quantity: Quantité (optionnel)
            unit: Unité (optionnel)
            source: "manual", "vision", "scan"

        Returns:
            True si envoyé avec succès
        """
        try:
            # Récupérer le frigo et l'utilisateur
            fridge = self.db.query(Fridge).filter(Fridge.id == fridge_id).first()
            if not fridge or not fridge.user_id:
                logger.warning(f"Fridge {fridge_id} not found or no user")
                return False

            # Construire le titre et le message
            title_map = {
                "added": "📦 Produit ajouté",
                "updated": "✏️ Produit modifié",
                "consumed": "🍽️ Produit consommé",
                "removed": "🗑️ Produit retiré",
            }

            title = title_map.get(action, "📦 Inventaire mis à jour")

            # Message détaillé
            if quantity and unit:
                body = f"{product_name} : {quantity} {unit}"
            else:
                body = product_name

            # Ajouter la source si c'est un scan
            if source == "vision":
                body += " (scan IA)"

            # Envoyer la notification push
            return self.send_push_notification(
                user_id=fridge.user_id,
                title=title,
                body=body,
                data={
                    "action": action,
                    "product_name": product_name,
                    "fridge_id": fridge_id,
                    "source": source,
                    "type": "inventory_update",
                },
            )

        except Exception as e:
            logger.error(f"Failed to send inventory notification: {e}")
            return False

    def send_smart_inventory_notification(
        self,
        fridge_id: int,
        action: str,
        product_name: str,
        quantity: float = None,
        remaining_quantity: float = None,
        unit: str = None,
        freshness_status: str = "unknown",
        expiry_date=None,
        source: str = "manual",
    ) -> bool:
        """
        Notifications intelligentes et contextuelles

        Génère des messages humains et engageants selon le contexte
        """
        from datetime import date

        # Récupérer le frigo et l'utilisateur
        fridge = self.db.query(Fridge).filter(Fridge.id == fridge_id).first()
        if not fridge or not fridge.user_id:
            logger.warning(f"Fridge {fridge_id} not found or no user")
            return False

        # GÉNÉRATION CONTEXTUELLE DU MESSAGE
        title, body, emoji = self._generate_smart_message(
            action=action,
            product_name=product_name,
            quantity=quantity,
            remaining_quantity=remaining_quantity,
            unit=unit,
            freshness_status=freshness_status,
            expiry_date=expiry_date,
            source=source,
        )

        # Envoyer la notification push
        return self.send_push_notification(
            user_id=fridge.user_id,
            title=title,
            body=body,
            data={
                "action": action,
                "product_name": product_name,
                "fridge_id": fridge_id,
                "source": source,
                "type": "inventory_update",
                "freshness_status": freshness_status,
            },
        )

    def _generate_smart_message(
        self,
        action: str,
        product_name: str,
        quantity: float = None,
        remaining_quantity: float = None,
        unit: str = None,
        freshness_status: str = "unknown",
        expiry_date=None,
        source: str = "manual",
    ) -> tuple:
        """
        🧠 INTELLIGENCE ARTIFICIELLE CONTEXTUELLE

        Génère des messages humains selon le contexte complet

        Returns:
            (title, body, emoji)
        """
        from datetime import date

        # ==========================================
        # 🍽️ ACTION : CONSOMMATION
        # ==========================================
        if action == "consumed":

            # 🚨 CAS 1 : Produit EXPIRÉ consommé (bizarre !)
            if freshness_status == "expired":
                title = "Attention à la fraîcheur"
                body = f"Vous avez consommé {product_name} qui était périmé. Assurez-vous qu'il était encore bon !"
                if remaining_quantity and remaining_quantity > 0:
                    body += f" Il en reste {remaining_quantity} {unit}, pensez à les jeter pour votre sécurité."
                return (title, body, "⚠️")

            # 🟠 CAS 2 : Produit qui expire AUJOURD'HUI
            elif freshness_status == "expires_today":
                title = "👍 Parfait timing !"
                body = f"Vous avez consommé {product_name} pile avant expiration. "
                if remaining_quantity and remaining_quantity > 0:
                    body += f"Attention, il en reste {remaining_quantity} {unit} qui expirent aujourd'hui !"
                else:
                    body += "Plus aucun gaspillage, bravo ! 🎉"
                return (title, body, "👍")

            # 🟡 CAS 3 : Produit qui expire BIENTÔT
            elif freshness_status == "expiring_soon":
                title = "⏰ Bonne initiative !"
                body = f"{product_name} consommé avant péremption. "

                if expiry_date:
                    from datetime import date as dt

                    try:
                        if isinstance(expiry_date, str):
                            exp_date = dt.fromisoformat(expiry_date)
                        else:
                            exp_date = expiry_date
                        days_left = (exp_date - dt.today()).days

                        if remaining_quantity and remaining_quantity > 0:
                            body += f"Il reste {remaining_quantity} {unit} (expire dans {days_left} jour{'s' if days_left > 1 else ''}). Pensez à tout finir ! 🍽️"
                        else:
                            body += "Plus de gaspillage possible ! ✨"
                    except:
                        pass

                return (title, body, "⏰")

            # CAS 4 : Produit FRAIS (normal)
            else:
                title = "🍽️ Bon appétit !"

                if source == "vision":
                    body = f"{product_name} détecté automatiquement et retiré de l'inventaire"
                else:
                    body = f"{product_name} retiré de votre inventaire"

                if quantity and unit:
                    body += f" ({quantity} {unit})"

                if remaining_quantity and remaining_quantity > 0:
                    body += f". Il en reste {remaining_quantity} {unit}."
                else:
                    body += ". Stock épuisé !"

                return (title, body, "🍽️")

        # ==========================================
        # ➕ ACTION : AJOUT
        # ==========================================
        elif action == "added":
            title = "📦 Nouveau produit !"

            if source == "vision":
                body = f"{product_name} détecté automatiquement par scan IA"
            else:
                body = f"{product_name} ajouté à votre frigo"

            if quantity and unit:
                body += f" ({quantity} {unit})"

            # Ajouter info sur fraîcheur si pertinent
            if freshness_status == "expiring_soon" and expiry_date:
                from datetime import date as dt

                try:
                    if isinstance(expiry_date, str):
                        exp_date = dt.fromisoformat(expiry_date)
                    else:
                        exp_date = expiry_date
                    days_left = (exp_date - dt.today()).days
                    body += f". Expire dans {days_left} jour{'s' if days_left > 1 else ''}, à consommer rapidement !"
                except:
                    pass

            return (title, body, "📦")

        # ==========================================
        # ✏️ ACTION : MODIFICATION
        # ==========================================
        elif action == "updated":
            title = "✏️ Produit mis à jour"
            body = f"{product_name} modifié"

            if quantity and unit:
                body += f" ({quantity} {unit})"

            return (title, body, "✏️")

        # ==========================================
        # 🗑️ ACTION : SUPPRESSION
        # ==========================================
        elif action == "removed":

            # Cas spécial : suppression d'un produit périmé
            if freshness_status == "expired":
                title = "🗑️ Bon réflexe !"
                body = f"{product_name} périmé retiré du frigo. Merci de garder un frigo sain !"
                return (title, body, "🗑️")

            # Cas spécial : suppression d'un produit qui expire bientôt
            elif freshness_status == "expiring_soon":
                title = "Produit retiré"
                body = f"{product_name} retiré alors qu'il expire bientôt. Pensez à le consommer si possible !"
                return (title, body, "⚠️")

            # Cas normal
            else:
                title = "🗑️ Produit retiré"
                body = f"{product_name} supprimé de l'inventaire"

                if quantity and unit:
                    body += f" ({quantity} {unit})"

                return (title, body, "🗑️")

        # ==========================================
        # FALLBACK (cas non géré)
        # ==========================================
        else:
            title = f"📱 Mise à jour : {product_name}"
            body = f"Action : {action}"
            if quantity and unit:
                body += f" ({quantity} {unit})"
            return (title, body, "📱")
