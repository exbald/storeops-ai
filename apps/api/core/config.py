import os

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = os.getenv("APP_ENV", "development")
    profile: str = os.getenv("PROFILE", "LOCAL")  # LOCAL or CLOUD
    ai_mode: str = os.getenv("AI_MODE", "STUB")   # LIVE or STUB
    port: int = int(os.getenv("PORT", "8000"))
    firebase_project_id: str = os.getenv("FIREBASE_PROJECT_ID", "storeops-dev")
    media_storage_dir: str = os.getenv("MEDIA_STORAGE_DIR", ".local_storage/media")
    state_backend: str = os.getenv("STATE_BACKEND", "in_memory")  # in_memory or firestore

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

