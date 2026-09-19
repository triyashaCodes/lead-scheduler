from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    frontend_origin: str

    resume_storage_dir: str
    max_resume_size_bytes: int

    google_client_id: str
    attorney_emails: str

    smtp_host: str
    smtp_port: int
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str
    attorney_notification_email: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
