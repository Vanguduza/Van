from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VAN_", env_file=".env", extra="ignore")

    app_name: str = "van-gateway"
    database_path: str = "data/van_gateway.sqlite3"
    hermes_base_url: str = "http://127.0.0.1:8642"
    hermes_profile: str = "van"
    hermes_bearer_token: str = ""
    owner_intent_max_age_seconds: int = 24 * 60 * 60
    attention_budget_per_hour: int = 12
    google_token_fernet_key: str = ""  # required for live Google; empty => Google degraded
    require_hermes_for_mutations: bool = True
    event_page_size: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
