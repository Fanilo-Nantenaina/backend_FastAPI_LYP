from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    APP_NAME: str = "Smart Fridge API"
    VERSION: str = "2.0.0"
    DEBUG: bool = False

    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    EXPIRY_WARNING_DAYS: int = 3
    LOST_ITEM_HOURS: int = 72

    DEVICE_PAIRING_CODE_LENGTH: int = 6
    DEVICE_PAIRING_TIMEOUT_MINUTES: int = 5

    REDIS_URL: Optional[str] = None

    SCHEDULER_ENABLED: bool = True
    ALERT_CHECK_INTERVAL_HOURS: int = 1
    SEND_DAILY_SUMMARY: bool = True
    DAILY_SUMMARY_TIME: str = "08:00"

    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "noreply@smartfridge.com"

    FCM_SERVER_KEY: Optional[str] = None
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None

    ALLOWED_ORIGINS: List[str] = ["http://localhost", "http://localhost:3000"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
