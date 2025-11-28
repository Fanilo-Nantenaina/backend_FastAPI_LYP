from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, Dict, Any
import logging

from app.middleware.transaction_handler import transactional
from app.models.user import User
from app.core.security import get_password_hash, verify_password
from app.schemas.user import UserUpdateRequest

logger = logging.getLogger(__name__)


class UserService:
    """Service de gestion des utilisateurs"""

    def __init__(self, db: Session):
        self.db = db

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Récupère un utilisateur par son ID"""
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Récupère un utilisateur par son email"""
        return self.db.query(User).filter(User.email == email).first()

    @transactional
    def create_user(
        self,
        email: str,
        name: str,
        password: str,
        timezone: str = "UTC",
        dietary_restrictions: Optional[list] = None,
    ) -> Optional[User]:
        """
        Crée un nouvel utilisateur

        Returns:
            User créé ou None si l'email existe déjà
        """
        try:
            user = User(
                email=email,
                name=name,
                password_hash=get_password_hash(password),
                timezone=timezone,
                dietary_restrictions=dietary_restrictions or [],
                prefs={},
            )

            self.db.add(user)
            # self.db.commit()
            self.db.refresh(user)

            logger.info(f"User created: {user.id} - {user.email}")
            return user

        except IntegrityError:
            self.db.rollback()
            logger.warning(f"User creation failed: email {email} already exists")
            return None

    @transactional
    def update_user(
        self, user_id: int, update_data: UserUpdateRequest
    ) -> Optional[User]:
        """Met à jour les informations d'un utilisateur"""
        user = self.get_user_by_id(user_id)

        if not user:
            return None

        if update_data.name is not None:
            user.name = update_data.name

        if update_data.preferred_cuisine is not None:
            user.preferred_cuisine = update_data.preferred_cuisine

        if update_data.dietary_restrictions is not None:
            user.dietary_restrictions = update_data.dietary_restrictions

        if update_data.timezone is not None:
            user.timezone = update_data.timezone

        if update_data.prefs is not None:
            current_prefs = user.prefs or {}
            current_prefs.update(update_data.prefs)
            user.prefs = current_prefs

        # self.db.commit()
        self.db.refresh(user)

        logger.info(f"User updated: {user.id}")
        return user

    @transactional
    def update_password(
        self, user_id: int, old_password: str, new_password: str
    ) -> bool:
        """
        Change le mot de passe d'un utilisateur

        Returns:
            True si le mot de passe a été changé, False sinon
        """
        user = self.get_user_by_id(user_id)

        if not user:
            return False

        if not verify_password(old_password, user.password_hash):
            logger.warning(
                f"Password update failed for user {user_id}: incorrect old password"
            )
            return False

        user.password_hash = get_password_hash(new_password)
        # self.db.commit()

        logger.info(f"Password updated for user {user_id}")
        return True

    @transactional
    def delete_user(self, user_id: int) -> bool:
        """
        Supprime un utilisateur

        Note: Cascade supprime automatiquement les fridges, listes, etc.
        """
        user = self.get_user_by_id(user_id)

        if not user:
            return False

        self.db.delete(user)
        # self.db.commit()

        logger.info(f"User deleted: {user_id}")
        return True

    def get_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """Récupère les préférences complètes d'un utilisateur"""
        user = self.get_user_by_id(user_id)

        if not user:
            return {}

        return {
            "timezone": user.timezone,
            "preferred_cuisine": user.preferred_cuisine,
            "dietary_restrictions": user.dietary_restrictions or [],
            "prefs": user.prefs or {},
        }

    @transactional
    def update_user_preferences(
        self, user_id: int, preferences: Dict[str, Any]
    ) -> Optional[User]:
        """Met à jour les préférences d'un utilisateur"""
        user = self.get_user_by_id(user_id)

        if not user:
            return None

        user.prefs = preferences
        # self.db.commit()
        self.db.refresh(user)

        return user
