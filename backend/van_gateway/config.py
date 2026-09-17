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
    internal_control_token: str = ""  # Hermes→gateway privileged control API
    ingress_token: str = ""  # Owner-device bearer gate for externally reachable HTTP routes
    device_secret_fernet_key: str = ""  # Android HMAC secrets encrypted at rest

    # VATI trading plane. Broker secrets remain on the trading host.
    vati_ledger_path: str = "data/vati_ledger.sqlite3"
    vati_accounts_registry: str = "data/vati_accounts.json"
    vati_lake_root: str = "data/vati_lake"
    vati_reporting_currency: str = "USD"
    vati_secrets_dir: str = "data/vati_secrets"
    van_commander_url: str = ""
    van_commander_token_file: str = ""
    van_commander_ca_file: str = ""
    van_public_base_url: str = "http://127.0.0.1:8787"
    vati_deriv_app_id: str = "1089"

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

    # Rev 3.1 research capability. Exa credentials belong only to the gateway
    # capability plane and are never exposed to Android or model-visible payloads.
    exa_api_key: str = ""
    exa_base_url: str = "https://api.exa.ai"
    exa_egress_enabled: bool = False
    exa_timeout_seconds: float = 20.0

    # Rev 1.3 Automation & Browser Fabric. Every switch below defaults OFF:
    # §368 permits repository-side code before the owner security amendment only
    # when it is fail-closed behind disabled feature gates, and §365 makes n8n
    # adoption, egress, ingress and browser attachment owner-gated decisions.
    automation_enabled: bool = False
    automation_ingress_enabled: bool = False
    automation_egress_enabled: bool = False
    automation_n8n_base_url: str = "http://127.0.0.1:5678/api/v1"
    automation_n8n_api_key: str = ""
    automation_n8n_expected_version: str = ""
    automation_grant_signing_key: str = ""  # MACs run capability grants (§160)
    automation_grant_ttl_seconds: int = 300
    automation_timeout_seconds: float = 15.0
    automation_max_concurrency: int = 1  # §13 — start conservative, raise on measurement

    browser_enabled: bool = False
    browser_harness_base_url: str = "http://127.0.0.1:9141"
    browser_harness_expected_version: str = ""
    browser_stagehand_base_url: str = "http://127.0.0.1:9140"
    browser_stagehand_expected_version: str = ""
    # §418 — the provider is configured, never chosen by a model or page content.
    browser_stagehand_model_provider: str = ""
    browser_stagehand_model_name: str = ""
    # Rev 1.2 review M3 / §378 — production stops at observe → deterministic action.
    browser_semantic_max_tier: str = "L3"

    require_hermes_for_mutations: bool = True
    event_page_size: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
