from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    frontend_origin: str

    resume_storage_dir: str
    resume_max_bytes: int

    google_client_id: str
    attorney_emails: str

    # Empty smtp_host selects the console fallback instead of sending.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    email_from: str

    # Public form limits (per client address, per process).
    submission_rate_limit: int = 10
    submission_rate_window_seconds: int = 3600

    @property
    def max_request_bytes(self) -> int:
        # The resume plus room for the text fields and multipart framing.
        return self.resume_max_bytes + 64 * 1024

    @property
    def attorney_email_list(self) -> list[str]:
        return [e.strip() for e in self.attorney_emails.split(",") if e.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
