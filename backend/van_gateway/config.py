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
    internal_control_token: str = ""  # Hermes→gateway privileged Google job API
    vati_ledger_path: str = "data/vati_ledger.sqlite3"  # VATI hash-chained trading ledger (read; owner A4 writes only); postgres://… also accepted
    vati_accounts_registry: str = "data/vati_accounts.json"  # non-secret account registry (aliases, broker kind, safety identity)
    vati_lake_root: str = "data/vati_lake"  # bar lake for charts
    vati_reporting_currency: str = "USD"
    owner_intent_max_age_seconds: int = 24 * 60 * 60
    attention_budget_per_hour: int = 12

    # Google Workspace OAuth. Refresh tokens are encrypted in SQLite; client secrets
    # stay in the runtime environment and never enter model-visible payloads.
    google_token_fernet_key: str = ""
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    # Canonical Google-account sovereignty metadata. The raw Google account
    # identifier is only used by the local setup tool and is never persisted.
    google_ai_plan: str = "UNKNOWN"
    google_cloud_project_id: str = ""
    google_gemini_runtime_configured: bool = False
    google_cloud_runtime_configured: bool = False
    google_consumer_connected_capabilities: str = ""

    require_hermes_for_mutations: bool = True
    event_page_size: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
