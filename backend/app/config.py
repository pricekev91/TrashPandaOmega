from functools import lru_cache
from pydantic import BaseModel
import os


class Settings(BaseModel):
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://trashpanda:trashpanda@db:5432/trashpanda",
    )
    api_host: str = os.getenv("TRASHPANDA_API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("TRASHPANDA_API_PORT", "8000"))
    ai_base_url: str = os.getenv("TRASHPANDA_AI_BASE_URL", "http://192.168.6.252:8080/v1")
    ai_model: str = os.getenv("TRASHPANDA_AI_MODEL", "qwen2.5-coder-verbose:latest")
    config_dir: str = os.getenv("TRASHPANDA_CONFIG_DIR", "/app/config")
    data_dir: str = os.getenv("TRASHPANDA_DATA_DIR", "/app/data")
    artifacts_dir: str = os.getenv("TRASHPANDA_ARTIFACTS_DIR", "/app/data/incoming")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()