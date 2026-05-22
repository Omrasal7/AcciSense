from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="AcciSense API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    frontend_origin: str = Field(default="http://localhost:5173", alias="FRONTEND_ORIGIN")
    public_base_url: str = Field(default="http://localhost:8000", alias="PUBLIC_BASE_URL")

    accident_model_path: Path = Field(default=Path("../models/accident_cls.pt"), alias="ACCIDENT_MODEL_PATH")
    severity_model_path: Path = Field(default=Path("../models/severity_cls.pt"), alias="SEVERITY_MODEL_PATH")
    upload_dir: Path = Field(default=Path("./data/uploads"), alias="UPLOAD_DIR")
    database_path: Path = Field(default=Path("./data/accisense.db"), alias="DATABASE_PATH")
    camera_registry_path: Path = Field(default=Path("./data/camera_registry.csv"), alias="CAMERA_REGISTRY_PATH")

    enable_opencv_fallback: bool = Field(default=False, alias="ENABLE_OPENCV_FALLBACK")
    enable_twilio: bool = Field(default=False, alias="ENABLE_TWILIO")
    enable_email: bool = Field(default=False, alias="ENABLE_EMAIL")

    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str = Field(default="", alias="TWILIO_FROM_NUMBER")

    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="", alias="SMTP_FROM_EMAIL")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")

    google_maps_api_key: str = Field(default="", alias="GOOGLE_MAPS_API_KEY")
    default_alert_emails: str = Field(default="", alias="DEFAULT_ALERT_EMAILS")
    default_alert_phones: str = Field(default="", alias="DEFAULT_ALERT_PHONES")


@lru_cache
def get_settings() -> Settings:
    return Settings()
