import os

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

load_dotenv(override=True)


class ConfigurationError(RuntimeError):
    """Raised when the configured backends are incomplete or inconsistent."""


class Settings(BaseSettings):
    app_env: str = os.getenv("APP_ENV", "development")
    profile: str = os.getenv("PROFILE", "LOCAL")  # LOCAL or CLOUD
    ai_mode: str = os.getenv("AI_MODE", "STUB")   # LIVE or STUB
    port: int = int(os.getenv("PORT", "8000"))
    firebase_project_id: str = (
        os.getenv("FIREBASE_PROJECT_ID")
        or os.getenv("GCP_PROJECT")
        or os.getenv("STOREOPS_PROJECT_ID")
        or "storeops-dev"
    )
    media_storage_dir: str = os.getenv("MEDIA_STORAGE_DIR", ".local_storage/media")
    state_backend: str = os.getenv("STATE_BACKEND", "in_memory")  # in_memory or firestore
    data_backend: str = os.getenv("DATA_BACKEND", "LOCAL")  # LOCAL (DuckDB) or CLOUD (BigQuery)
    media_bucket: str | None = os.getenv("MEDIA_BUCKET") or None  # GCS bucket for media bytes
    gcp_project: str | None = os.getenv("GCP_PROJECT") or os.getenv("GCP_PROJECT_ID") or None
    bigquery_dataset: str | None = os.getenv("BIGQUERY_DATASET") or None
    # HMAC key for signed media byte URLs; required for PROFILE=CLOUD (see blob/signing.py).
    media_url_signing_key: str | None = Field(
        default=os.getenv("MEDIA_URL_SIGNING_KEY") or None, repr=False
    )

    @model_validator(mode="after")
    def validate_cloud_profile(self) -> "Settings":
        if self.profile.upper() == "CLOUD":
            if self.ai_mode.upper() == "STUB":
                raise ValueError("Cloud profile refuses stub AI mode; live credentials required")
            if self.state_backend.lower() == "in_memory":
                raise ValueError("Cloud profile refuses in_memory state backend; Firestore required")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ["production", "prod"]


settings = Settings()

