import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = os.getenv("APP_ENV", "development")
    profile: str = os.getenv("PROFILE", "LOCAL")  # LOCAL or CLOUD
    ai_mode: str = os.getenv("AI_MODE", "STUB")   # LIVE or STUB
    port: int = int(os.getenv("PORT", "8000"))
    firebase_project_id: str = os.getenv("FIREBASE_PROJECT_ID", "storeops-dev")
    media_storage_dir: str = os.getenv("MEDIA_STORAGE_DIR", ".local_storage/media")
    state_backend: str = os.getenv("STATE_BACKEND", "in_memory")  # in_memory or firestore

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ["production", "prod"]


settings = Settings()
