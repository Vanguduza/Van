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
    #: P0-SEC-001. Per-purpose credentials as `scope,scope:token; scope:token`. The legacy
    #: token above keeps every scope except device_enrolment, so an existing deployment is
    #: not broken by this and the one scope that mints owner-device authority has to be
    #: granted deliberately.
    internal_control_scoped_tokens: str = ""
    #: P0-SEC-001. The one credential that can mint owner-device authority, kept out of
    #: everything the Hermes runtime reads. Empty means device enrolment is unreachable,
    #: which is inconvenient once and is the right way round.
    device_enrolment_token: str = ""
    #: Gate 11 operator surface (metrics, alerts, health, command trace).
    #: Granted on purpose; the legacy internal token does not carry this scope.
    observability_token: str = ""
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
    #: P2-DEAD-001 — HMAC secret for signed provider webhooks. Empty means signed ingress is
    #: refused rather than accepted unverified: an unauthenticated event ingress is how an
    #: external system starts writing VAN's evidence store.
    automation_webhook_secret: str = ""
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
    notebook_consumer_profile_dir: str = ""  # legacy; direct Playwright is no longer used
    notebook_consumer_profile_alias: str = "authenticated_owner"
    notebook_consumer_profile_secret_ref: str = "secretref://browser/google-primary"
    notebook_consumer_base_url: str = "https://notebooklm.google.com"
    notebook_consumer_headless: bool = True
    notebook_consumer_timeout_seconds: float = 20.0
    #: P1-GOOG-002 — where "make a note" lands when the owner does not name a
    #: notebook. Empty means no default, and such a command is refused rather
    #: than letting the agent runtime choose one of the owner's notebooks.
    notebook_default_id: str = ""

    require_hermes_for_mutations: bool = True
    event_page_size: int = 100

    # ---- Gate 11: observability and operations -----------------------------
    #: Log level for the structured JSON logger (P3-OBS-001).
    log_level: str = "INFO"
    #: The scheduler that makes due work actually happen (P3-OPS-004). Defaulted on:
    #: a reminder the owner set is not optional, and the previous state of the world
    #: — the routine existing with no caller — is what the finding was about.
    scheduler_enabled: bool = True
    #: How often due reminders are swept. A minute is the resolution a reminder is
    #: worth; anything finer is a busy loop against SQLite for no owner-visible gain.
    reminder_sweep_seconds: int = 60
    #: P0-EXEC-002 — how long VAN waits for a dispatched command before telling the
    #: owner it never heard back. Zero disables the deadline entirely, which means
    #: going back to a mission that can sit at RUNNING forever.
    execution_deadline_seconds: int = 900
    #: How often retention runs (P3-OPS-001). Daily: the horizons are in days, so a
    #: more frequent sweep deletes the same rows a day earlier at best.
    retention_interval_seconds: int = 86_400
    #: How often PKI expiry is re-read (P3-OPS-003). Certificates expire on a scale
    #: of days; an hour is ample and keeps the alert fresh across a renewal.
    pki_scan_interval_seconds: int = 3_600
    #: Where the bridge PKI lives. Empty means this deployment has no trading PKI,
    #: which is reported as absent rather than as expired.
    pki_dir: str = ""
    #: Where backups are written and read from (P3-OPS-002). Empty means backups are
    #: not configured here, which the health surface distinguishes from stale.
    backup_dir: str = ""
    #: Whether the scheduler takes a backup itself. Off by default: on most hosts the
    #: backup belongs to a system-level job with its own offsite target, and a
    #: scheduler that writes backups to the same disk as the database is not a backup.
    backup_enabled: bool = False
    backup_interval_seconds: int = 86_400
    #: P3-OPS-009 — whether the scheduler proves a backup can be restored, rather than
    #: only that it was written. Owner decision 10 in the closure blueprint took "local
    #: only, with the drill enabled" as the default, and the drill was the half that had
    #: no caller: `ops.backup.drill` was complete and referenced by its own tests alone.
    #: On by default because a backup nobody has restored is a hypothesis, and this is
    #: the cheapest way to stop holding one. It restores into a scratch directory and
    #: never touches the live database.
    backup_drill_enabled: bool = True
    #: Weekly. The drill copies the whole database, so it is a heavier job than the
    #: backup; a week is often enough to catch a format or permission change before the
    #: night it matters.
    backup_drill_interval_seconds: int = 604_800

    # ---- Remote Browser Rev 1.5 -------------------------------------------------
    #
    # Empty is the honest default. There is no Browser Stream Host in this deployment
    # until the owner provisions one (RB-002/RB-010), and a gateway that invents a signal
    # URL would hand the phone an endpoint that does not answer — §42.5's "integrated
    # because a dependency exists", one layer down.
    #: PEM file holding the dedicated ES256 grant-signing private key (§5.5). Empty means
    #: no grant can be minted, so the interactive routes are not mounted at all.
    browser_stream_signing_key_file: str = ""
    #: Mandatory `kid`. Rotation keeps the previous verifier for an overlap window on the
    #: stream host; the Gateway signs with exactly one.
    browser_stream_signing_kid: str = "browser-stream-signing-1"
    #: Where the device performs SDP/ICE signalling. §6.4: never `van-trading-core`, which
    #: is private and holds the Browser Fabric's authority.
    browser_stream_signal_url: str = ""
    #: JSON array of ICE servers, passed through to the device verbatim. Deployment
    #: configuration, not owner authority.
    browser_stream_ice_servers: str = "[]"


@lru_cache
def get_settings() -> Settings:
    return Settings()