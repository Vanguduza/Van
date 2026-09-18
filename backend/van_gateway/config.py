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

    # Rev 1.3 Automation & Browser Fabric. All switches default OFF and
    # runtime credentials remain in the gateway environment/secret plane.
    automation_enabled: bool = False
    automation_ingress_enabled: bool = False
    automation_egress_enabled: bool = False
    automation_n8n_base_url: str = "http://127.0.0.1:5678/api/v1"
    automation_n8n_api_key: str = ""
    automation_n8n_expected_version: str = ""
    automation_grant_signing_key: str = ""
    automation_grant_ttl_seconds: int = 300
    automation_timeout_seconds: float = 15.0
    automation_max_concurrency: int = 1

    browser_enabled: bool = False
    browser_harness_base_url: str = "http://127.0.0.1:9141"
    browser_harness_expected_version: str = ""
    browser_stagehand_base_url: str = "http://127.0.0.1:9140"
    browser_stagehand_expected_version: str = ""
    browser_stagehand_model_provider: str = ""
    browser_stagehand_model_name: str = ""

    # Rev 3.1 knowledge-source capability plane. These providers emit evidence
    # or verified mutation receipts only; none can promote itself to owner truth.
    vekl_enabled: bool = False
    vekl_base_url: str = ""
    vekl_session_id: str = ""
    vekl_principal_id: str = ""
    vekl_bearer_token: str = ""
    vekl_timeout_seconds: float = 8.0

    obsidian_enabled: bool = False
    obsidian_vault_path: str = ""
    obsidian_max_file_bytes: int = 2_000_000
    obsidian_max_files: int = 20_000
    obsidian_refresh_interval_seconds: int = 30

    notebook_enterprise_enabled: bool = False
    notebook_enterprise_project_number: str = ""
    notebook_enterprise_location: str = "global"
    notebook_enterprise_service_account_file: str = ""
    notebook_enterprise_access_token_file: str = ""
    notebook_enterprise_timeout_seconds: float = 20.0
    notebook_enterprise_upload_root: str = ""
    notebook_enterprise_max_upload_bytes: int = 100_000_000

    notebook_consumer_enabled: bool = False
    notebook_consumer_profile_dir: str = ""
    notebook_consumer_base_url: str = "https://notebooklm.google.com"
    notebook_consumer_headless: bool = True
    notebook_consumer_timeout_seconds: float = 20.0

    require_hermes_for_mutations: bool = True
    event_page_size: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()