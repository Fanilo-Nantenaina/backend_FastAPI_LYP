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
    def __init__(self, db: Session):
        self.db = db

    def send_email_notification(
        self, user_email: str, subject: str, body: str, html_body: Optional[str] = None
    ) -> bool:
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
        subject = self._get_alert_email_subject(alert)
        body = self._get_alert_email_body(alert)
        html_body = self._get_alert_email_html(alert)

        return self.send_email_notification(
            user_email=user.email, subject=subject, body=body, html_body=html_body
        )

    def _get_alert_email_subject(self, alert: Alert) -> str:
        subjects = {
            "EXPIRY_SOON": "Produits à consommer rapidement",
            "EXPIRED": "Produits périmés dans votre frigo",
            "LOST_ITEM": "Produits non détectés récemment",
            "LOW_STOCK": "Stock faible",
        }
        return subjects.get(alert.type, "📬 Alerte Smart Fridge")

    def _get_alert_email_body(self, alert: Alert) -> str:
        return f"""
            Bonjour,

            Vous avez une nouvelle alerte concernant votre réfrigérateur :

            {alert.message}

            Type d'alerte : {alert.type}
            Date : {alert.created_at.strftime("%d/%m/%Y %H:%M")}

            Connectez-vous à votre application Smart Fridge pour plus de détails.

            Cordialement,
            L'équipe Smart Fridge
        """

    def _get_alert_email_html(self, alert: Alert) -> str:
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
                            <h2 style="margin-top: 0;">{alert.type.replace("_", " ").title()}</h2>
                            <p style="font-size: 16px;">{alert.message}</p>
                            <p style="color: #666; font-size: 14px;">
                                Date : {alert.created_at.strftime("%d/%m/%Y à %H:%M")}
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
            Bonjour {user.name or "cher utilisateur"},

            Voici le résumé quotidien de votre frigo "{fridge.name}" :

                    - Articles en stock : {inventory_count}
                    - Alertes en attente : {len(pending_alerts)}

            {"=" * 50}
            ALERTES EN ATTENTE :
            {"=" * 50}

        """

        if pending_alerts:
            for alert in pending_alerts:
                body += f"• [{alert.type}] {alert.message}\n"
        else:
            body += "Aucune alerte en attente. Tout va bien ! \n"

        body += f"""

            {"=" * 50}

            Consultez votre application pour plus de détails.

            Bonne journée !
            L'équipe Smart Fridge
        """

        return self.send_email_notification(
            user_email=user.email, subject=subject, body=body
        )

    def _sanitize_fcm_data(self, data: Optional[Dict[str, Any]]) -> Dict[str, str]:
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
        try:
            import firebase_admin
            from firebase_admin import credentials, messaging

            if not firebase_admin._apps:
                cred = credentials.Certificate(
                    "smart-fridge-357b0-firebase-adminsdk-fbsvc-e5dbd0f2cb.json"
                )
                firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin SDK initialized")

            fridges = (
                self.db.query(Fridge)
                .filter(Fridge.user_id == user_id, Fridge.is_paired)
                .all()
            )

            if not fridges:
                logger.info(f"No paired fridges found for user {user_id}")
                return False

            safe_data = self._sanitize_fcm_data(data)

            success_count = 0

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

                    message = messaging.Message(
                        notification=messaging.Notification(
                            title=title,
                            body=body,
                        ),
                        data=safe_data,
                        token=fcm_token,
                        android=messaging.AndroidConfig(
                            priority="high",
                            notification=messaging.AndroidNotification(
                                sound="default",
                                channel_id="smart_fridge_alerts",
                                color="#3B82F6",
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
        if not user.prefs or "phone_number" not in user.prefs:
            logger.info(f"No phone number for user {user.id}")
            return False

        phone_number = user.prefs["phone_number"]

        message = f"Smart Fridge Alert: {alert.message}. Consultez l'app pour plus de détails."

        return self.send_sms_notification(phone_number, message)

    def notify_alert(
        self, alert: Alert, user: User, channels: List[str] = ["push", "email"]
    ) -> Dict[str, bool]:
        results = {}

        if "email" in channels:
            results["email"] = self.send_alert_email(alert, user)

        if "push" in channels:
            results["push"] = self.send_alert_push(alert, user.id)

        if "sms" in channels:
            results["sms"] = self.send_alert_sms(alert, user)

        return results

    def notify_expiry_batch(self, fridge_id: int, user: User) -> bool:
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
            Bonjour {user.name or "cher utilisateur"},

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
        try:
            fridge = (
                self.db.query(Fridge)
                .filter(Fridge.id == fridge_id, Fridge.user_id == user_id)
                .first()
            )

            if not fridge:
                logger.warning(f"Fridge {fridge_id} not found for user {user_id}")
                return False

            if not fridge.kiosk_metadata:
                fridge.kiosk_metadata = {}

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
        try:
            fridge = self.db.query(Fridge).filter(Fridge.id == fridge_id).first()
            if not fridge or not fridge.user_id:
                logger.warning(f"Fridge {fridge_id} not found or no user")
                return False

            title_map = {
                "added": "Produit ajouté",
                "updated": "Produit modifié",
                "consumed": "Produit consommé",
                "removed": "Produit retiré",
            }

            title = title_map.get(action, "Inventaire mis à jour")

            if quantity and unit:
                body = f"{product_name} : {quantity} {unit}"
            else:
                body = product_name

            if source == "vision":
                body += " (scan IA)"

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
        fridge = self.db.query(Fridge).filter(Fridge.id == fridge_id).first()
        if not fridge or not fridge.user_id:
            logger.warning(f"Fridge {fridge_id} not found or no user")
            return False

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
        if action == "consumed":
            if freshness_status == "expired":
                title = "Attention à la fraîcheur"
                body = f"Vous avez consommé {product_name} qui était périmé. Assurez-vous qu'il était encore bon !"
                if remaining_quantity and remaining_quantity > 0:
                    body += f" Il en reste {remaining_quantity} {unit}, pensez à les jeter pour votre sécurité."
                return (title, body, "⚠️")

            elif freshness_status == "expires_today":
                title = "👍 Parfait timing !"
                body = f"Vous avez consommé {product_name} pile avant expiration. "
                if remaining_quantity and remaining_quantity > 0:
                    body += f"Attention, il en reste {remaining_quantity} {unit} qui expirent aujourd'hui !"
                else:
                    body += "Plus aucun gaspillage, bravo ! 🎉"
                return (title, body, "👍")

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
                    except Exception:
                        pass

                return (title, body, "⏰")

            else:
                title = "Bon appétit !"

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

        elif action == "added":
            title = "Nouveau produit !"

            if source == "vision":
                body = f"{product_name} détecté automatiquement par scan IA"
            else:
                body = f"{product_name} ajouté à votre frigo"

            if quantity and unit:
                body += f" ({quantity} {unit})"

            if freshness_status == "expiring_soon" and expiry_date:
                from datetime import date as dt

                try:
                    if isinstance(expiry_date, str):
                        exp_date = dt.fromisoformat(expiry_date)
                    else:
                        exp_date = expiry_date
                    days_left = (exp_date - dt.today()).days
                    body += f". Expire dans {days_left} jour{'s' if days_left > 1 else ''}, à consommer rapidement !"
                except Exception:
                    pass

            return (title, body, "")

        elif action == "updated":
            title = "Produit mis à jour"
            body = f"{product_name} modifié"

            if quantity and unit:
                body += f" ({quantity} {unit})"

            return (title, body, "✏️")

        elif action == "removed":
            if freshness_status == "expired":
                title = "Bon réflexe !"
                body = f"{product_name} périmé retiré du frigo. Merci de garder un frigo sain !"
                return (title, body, "🗑️")

            elif freshness_status == "expiring_soon":
                title = "Produit retiré"
                body = f"{product_name} retiré alors qu'il expire bientôt. Pensez à le consommer si possible !"
                return (title, body, "⚠️")

            else:
                title = "Produit retiré"
                body = f"{product_name} supprimé de l'inventaire"

                if quantity and unit:
                    body += f" ({quantity} {unit})"

                return (title, body, "🗑️")

        else:
            title = f"Mise à jour : {product_name}"
            body = f"Action : {action}"
            if quantity and unit:
                body += f" ({quantity} {unit})"
            return (title, body, "📱")

    def send_batch_scan_notification(
        self,
        fridge_id: int,
        scan_type: str,
        products: List[Dict[str, Any]],
    ) -> bool:
        import logging

        logger = logging.getLogger(__name__)

        try:
            fridge = self.db.query(Fridge).filter(Fridge.id == fridge_id).first()
            if not fridge or not fridge.user_id:
                logger.warning(f"Fridge {fridge_id} not found or no user")
                return False

            if not products:
                logger.info("No products to notify")
                return False

            title, body, emoji = self._generate_batch_scan_message(
                scan_type=scan_type,
                products=products,
            )

            data = {
                "type": "batch_scan",
                "scan_type": scan_type,
                "fridge_id": str(fridge_id),
                "product_count": str(len(products)),
                "timestamp": datetime.utcnow().isoformat(),
            }

            success = self.send_push_notification(
                user_id=fridge.user_id,
                title=title,
                body=body,
                data=data,
            )

            if success:
                logger.info(
                    f"Batch notification sent: {len(products)} products "
                    f"({scan_type}) to fridge {fridge_id}"
                )
            else:
                logger.warning(" Failed to send batch notification")

            return success

        except Exception as e:
            logger.error(f"Failed to send batch scan notification: {e}")
            return False

    def _generate_batch_scan_message(
        self,
        scan_type: str,
        products: List[Dict[str, Any]],
    ) -> tuple:
        total_products = len(products)

        if scan_type == "add":
            added_count = sum(1 for p in products if p.get("action") == "added")
            updated_count = sum(1 for p in products if p.get("action") == "updated")

            expiring_soon = []
            expires_today = []

            for product in products:
                freshness = product.get("freshness_status", "unknown")
                if freshness == "expiring_soon":
                    expiring_soon.append(product["product_name"])
                elif freshness == "expires_today":
                    expires_today.append(product["product_name"])

            title = f"{total_products} produit{'s' if total_products > 1 else ''} scanné{'s' if total_products > 1 else ''}"

            body_parts = []

            if total_products <= 3:
                product_list = ", ".join([p["product_name"] for p in products])
                body_parts.append(product_list)
            else:
                first_products = ", ".join([p["product_name"] for p in products[:2]])
                remaining = total_products - 2
                body_parts.append(
                    f"{first_products} et {remaining} autre{'s' if remaining > 1 else ''}"
                )

            action_details = []
            if added_count > 0:
                action_details.append(
                    f"{added_count} ajouté{'s' if added_count > 1 else ''}"
                )
            if updated_count > 0:
                action_details.append(f"{updated_count} mis à jour")

            if action_details:
                body_parts.append(f"({', '.join(action_details)})")

            if expires_today:
                body_parts.append(
                    f" {len(expires_today)} expire{'nt' if len(expires_today) > 1 else ''} aujourd'hui !"
                )
            elif expiring_soon:
                body_parts.append(
                    f"⏰ {len(expiring_soon)} expire{'nt' if len(expiring_soon) > 1 else ''} bientôt"
                )

            body = " • ".join(body_parts)
            emoji = ""

        elif scan_type == "consume":
            fully_consumed = sum(
                1 for p in products if p.get("remaining_quantity", 1) == 0
            )
            partially_consumed = total_products - fully_consumed

            expired_consumed = sum(
                1 for p in products if p.get("freshness_status") == "expired"
            )

            title = f"{total_products} produit{'s' if total_products > 1 else ''} consommé{'s' if total_products > 1 else ''}"

            body_parts = []

            if total_products <= 3:
                product_list = ", ".join([p["product_name"] for p in products])
                body_parts.append(product_list)
            else:
                first_products = ", ".join([p["product_name"] for p in products[:2]])
                remaining = total_products - 2
                body_parts.append(
                    f"{first_products} et {remaining} autre{'s' if remaining > 1 else ''}"
                )

            stock_details = []
            if fully_consumed > 0:
                stock_details.append(
                    f"{fully_consumed} épuisé{'s' if fully_consumed > 1 else ''}"
                )
            if partially_consumed > 0:
                stock_details.append(f"{partially_consumed} en stock")

            if stock_details:
                body_parts.append(f"({', '.join(stock_details)})")

            if expired_consumed > 0:
                body_parts.append(
                    f" {expired_consumed} périmé{'s' if expired_consumed > 1 else ''} !"
                )

            body = " • ".join(body_parts)
            emoji = "🍽️"

        else:
            title = f"{total_products} produits mis à jour"
            body = ", ".join([p["product_name"] for p in products[:3]])
            if total_products > 3:
                body += f" et {total_products - 3} autres"
            emoji = "📱"

        return (title, body, emoji)
